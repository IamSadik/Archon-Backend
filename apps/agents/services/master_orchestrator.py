"""
Master Orchestrator - Central coordination layer for the autonomous agent system.

This is the "brain" that coordinates:
1. User message routing (planning vs execution vs query)
2. Planner <-> Executor handoffs
3. Session continuity and checkpoint management
4. Memory integration across all operations
5. WebSocket real-time updates

The Master Orchestrator is the single entry point for all agent interactions.
"""
import asyncio
import logging
from typing import Dict, Any, Optional, Callable, Awaitable
from uuid import uuid4
from dataclasses import dataclass, field
from enum import Enum

from django.utils import timezone
from django.db import transaction
from asgiref.sync import sync_to_async

from apps.agents.models import AgentSession, AgentExecution
from apps.agents.services.autonomous_executor import (
    AutonomousExecutor,
    ExecutionState,
    ExecutionContext,
    ExecutionCheckpoint
)
from apps.planning.services import PlanningService, PlannerOrchestrator
from apps.memory.services import MemoryService
from apps.projects.models import Project

logger = logging.getLogger(__name__)


class MessageIntent(Enum):
    """Types of user message intents."""
    PLANNING = "planning"           # Create/modify plans, features, tasks
    EXECUTION = "execution"         # Execute code, run tasks
    QUERY = "query"                 # Ask questions about project/code
    CONTROL = "control"             # Pause, resume, stop, status
    CONTINUATION = "continuation"   # Continue previous work
    CLARIFICATION = "clarification" # Response to a question


@dataclass
class OrchestratorSession:
    """Tracks the current orchestrator session state."""
    session_id: str
    project_id: str
    user_id: str
    agent_session: Optional[AgentSession] = None
    planner_active: bool = False
    executor_active: bool = False
    current_intent: Optional[MessageIntent] = None
    awaiting_response: bool = False
    awaiting_type: Optional[str] = None
    last_planner_result: Optional[Dict] = None
    last_executor_result: Optional[Dict] = None
    context: Dict[str, Any] = field(default_factory=dict)


class MasterOrchestrator:
    """
    Central orchestrator that coordinates all agent operations.
    
    This is the main entry point for:
    - Processing user messages
    - Coordinating planner and executor
    - Managing session state and checkpoints
    - Handling real-time updates via callbacks
    
    Usage:
        orchestrator = MasterOrchestrator(user, project)
        result = await orchestrator.process_message("Add user authentication")
    """
    
    def __init__(
        self,
        user,
        project: Project,
        on_status_update: Callable[[Dict[str, Any]], Awaitable[None]] = None,
        on_planner_update: Callable[[Dict[str, Any]], Awaitable[None]] = None,
        on_executor_update: Callable[[Dict[str, Any]], Awaitable[None]] = None,
        on_user_input_needed: Callable[[Dict[str, Any]], Awaitable[None]] = None
    ):
        """
        Initialize the Master Orchestrator.
        
        Args:
            user: User instance
            project: Project to work on
            on_status_update: Callback for general status updates
            on_planner_update: Callback for planner-specific updates
            on_executor_update: Callback for executor-specific updates
            on_user_input_needed: Callback when user input is required
        """
        self.user = user
        self.project = project
        
        # Callbacks for real-time updates
        self.on_status_update = on_status_update
        self.on_planner_update = on_planner_update
        self.on_executor_update = on_executor_update
        self.on_user_input_needed = on_user_input_needed
        
        # Initialize services
        self.planner_orchestrator = PlannerOrchestrator(user, project)
        self.memory_service = MemoryService(user, project)
        self.planning_service = PlanningService(user, project)
        
        # Executor (created on demand)
        self._executor: Optional[AutonomousExecutor] = None
        
        # Session state
        self._session: Optional[OrchestratorSession] = None
        self._agent_session: Optional[AgentSession] = None
        
        # Intent classification keywords
        self._intent_keywords = {
            MessageIntent.PLANNING: [
                'plan', 'feature', 'create', 'add', 'design', 'architect',
                'breakdown', 'split', 'organize', 'structure', 'roadmap',
                'milestone', 'epic', 'story', 'requirement'
            ],
            MessageIntent.EXECUTION: [
                'implement', 'code', 'build', 'write', 'generate', 'execute',
                'run', 'deploy', 'test', 'fix', 'debug', 'refactor'
            ],
            MessageIntent.QUERY: [
                'what', 'how', 'why', 'where', 'when', 'explain', 'show',
                'list', 'describe', 'status', 'progress'
            ],
            MessageIntent.CONTROL: [
                'pause', 'stop', 'resume', 'cancel', 'restart', 'reset'
            ],
            MessageIntent.CONTINUATION: [
                'continue', 'next', 'proceed', 'go on', 'keep going'
            ]
        }
    
    # ==================== Main Entry Points ====================
    
    async def process_message(
        self,
        message: str,
        session_context: Dict = None
    ) -> Dict[str, Any]:
        """
        Process a user message - main entry point.
        
        This method:
        1. Classifies the intent
        2. Routes to appropriate handler (planner/executor/query)
        3. Manages handoffs between components
        4. Returns unified response
        
        Args:
            message: User's message
            session_context: Optional context from previous interactions
            
        Returns:
            Response dictionary with results and next steps
        """
        session_context = session_context or {}
        
        # Ensure we have a session
        if not self._session:
            await self._initialize_session()
        
        # Update session context
        self._session.context.update(session_context)
        
        # Notify status
        await self._notify_status("processing", {"message": message[:100]})
        
        try:
            # Step 1: Check if this is a response to a pending question
            if self._session.awaiting_response:
                return await self._handle_clarification_response(message)
            
            # Step 2: Classify intent
            intent = await self._classify_intent(message)
            self._session.current_intent = intent
            
            # Step 3: Retrieve relevant context
            memory_context = await self._get_memory_context(message)
            
            # Step 4: Route to appropriate handler
            if intent == MessageIntent.CONTROL:
                result = await self._handle_control_message(message)
            elif intent == MessageIntent.QUERY:
                result = await self._handle_query_message(message, memory_context)
            elif intent == MessageIntent.CONTINUATION:
                result = await self._handle_continuation(memory_context)
            elif intent == MessageIntent.PLANNING:
                result = await self._handle_planning_message(message, memory_context)
            elif intent == MessageIntent.EXECUTION:
                result = await self._handle_execution_message(message, memory_context)
            else:
                # Default to planning for ambiguous messages
                result = await self._handle_planning_message(message, memory_context)
            
            # Step 5: Store interaction in memory
            await self._store_interaction(message, intent, result)
            
            # Step 6: Check if we need to hand off to executor
            if result.get('delegate_to_executor'):
                result = await self._handoff_to_executor(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self._notify_status("error", {"error": str(e)})
            return {
                'success': False,
                'error': str(e),
                'type': 'error'
            }
    
    async def restore_session(self, session_id: str = None) -> Dict[str, Any]:
        """
        Restore a previous session or initialize current state.
        Called when user returns after a break.
        
        Args:
            session_id: Optional specific session to restore
            
        Returns:
            Restored context with current state and suggestions
        """
        await self._notify_status("restoring_session", {"session_id": session_id})
        
        # Get planner restoration
        planner_state = self.planner_orchestrator.restore_session(session_id)
        
        # Check for any paused executor sessions
        executor_sessions = await sync_to_async(list)(
            AgentSession.objects.filter(
                project=self.project,
                user=self.user,
                status__in=['paused', 'active']
            ).order_by('-last_activity_at')[:5]
        )
        
        # Get recent memory context
        recent_memories = self.memory_service.get_recent_memories(limit=10)
        
        # Build restoration response
        restoration = {
            'type': 'session_restored',
            'project': {
                'id': str(self.project.id),
                'name': self.project.name
            },
            'planner_state': planner_state,
            'executor_sessions': [
                {
                    'id': str(s.id),
                    'name': s.session_name,
                    'status': s.status,
                    'goal': s.goal,
                    'last_activity': s.last_activity_at.isoformat()
                }
                for s in executor_sessions
            ],
            'recent_context': recent_memories,
            'suggested_action': None
        }
        
        # Determine best suggestion
        if planner_state.get('active_feature'):
            # Active feature exists
            feature = planner_state['active_feature']
            restoration['suggested_action'] = {
                'type': 'continue_feature',
                'message': f"Continue working on: {feature.get('name', 'current feature')}",
                'intent': MessageIntent.CONTINUATION.value
            }
        elif executor_sessions:
            # Paused executor session exists
            session = executor_sessions[0]
            restoration['suggested_action'] = {
                'type': 'resume_executor',
                'message': f"Resume: {session.session_name}",
                'session_id': str(session.id),
                'intent': MessageIntent.CONTROL.value
            }
        elif planner_state.get('resumable_features'):
            # Resumable features exist
            feature = planner_state['resumable_features'][0]
            restoration['suggested_action'] = {
                'type': 'resume_feature',
                'message': f"Resume feature: {feature.get('name')}",
                'feature_id': feature.get('id'),
                'intent': MessageIntent.CONTINUATION.value
            }
        else:
            restoration['suggested_action'] = {
                'type': 'start_new',
                'message': "What would you like to build?",
                'intent': MessageIntent.PLANNING.value
            }
        
        # Initialize session
        await self._initialize_session()
        
        return restoration
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status."""
        status = {
            'project_id': str(self.project.id),
            'has_session': self._session is not None,
            'planner_active': self._session.planner_active if self._session else False,
            'executor_active': self._session.executor_active if self._session else False,
            'awaiting_input': self._session.awaiting_response if self._session else False
        }
        
        if self._executor:
            executor_status = await self._executor.get_status()
            status['executor_status'] = executor_status
        
        return status
    
    # ==================== Intent Classification ====================
    
    async def _classify_intent(self, message: str) -> MessageIntent:
        """Classify the intent of a user message."""
        message_lower = message.lower()
        
        # Score each intent based on keyword matches
        scores = {}
        for intent, keywords in self._intent_keywords.items():
            score = sum(1 for kw in keywords if kw in message_lower)
            scores[intent] = score
        
        # Check for special patterns
        if message_lower.startswith(('pause', 'stop', 'resume', 'cancel')):
            return MessageIntent.CONTROL
        
        if message_lower.startswith(('what', 'how', 'why', 'show', 'list')):
            return MessageIntent.QUERY
        
        if message_lower in ('continue', 'next', 'go', 'proceed'):
            return MessageIntent.CONTINUATION
        
        # Use intent analyzer for more sophisticated classification
        try:
            intent_result = self.planner_orchestrator.intent_analyzer.analyze(
                message, 
                self._session.context if self._session else {}
            )
            
            # Map intent analyzer result to our intents
            intent_type = intent_result.intent_type.value
            if 'create' in intent_type or 'plan' in intent_type:
                return MessageIntent.PLANNING
            elif 'execute' in intent_type or 'implement' in intent_type:
                return MessageIntent.EXECUTION
            elif 'query' in intent_type or 'status' in intent_type:
                return MessageIntent.QUERY
        except Exception:
            pass
        
        # Default based on highest score
        if scores:
            best_intent = max(scores, key=scores.get)
            if scores[best_intent] > 0:
                return best_intent
        
        # Default to planning
        return MessageIntent.PLANNING
    
    # ==================== Message Handlers ====================
    
    async def _handle_planning_message(
        self,
        message: str,
        memory_context: Dict
    ) -> Dict[str, Any]:
        """Handle planning-related messages."""
        self._session.planner_active = True
        
        await self._notify_status("planning", {"message": message[:50]})
        
        # Process through planner orchestrator
        result = await sync_to_async(self.planner_orchestrator.process_message)(
            message,
            {
                **self._session.context,
                'memory': memory_context
            }
        )
        
        self._session.last_planner_result = result
        
        # Check if planner wants to delegate to executor
        if result.get('type') == 'delegate_to_executor':
            result['delegate_to_executor'] = True
        
        # Check if clarification needed
        if result.get('type') == 'clarification_needed':
            self._session.awaiting_response = True
            self._session.awaiting_type = 'planning_clarification'
            
            if self.on_user_input_needed:
                await self.on_user_input_needed({
                    'type': 'clarification',
                    'questions': result.get('questions', []),
                    'context': 'planning'
                })
        
        if self.on_planner_update:
            await self.on_planner_update(result)
        
        return result
    
    async def _handle_execution_message(
        self,
        message: str,
        memory_context: Dict
    ) -> Dict[str, Any]:
        """Handle execution-related messages."""
        self._session.executor_active = True
        
        await self._notify_status("preparing_execution", {"goal": message[:50]})
        
        # Get planning context for executor
        planning_context = self.planner_orchestrator.get_planning_context_for_executor()
        
        # Create or get agent session
        if not self._agent_session:
            self._agent_session = await sync_to_async(AgentSession.objects.create)(
                user=self.user,
                project=self.project,
                session_name=f"Execution: {message[:50]}",
                agent_type='executor',
                goal=message,
                context={
                    'planning_context': planning_context,
                    'memory_context': memory_context
                },
                status='active'
            )
        
        # Initialize executor if needed
        if not self._executor:
            self._executor = AutonomousExecutor(
                planning_service=self.planning_service,
                memory_service=self.memory_service,
                on_status_change=self._handle_executor_status,
                on_action_complete=self._handle_executor_action,
                on_user_input_needed=self._handle_executor_input_needed
            )
        
        # Start autonomous execution
        context = await self._executor.start(
            session_id=str(self._agent_session.id),
            project_id=str(self.project.id),
            user_id=str(self.user.id),
            initial_goal=message
        )
        
        return {
            'type': 'execution_started',
            'session_id': str(self._agent_session.id),
            'goal': message,
            'status': context.state.value,
            'message': f"Started autonomous execution for: {message}"
        }
    
    async def _handle_query_message(
        self,
        message: str,
        memory_context: Dict
    ) -> Dict[str, Any]:
        """Handle query/question messages."""
        await self._notify_status("querying", {"query": message[:50]})
        
        # Search memory for relevant information
        search_results = self.memory_service.search_memory(message, top_k=5)
        
        # Get current planning state
        planning_state = self.planner_orchestrator._get_current_planning_state()
        
        # Build response based on query type
        message_lower = message.lower()
        
        if 'status' in message_lower or 'progress' in message_lower:
            # Status query
            plan_summary = self.planning_service.get_plan_summary()
            return {
                'type': 'status_response',
                'plan_summary': plan_summary,
                'active_feature': planning_state.get('active_feature'),
                'executor_active': self._session.executor_active,
                'memory_context': search_results
            }
        
        elif 'what' in message_lower and 'next' in message_lower:
            # "What's next?" query
            suggestions = self.planning_service.get_next_suggested_features(limit=3)
            return {
                'type': 'suggestions_response',
                'suggestions': suggestions,
                'current_state': planning_state
            }
        
        else:
            # General query - use memory search
            return {
                'type': 'query_response',
                'query': message,
                'results': search_results,
                'context': memory_context
            }
    
    async def _handle_control_message(self, message: str) -> Dict[str, Any]:
        """Handle control messages (pause, resume, stop)."""
        await self._notify_status("processing_control", {"command": message})
        
        message_lower = message.lower()
        
        if 'pause' in message_lower:
            return await self._pause_execution()
        elif 'resume' in message_lower:
            return await self._resume_execution()
        elif 'stop' in message_lower or 'cancel' in message_lower:
            return await self._stop_execution()
        elif 'status' in message_lower:
            return await self.get_status()
            
        return {
            'success': False,
            'message': 'Unknown control command'
        }
    
    async def _handle_continuation(self, memory_context: Dict) -> Dict[str, Any]:
        """Handle continuation requests."""
        if self._session.awaiting_response:
            return await self._handle_clarification_response("continue")
            
        if self._session.planner_active:
            # Continue with planner's next suggestion
            planner_state = self.planner_orchestrator._get_current_planning_state()
            active_feature = planner_state.get('active_feature')
            
            if active_feature:
                # Find next task
                suggestion = self.planner_orchestrator.planning_service._suggest_next_action(
                    self.planner_orchestrator.planning_service.get_active_feature()
                )
                return await self.process_message(suggestion, self._session.context)
        
        if self._session.executor_active and self._executor:
            # Resume executor if paused
            return await self._resume_execution()
            
        return {
            'success': False,
            'message': "Nothing to continue. What would you like to do?"
        }
    
    async def _handle_clarification_response(self, message: str) -> Dict[str, Any]:
        """Handle user's response to a clarification request."""
        self._session.awaiting_response = False
        self._session.awaiting_type = None
        
        # Combine original intent context with new answer
        context = self._session.context
        context['user_clarification'] = message
        
        # Re-process with original intent but added context
        if self._session.planner_active:
            return await self._handle_planning_message(message, self._session.context)
        elif self._session.executor_active and self._executor:
            # Pass input to executor
            await self._executor.provide_user_input({'response': message})
            return {
                'type': 'input_received',
                'message': 'Input received, continuing execution.'
            }
            
        return await self.process_message(message, context)
    
    # ==================== Planner <-> Executor Handoff ====================
    
    async def _handoff_to_executor(self, planner_result: Dict) -> Dict[str, Any]:
        """
        Hand off work from planner to autonomous executor.
        
        Args:
            planner_result: Result from planner containing delegation details
            
        Returns:
            Status of handoff
        """
        await self._notify_status("handoff", {"target": "executor"})
        
        planning_context = planner_result.get('planning_context', {})
        entities = planner_result.get('entities', {})
        
        # Determine the goal
        goal = planner_result.get('suggested_action', '')
        if not goal and entities:
            if 'feature_name' in entities:
                goal = f"Implement feature: {entities['feature_name']}"
            elif 'task_description' in entities:
                goal = entities['task_description']
        
        if not goal:
            goal = "Execute pending tasks"
            
        # Initialize execution session
        return await self._handle_execution_message(goal, planning_context)
    
    async def _report_execution_complete(
        self,
        task_id: str,
        result: Dict
    ) -> Dict[str, Any]:
        """Report task completion back to planner."""
        # Update planner state
        planner_update = self.planner_orchestrator.report_task_completion(task_id, result)
        
        # Notify user
        if self.on_status_update:
            await self.on_status_update({
                'type': 'task_completed',
                'task_id': task_id,
                'result': result,
                'next_step': planner_update.get('suggestion')
            })
            
        return planner_update
    
    async def _report_execution_failure(
        self,
        task_id: str,
        error: str
    ) -> Dict[str, Any]:
        """Report task failure back to planner."""
        planner_update = self.planner_orchestrator.report_task_failure(task_id, error)
        
        if self.on_status_update:
            await self.on_status_update({
                'type': 'task_failed',
                'task_id': task_id,
                'error': error,
                'suggestion': planner_update.get('suggestion')
            })
            
        return planner_update
    
    # ==================== Executor Control ====================
    
    async def _pause_execution(self) -> Dict[str, Any]:
        """Pause current execution."""
        if self._executor:
            context = await self._executor.pause()
            
            # Persist state
            await self._persist_checkpoint(context)
            
            # Update session status
            if self._agent_session:
                self._agent_session.status = 'paused'
                await sync_to_async(self._agent_session.save)()
            
            return {
                'type': 'execution_paused',
                'message': 'Execution paused. You can resume later.'
            }
        return {'success': False, 'message': 'No active execution to pause'}
    
    async def _resume_execution(self) -> Dict[str, Any]:
        """Resume paused execution."""
        if not self._agent_session:
            # Try to find last paused session
            last_session = await sync_to_async(AgentSession.objects.filter(
                project=self.project,
                user=self.user,
                status='paused'
            ).order_by('-last_activity_at').first)()
            
            if last_session:
                self._agent_session = last_session
            else:
                return {'success': False, 'message': 'No paused session to resume'}
        
        # Initialize executor if needed
        if not self._executor:
            self._executor = AutonomousExecutor(
                planning_service=self.planning_service,
                memory_service=self.memory_service,
                on_status_change=self._handle_executor_status,
                on_action_complete=self._handle_executor_action,
                on_user_input_needed=self._handle_executor_input_needed
            )
        
        # Load checkpoint
        checkpoint = await self._load_checkpoint(self._agent_session)
        
        if checkpoint:
            # Resume from checkpoint
            await self._executor.resume_from_checkpoint(
                checkpoint, 
                self.planning_service,
                self.memory_service
            )
        else:
            # Restart
            await self._executor.start(
                str(self._agent_session.id),
                str(self.project.id),
                str(self.user.id),
                self._agent_session.goal
            )
            
        self._agent_session.status = 'active'
        await sync_to_async(self._agent_session.save)()
        
        return {
            'type': 'execution_resumed',
            'session_id': str(self._agent_session.id),
            'goal': self._agent_session.goal
        }
    
    async def _stop_execution(self) -> Dict[str, Any]:
        """Stop current execution permanently."""
        if self._executor:
            await self._executor.stop()
            
        if self._agent_session:
            self._agent_session.status = 'cancelled'
            await sync_to_async(self._agent_session.save)()
            
            self._session.executor_active = False
            self._agent_session = None
            self._executor = None
            
        return {
            'type': 'execution_stopped',
            'message': 'Execution stopped.'
        }
    
    # ==================== Executor Callbacks ====================
    
    async def _handle_executor_status(self, status: Dict[str, Any]):
        """Handle status updates from executor."""
        # Forward to UI
        if self.on_executor_update:
            await self.on_executor_update(status)
            
        # Update DB session
        if self._agent_session:
            self._agent_session.update_activity()
    
    async def _handle_executor_action(self, action: Dict[str, Any]):
        """Handle completed action from executor."""
        if self.on_executor_update:
            await self.on_executor_update({
                'type': 'action_completed',
                'action': action
            })
            
        # Check if we should report to planner
        if action.get('type') == 'task_completion':
            # Link tasks between planner and executor
            pass
    
    async def _handle_executor_input_needed(self, request: Dict[str, Any]):
        """Handle input request from executor."""
        self._session.awaiting_response = True
        self._session.awaiting_type = 'executor_input'
        
        if self.on_user_input_needed:
            await self.on_user_input_needed(request)
    
    # ==================== Session & Checkpoint Management ====================
    
    async def _initialize_session(self):
        """Initialize orchestrator session."""
        session_id = str(uuid4())
        
        self._session = OrchestratorSession(
            session_id=session_id,
            project_id=str(self.project.id),
            user_id=str(self.user.id)
        )
        
        # Check for active agent session in DB
        active_session = await sync_to_async(AgentSession.objects.filter(
            project=self.project,
            user=self.user,
            status='active'
        ).first)()
        
        if active_session:
            self._agent_session = active_session
            self._session.executor_active = True
            
            # Rehydrate executor
            if not self._executor:
                self._executor = AutonomousExecutor(
                    planning_service=self.planning_service,
                    memory_service=self.memory_service,
                    on_status_change=self._handle_executor_status,
                    on_action_complete=self._handle_executor_action,
                    on_user_input_needed=self._handle_executor_input_needed
                )
    
    async def _persist_checkpoint(self, context: ExecutionContext):
        """Persist execution state to database."""
        if not self._agent_session:
            return
            
        # Convert context to serializable dict
        from apps.agents.models import AgentCheckpoint
        
        checkpoint_data = {
            'iteration': context.iteration,
            'state': context.state.value,
            'current_goal': context.current_goal or '',
            'completed_actions': [a.action_id for a in context.completed_actions],
            'pending_actions': [a.action_id for a in context.pending_actions],
            'context_snapshot': {
                'iteration': context.iteration,
                'state': context.state.value,
                'stats': {
                    'actions_completed': len(context.completed_actions),
                    'actions_failed': len(context.failed_actions)
                }
            },
            'memory_snapshot': context.memory_context
        }
        
        await sync_to_async(AgentCheckpoint.objects.create)(
            session=self._agent_session,
            **checkpoint_data
        )
        
        # Update session pointer
        self._agent_session.checkpoint_id = str(context.iteration)
        await sync_to_async(self._agent_session.save)()
    
    async def _load_checkpoint(self, session: AgentSession) -> Optional[ExecutionCheckpoint]:
        """Load latest checkpoint from database."""
        from apps.agents.models import AgentCheckpoint
        
        checkpoint_model = await sync_to_async(
            lambda: AgentCheckpoint.objects.filter(session=session).order_by('-created_at').first()
        )()
        
        if not checkpoint_model:
            return None
            
        return ExecutionCheckpoint(
            checkpoint_id=str(checkpoint_model.id),
            iteration=checkpoint_model.iteration,
            state=ExecutionState(checkpoint_model.state),
            current_goal=checkpoint_model.current_goal,
            completed_actions=checkpoint_model.completed_actions,
            pending_actions=checkpoint_model.pending_actions,
            context_snapshot=checkpoint_model.context_snapshot
        )
    
    # ==================== Memory Integration ====================
    
    async def _get_memory_context(self, message: str) -> Dict[str, Any]:
        """Get relevant memory context."""
        # Search for related memories
        results = await sync_to_async(self.memory_service.search_memory)(message, top_k=5)
        
        # Get active project context
        project_context = {
            'name': self.project.name,
            'description': self.project.description
        }
        
        return {
            'search_results': results,
            'project': project_context,
            'timestamp': timezone.now().isoformat()
        }

    async def _notify_status(self, status_type: str, data: Dict[str, Any]):
        """Helper to send status updates."""
        if self.on_status_update:
            await self.on_status_update({
                'type': status_type,
                **data
            })
