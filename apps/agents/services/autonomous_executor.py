"""
Autonomous Executor - Self-directed agent execution engine.
Enables agents to work autonomously on tasks without constant user prompting.
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

from django.utils import timezone

logger = logging.getLogger(__name__)


class ExecutionState(Enum):
    """States for autonomous execution."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_INPUT = "waiting_input"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class ActionType(Enum):
    """Types of autonomous actions."""
    ANALYZE = "analyze"
    PLAN = "plan"
    RESEARCH = "research"
    GENERATE_CODE = "generate_code"
    REFACTOR = "refactor"
    TEST = "test"
    DEBUG = "debug"
    DOCUMENT = "document"
    REVIEW = "review"
    DEPLOY = "deploy"
    COMMUNICATE = "communicate"


@dataclass
class AutonomousAction:
    """Represents a single autonomous action."""
    action_id: str
    action_type: ActionType
    description: str
    priority: int = 5  # 1-10, higher = more important
    requires_confirmation: bool = False
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    status: str = "pending"  # pending, running, completed, failed, skipped
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class ExecutionCheckpoint:
    """Checkpoint for resumable execution."""
    checkpoint_id: str
    iteration: int
    state: ExecutionState
    current_goal: str
    completed_actions: List[str]
    pending_actions: List[str]
    context_snapshot: Dict[str, Any]
    created_at: datetime = field(default_factory=timezone.now)


@dataclass
class ExecutionContext:
    """Context for autonomous execution."""
    session_id: str
    project_id: str
    user_id: str
    state: ExecutionState = ExecutionState.IDLE
    current_goal: Optional[str] = None
    current_plan: Optional[Dict[str, Any]] = None
    iteration: int = 0
    max_iterations: int = 100
    pending_actions: List[AutonomousAction] = field(default_factory=list)
    completed_actions: List[AutonomousAction] = field(default_factory=list)
    failed_actions: List[AutonomousAction] = field(default_factory=list)
    checkpoints: List[ExecutionCheckpoint] = field(default_factory=list)
    memory_context: Dict[str, Any] = field(default_factory=dict)
    waiting_for: Optional[Dict[str, Any]] = None  # What we're waiting for from user
    pause_reason: Optional[str] = None
    stop_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None


class AutonomousExecutor:
    """
    Executes agent tasks autonomously with self-direction capabilities.
    
    Features:
    - Self-directed planning and execution
    - Automatic decision making based on context
    - Pause/resume with checkpoints
    - User intervention points
    - Progress tracking and reporting
    """
    
    def __init__(
        self,
        planning_service,
        memory_service,
        code_executor=None,
        on_status_change: Callable[[Dict[str, Any]], Awaitable[None]] = None,
        on_action_complete: Callable[[Dict[str, Any]], Awaitable[None]] = None,
        on_user_input_needed: Callable[[Dict[str, Any]], Awaitable[None]] = None
    ):
        self.planning_service = planning_service
        self.memory_service = memory_service
        self.code_executor = code_executor
        
        # Callbacks for real-time updates
        self.on_status_change = on_status_change
        self.on_action_complete = on_action_complete
        self.on_user_input_needed = on_user_input_needed
        
        # Execution state
        self._context: Optional[ExecutionContext] = None
        self._running = False
        self._user_response_event = asyncio.Event()
        self._user_response: Optional[Dict[str, Any]] = None
        
        # Configuration
        self.config = {
            'max_iterations': 100,
            'checkpoint_interval': 10,
            'action_timeout': 300,  # seconds
            'require_confirmation_for': [ActionType.DEPLOY, ActionType.REFACTOR],
            'auto_retry_on_failure': True,
            'max_retries': 3
        }
    
    # ==================== Main Execution Loop ====================
    
    async def start(
        self,
        session_id: str,
        project_id: str,
        user_id: str,
        initial_goal: str = None
    ) -> ExecutionContext:
        """Start autonomous execution."""
        self._context = ExecutionContext(
            session_id=session_id,
            project_id=project_id,
            user_id=user_id,
            current_goal=initial_goal,
            started_at=timezone.now(),
            max_iterations=self.config['max_iterations']
        )
        
        self._running = True
        await self._notify_status_change("started", {"goal": initial_goal})
        
        # Start the execution loop in background
        asyncio.create_task(self._execution_loop())
        
        return self._context
    
    async def _execution_loop(self):
        """Main autonomous execution loop."""
        try:
            while self._running and self._context.iteration < self._context.max_iterations:
                self._context.iteration += 1
                self._context.last_activity = timezone.now()
                
                # Check for pause
                if self._context.state == ExecutionState.PAUSED:
                    await asyncio.sleep(1)
                    continue
                
                # Phase 1: Assess current situation
                await self._assess_situation()
                
                # Phase 2: Plan next actions if needed
                if not self._context.pending_actions:
                    if await self._should_continue():
                        await self._plan_next_actions()
                    else:
                        # Goal achieved or no more work
                        await self._complete_execution("Goal achieved")
                        break
                
                # Phase 3: Execute next action
                if self._context.pending_actions:
                    await self._execute_next_action()
                
                # Phase 4: Create checkpoint if needed
                if self._context.iteration % self.config['checkpoint_interval'] == 0:
                    await self._create_checkpoint()
                
                # Small delay to prevent tight loops
                await asyncio.sleep(0.5)
            
            # Max iterations reached
            if self._context.iteration >= self._context.max_iterations:
                await self._complete_execution("Max iterations reached")
                
        except Exception as e:
            logger.error(f"Execution loop error: {e}")
            await self._fail_execution(str(e))
    
    async def _assess_situation(self):
        """Assess current situation and update context."""
        self._context.state = ExecutionState.PLANNING
        
        # Load recent memory context
        try:
            memories = await self._get_relevant_memories()
            self._context.memory_context = {
                'recent_actions': memories.get('actions', []),
                'learned_patterns': memories.get('patterns', []),
                'project_context': memories.get('project', {})
            }
        except Exception as e:
            logger.warning(f"Could not load memories: {e}")
    
    async def _should_continue(self) -> bool:
        """Determine if execution should continue."""
        # Check if we have a goal
        if not self._context.current_goal:
            return False
        
        # Check completed actions against goal
        if len(self._context.completed_actions) > 0:
            # Ask the planning service if goal is met
            try:
                assessment = await self._assess_goal_completion()
                return not assessment.get('goal_complete', False)
            except Exception:
                # Continue if assessment fails
                return True
        
        return True
    
    async def _plan_next_actions(self):
        """Plan the next set of actions to take."""
        await self._notify_status_change("planning", {
            "iteration": self._context.iteration
        })
        
        try:
            # Get current plan or create new one
            if not self._context.current_plan:
                plan = await self._create_initial_plan()
                self._context.current_plan = plan
            
            # Convert plan tasks to actions
            tasks = self._context.current_plan.get('tasks', [])
            completed_ids = [a.action_id for a in self._context.completed_actions]
            
            for task in tasks:
                task_id = task.get('id', str(uuid4()))
                if task_id not in completed_ids:
                    action = self._task_to_action(task)
                    self._context.pending_actions.append(action)
            
            # Sort by priority
            self._context.pending_actions.sort(key=lambda a: -a.priority)
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            # Create a basic analysis action as fallback
            self._context.pending_actions.append(AutonomousAction(
                action_id=str(uuid4()),
                action_type=ActionType.ANALYZE,
                description=f"Analyze how to: {self._context.current_goal}",
                priority=10
            ))
    
    async def _execute_next_action(self):
        """Execute the next pending action."""
        if not self._context.pending_actions:
            return
        
        action = self._context.pending_actions.pop(0)
        action.status = "running"
        action.started_at = timezone.now()
        
        self._context.state = ExecutionState.EXECUTING
        await self._notify_status_change("executing_action", {
            "action_id": action.action_id,
            "action_type": action.action_type.value,
            "description": action.description
        })
        
        # Check if confirmation required
        if action.requires_confirmation or action.action_type in self.config['require_confirmation_for']:
            approved = await self._request_confirmation(action)
            if not approved:
                action.status = "skipped"
                action.completed_at = timezone.now()
                self._context.completed_actions.append(action)
                return
        
        # Execute the action
        try:
            result = await self._execute_action(action)
            action.output_data = result
            action.status = "completed"
            action.completed_at = timezone.now()
            self._context.completed_actions.append(action)
            
            # Store in memory
            await self._store_action_memory(action)
            
            # Notify completion
            await self._notify_action_complete(action)
            
        except Exception as e:
            action.status = "failed"
            action.error = str(e)
            action.completed_at = timezone.now()
            self._context.failed_actions.append(action)
            
            # Retry logic
            if self.config['auto_retry_on_failure']:
                retry_count = action.input_data.get('_retry_count', 0)
                if retry_count < self.config['max_retries']:
                    action.input_data['_retry_count'] = retry_count + 1
                    action.status = "pending"
                    self._context.pending_actions.insert(0, action)
                    logger.info(f"Retrying action {action.action_id}, attempt {retry_count + 1}")
    
    async def _execute_action(self, action: AutonomousAction) -> Dict[str, Any]:
        """Execute a specific action type."""
        action_handlers = {
            ActionType.ANALYZE: self._handle_analyze,
            ActionType.PLAN: self._handle_plan,
            ActionType.RESEARCH: self._handle_research,
            ActionType.GENERATE_CODE: self._handle_generate_code,
            ActionType.REFACTOR: self._handle_refactor,
            ActionType.TEST: self._handle_test,
            ActionType.DEBUG: self._handle_debug,
            ActionType.DOCUMENT: self._handle_document,
            ActionType.REVIEW: self._handle_review,
            ActionType.COMMUNICATE: self._handle_communicate,
        }
        
        handler = action_handlers.get(action.action_type, self._handle_generic)
        return await handler(action)
    
    # ==================== Action Handlers ====================
    
    async def _handle_analyze(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle analysis action."""
        # Use planning service to analyze
        context = action.input_data.get('context', {})
        context['goal'] = self._context.current_goal
        context['completed_actions'] = [a.description for a in self._context.completed_actions[-5:]]
        
        analysis = await asyncio.to_thread(
            self.planning_service.analyze_codebase,
            self._context.project_id,
            action.description
        )
        
        return {'analysis': analysis}
    
    async def _handle_plan(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle planning action."""
        plan = await self._create_initial_plan()
        self._context.current_plan = plan
        return {'plan': plan}
    
    async def _handle_research(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle research action."""
        # Query memory for relevant information
        query = action.input_data.get('query', action.description)
        
        memories = await asyncio.to_thread(
            self.memory_service.search,
            query=query,
            project_id=self._context.project_id,
            limit=10
        )
        
        return {'research_results': memories}
    
    async def _handle_generate_code(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle code generation action."""
        if not self.code_executor:
            return {'error': 'Code executor not available'}
        
        spec = action.input_data.get('specification', action.description)
        
        # Generate code using planning service
        code_result = await asyncio.to_thread(
            self.planning_service.generate_code_for_task,
            task_description=spec,
            project_id=self._context.project_id
        )
        
        return {'code': code_result}
    
    async def _handle_refactor(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle refactoring action."""
        target = action.input_data.get('target', '')
        refactor_type = action.input_data.get('refactor_type', 'improve')
        
        result = await asyncio.to_thread(
            self.planning_service.suggest_refactoring,
            project_id=self._context.project_id,
            target=target,
            refactor_type=refactor_type
        )
        
        return {'refactoring': result}
    
    async def _handle_test(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle testing action."""
        if not self.code_executor:
            return {'error': 'Code executor not available'}
        
        test_command = action.input_data.get('command', 'pytest')
        
        result = await asyncio.to_thread(
            self.code_executor.run_tests,
            command=test_command,
            project_id=self._context.project_id
        )
        
        return {'test_results': result}
    
    async def _handle_debug(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle debugging action."""
        error_info = action.input_data.get('error', '')
        
        analysis = await asyncio.to_thread(
            self.planning_service.analyze_error,
            error=error_info,
            project_id=self._context.project_id
        )
        
        return {'debug_analysis': analysis}
    
    async def _handle_document(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle documentation action."""
        target = action.input_data.get('target', '')
        
        docs = await asyncio.to_thread(
            self.planning_service.generate_documentation,
            target=target,
            project_id=self._context.project_id
        )
        
        return {'documentation': docs}
    
    async def _handle_review(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle code review action."""
        code = action.input_data.get('code', '')
        
        review = await asyncio.to_thread(
            self.planning_service.review_code,
            code=code,
            project_id=self._context.project_id
        )
        
        return {'review': review}
    
    async def _handle_communicate(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle communication action - asks user a question."""
        question = action.input_data.get('question', action.description)
        
        response = await self._request_user_input({
            'type': 'question',
            'question': question,
            'action_id': action.action_id
        })
        
        return {'user_response': response}
    
    async def _handle_generic(self, action: AutonomousAction) -> Dict[str, Any]:
        """Handle generic/unknown action types."""
        return {
            'status': 'completed',
            'message': f'Completed: {action.description}'
        }
    
    # ==================== User Interaction ====================
    
    async def _request_confirmation(self, action: AutonomousAction) -> bool:
        """Request user confirmation for an action."""
        self._context.state = ExecutionState.WAITING_INPUT
        self._context.waiting_for = {
            'type': 'confirmation',
            'action_id': action.action_id,
            'action': {
                'type': action.action_type.value,
                'description': action.description
            }
        }
        
        if self.on_user_input_needed:
            await self.on_user_input_needed(self._context.waiting_for)
        
        # Wait for response
        response = await self._wait_for_user_response()
        
        self._context.state = ExecutionState.EXECUTING
        self._context.waiting_for = None
        
        return response.get('approved', False)
    
    async def _request_user_input(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Request arbitrary input from user."""
        self._context.state = ExecutionState.WAITING_INPUT
        self._context.waiting_for = request
        
        if self.on_user_input_needed:
            await self.on_user_input_needed(request)
        
        response = await self._wait_for_user_response()
        
        self._context.state = ExecutionState.EXECUTING
        self._context.waiting_for = None
        
        return response
    
    async def _wait_for_user_response(self, timeout: int = 300) -> Dict[str, Any]:
        """Wait for user to provide a response."""
        self._user_response_event.clear()
        self._user_response = None
        
        try:
            await asyncio.wait_for(
                self._user_response_event.wait(),
                timeout=timeout
            )
            return self._user_response or {}
        except asyncio.TimeoutError:
            return {'timeout': True}
    
    async def provide_user_input(self, response: Dict[str, Any]):
        """Provide user input to waiting executor."""
        self._user_response = response
        self._user_response_event.set()
    
    # ==================== Control Methods ====================
    
    async def resume_from_checkpoint(
        self,
        checkpoint: ExecutionCheckpoint,
        planning_service,
        memory_service
    ) -> ExecutionContext:
        """
        Resume execution from a checkpoint.
        
        Args:
            checkpoint: The checkpoint to resume from
            planning_service: Planning service instance
            memory_service: Memory service instance
            
        Returns:
            Restored ExecutionContext
        """
        # Restore context from checkpoint
        self._context = ExecutionContext(
            session_id=checkpoint.context_snapshot.get('session_id', str(uuid4())),
            project_id=checkpoint.context_snapshot.get('project_id', ''),
            user_id=checkpoint.context_snapshot.get('user_id', ''),
            state=ExecutionState.PAUSED,
            current_goal=checkpoint.current_goal,
            current_plan=checkpoint.context_snapshot.get('plan'),
            iteration=checkpoint.iteration,
            memory_context=checkpoint.context_snapshot.get('memory_context', {}),
            started_at=timezone.now()
        )
        
        # Restore services
        self.planning_service = planning_service
        self.memory_service = memory_service
        
        # Mark as ready to resume
        self._running = False
        
        await self._notify_status_change("restored_from_checkpoint", {
            "checkpoint_id": checkpoint.checkpoint_id,
            "iteration": checkpoint.iteration,
            "goal": checkpoint.current_goal
        })
        
        return self._context
    
    async def pause(self, reason: str = "User requested") -> ExecutionContext:
        """Pause execution."""
        self._context.state = ExecutionState.PAUSED
        self._context.pause_reason = reason
        
        await self._create_checkpoint()
        await self._notify_status_change("paused", {"reason": reason})
        
        return self._context
    
    async def resume(self) -> ExecutionContext:
        """Resume paused execution.""" 
        if self._context.state != ExecutionState.PAUSED:
            raise ValueError("Cannot resume - not paused")
        
        self._context.state = ExecutionState.EXECUTING
        self._context.pause_reason = None
        
        await self._notify_status_change("resumed", {})
        
        return self._context
    
    async def stop(self, reason: str = "User requested") -> ExecutionContext:
        """Stop execution completely."""
        self._running = False
        self._context.state = ExecutionState.STOPPED
        self._context.stop_reason = reason
        
        await self._create_checkpoint()
        await self._notify_status_change("stopped", {"reason": reason})
        
        return self._context
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current execution status."""
        if not self._context:
            return {'state': 'not_started'}
        
        return {
            'session_id': self._context.session_id,
            'state': self._context.state.value,
            'iteration': self._context.iteration,
            'current_goal': self._context.current_goal,
            'pending_actions': len(self._context.pending_actions),
            'completed_actions': len(self._context.completed_actions),
            'failed_actions': len(self._context.failed_actions),
            'waiting_for': self._context.waiting_for,
            'last_activity': self._context.last_activity.isoformat() if self._context.last_activity else None,
            'checkpoints': len(self._context.checkpoints)
        }
    
    # ==================== Helper Methods ====================
    
    async def _create_initial_plan(self) -> Dict[str, Any]:
        """Create initial execution plan."""
        plan = await asyncio.to_thread(
            self.planning_service.create_plan,
            goal=self._context.current_goal,
            project_id=self._context.project_id,
            context=self._context.memory_context
        )
        return plan
    
    async def _assess_goal_completion(self) -> Dict[str, Any]:
        """Assess if the current goal has been completed."""
        completed_descriptions = [a.description for a in self._context.completed_actions]
        
        assessment = await asyncio.to_thread(
            self.planning_service.assess_completion,
            goal=self._context.current_goal,
            completed_actions=completed_descriptions,
            project_id=self._context.project_id
        )
        return assessment
    
    async def _get_relevant_memories(self) -> Dict[str, Any]:
        """Get relevant memories for context."""
        memories = await asyncio.to_thread(
            self.memory_service.get_context,
            project_id=self._context.project_id,
            query=self._context.current_goal or "",
            limit=20
        )
        return memories
    
    async def _store_action_memory(self, action: AutonomousAction):
        """Store completed action in memory."""
        try:
            await asyncio.to_thread(
                self.memory_service.store,
                content={
                    'type': 'autonomous_action',
                    'action_type': action.action_type.value,
                    'description': action.description,
                    'result': action.output_data,
                    'goal': self._context.current_goal
                },
                project_id=self._context.project_id,
                metadata={
                    'session_id': self._context.session_id,
                    'iteration': self._context.iteration
                }
            )
        except Exception as e:
            logger.warning(f"Could not store action memory: {e}")
    
    def _task_to_action(self, task: Dict[str, Any]) -> AutonomousAction:
        """Convert a plan task to an action."""
        action_type_map = {
            'analyze': ActionType.ANALYZE,
            'plan': ActionType.PLAN,
            'research': ActionType.RESEARCH,
            'code': ActionType.GENERATE_CODE,
            'generate': ActionType.GENERATE_CODE,
            'refactor': ActionType.REFACTOR,
            'test': ActionType.TEST,
            'debug': ActionType.DEBUG,
            'document': ActionType.DOCUMENT,
            'review': ActionType.REVIEW,
            'deploy': ActionType.DEPLOY,
            'ask': ActionType.COMMUNICATE,
        }
        
        task_type = task.get('type', 'analyze').lower()
        action_type = action_type_map.get(task_type, ActionType.ANALYZE)
        
        return AutonomousAction(
            action_id=task.get('id', str(uuid4())),
            action_type=action_type,
            description=task.get('description', task.get('title', '')),
            priority=task.get('priority', 5),
            requires_confirmation=task.get('requires_confirmation', False),
            input_data=task.get('input', {})
        )
    
    async def _create_checkpoint(self):
        """Create execution checkpoint."""
        checkpoint = ExecutionCheckpoint(
            checkpoint_id=str(uuid4()),
            iteration=self._context.iteration,
            state=self._context.state,
            current_goal=self._context.current_goal or "",
            completed_actions=[a.action_id for a in self._context.completed_actions],
            pending_actions=[a.action_id for a in self._context.pending_actions],
            context_snapshot={
                'memory_context': self._context.memory_context,
                'plan': self._context.current_plan
            }
        )
        
        self._context.checkpoints.append(checkpoint)
        
        await self._notify_status_change("checkpoint_created", {
            "checkpoint_id": checkpoint.checkpoint_id,
            "iteration": checkpoint.iteration
        })
    
    async def _complete_execution(self, reason: str):
        """Mark execution as completed."""
        self._running = False
        self._context.state = ExecutionState.COMPLETED
        
        await self._create_checkpoint()
        await self._notify_status_change("completed", {
            "reason": reason,
            "total_actions": len(self._context.completed_actions),
            "failed_actions": len(self._context.failed_actions)
        })
    
    async def _fail_execution(self, error: str):
        """Mark execution as failed."""
        self._running = False
        self._context.state = ExecutionState.FAILED
        
        await self._create_checkpoint()
        await self._notify_status_change("failed", {"error": error})
    
    async def _notify_status_change(self, event: str, details: Dict[str, Any]):
        """Notify about status change."""
        if self.on_status_change:
            await self.on_status_change({
                'event': event,
                'state': self._context.state.value if self._context else 'unknown',
                'timestamp': timezone.now().isoformat(),
                'details': details
            })
    
    async def _notify_action_complete(self, action: AutonomousAction):
        """Notify about action completion."""
        if self.on_action_complete:
            await self.on_action_complete({
                'action_id': action.action_id,
                'action_type': action.action_type.value,
                'description': action.description,
                'result': action.output_data,
                'iteration': self._context.iteration
            })
