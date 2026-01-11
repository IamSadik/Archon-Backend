"""
Planner Orchestrator - Coordinates the planning flow between user, memory, and execution.
This is the main entry point for planning operations.
"""
from typing import Dict, Any, List, Optional
from django.utils import timezone
from apps.planning.services.planning_service import PlanningService
from apps.planning.services.intent_analyzer import IntentAnalyzerService, IntentType
from apps.memory.services import MemoryService
from apps.projects.models import Project


class PlannerOrchestrator:
    """
    Main orchestrator that coordinates:
    - Intent analysis
    - Planning operations
    - Memory integration
    - Context restoration
    - Executor delegation
    
    This is the "brain" interface that the chat system uses.
    """
    
    def __init__(self, user, project: Project):
        """
        Initialize the planner orchestrator.
        
        Args:
            user: User instance
            project: Project to manage
        """
        self.user = user
        self.project = project
        self.planning_service = PlanningService(user, project)
        self.intent_analyzer = IntentAnalyzerService(user, project)
        self.memory_service = MemoryService(user, project)
    
    def process_message(self, message: str, session_context: Dict = None) -> Dict[str, Any]:
        """
        Process a user message through the planning system.
        
        This is the main entry point for all user interactions.
        
        Args:
            message: User's message
            session_context: Current session context (active feature, history, etc.)
            
        Returns:
            Response with planning actions taken and next steps
        """
        session_context = session_context or {}
        
        # Step 1: Retrieve relevant context from memory
        memory_context = self._retrieve_memory_context(message)
        
        # Step 2: Get current planning state
        planning_state = self._get_current_planning_state()
        
        # Merge contexts
        full_context = {
            **session_context,
            'memory': memory_context,
            'planning': planning_state
        }
        
        # Step 3: Analyze intent
        intent_result = self.intent_analyzer.analyze(message, full_context)
        
        # Step 4: Check if clarification needed
        if intent_result.requires_confirmation:
            return self._request_clarification(intent_result)
        
        # Step 5: Execute planning action or delegate to executor
        action_mapping = self.intent_analyzer.map_intent_to_planning_action(intent_result)
        
        if action_mapping.get('delegate_to') == 'executor':
            # This is a code/execution task - delegate to agent executor
            return self._delegate_to_executor(intent_result, full_context)
        
        # Step 6: Execute planning action
        result = self._execute_planning_action(action_mapping, intent_result)
        
        # Step 7: Update memory with action taken
        self._persist_action_to_memory(intent_result, result)
        
        # Step 8: Build response
        return self._build_response(intent_result, result, planning_state)
    
    def restore_session(self, session_id: str = None) -> Dict[str, Any]:
        """
        Restore a previous session or get current state.
        Called when user returns after a break.
        
        Args:
            session_id: Optional specific session to restore
            
        Returns:
            Restored context with suggested next actions
        """
        # Get active feature
        active_feature = self.planning_service.get_active_feature()
        
        # Get resumable features
        resumable = self.planning_service.get_resumable_features()
        
        # Get plan summary
        plan_summary = self.planning_service.get_plan_summary()
        
        # Get recent memory context
        recent_context = self._get_recent_session_context()
        
        # Build restoration response
        restoration = {
            'restored': True,
            'project': {
                'id': str(self.project.id),
                'name': self.project.name
            },
            'plan_summary': plan_summary,
            'active_feature': None,
            'resumable_features': resumable,
            'recent_context': recent_context,
            'suggested_action': None
        }
        
        if active_feature:
            # There's an active feature - suggest continuing
            feature_context = self.planning_service._feature_to_tree(active_feature)
            next_action = self.planning_service._suggest_next_action(active_feature)
            
            restoration['active_feature'] = feature_context
            restoration['suggested_action'] = {
                'type': 'continue',
                'message': f"Continue working on: {active_feature.name}",
                'next_step': next_action
            }
        elif resumable:
            # Suggest resuming most recent paused feature
            most_recent = resumable[0]
            restoration['suggested_action'] = {
                'type': 'resume',
                'message': f"Resume work on: {most_recent['name']}",
                'feature_id': most_recent['id']
            }
        else:
            # Suggest starting a new feature
            suggestions = self.planning_service.get_next_suggested_features(limit=3)
            if suggestions:
                restoration['suggested_action'] = {
                    'type': 'start',
                    'message': "Start one of these features:",
                    'options': suggestions
                }
            else:
                restoration['suggested_action'] = {
                    'type': 'create',
                    'message': "No features yet. What would you like to build?"
                }
        
        return restoration
    
    def get_planning_context_for_executor(self) -> Dict[str, Any]:
        """
        Get planning context to pass to the executor agent.
        
        Returns:
            Context dictionary for code execution
        """
        active_feature = self.planning_service.get_active_feature()
        
        context = {
            'project_id': str(self.project.id),
            'project_name': self.project.name,
            'active_feature': None,
            'related_files': [],
            'architectural_decisions': [],
            'constraints': []
        }
        
        if active_feature:
            context['active_feature'] = {
                'id': str(active_feature.id),
                'name': active_feature.name,
                'description': active_feature.description,
                'status': active_feature.status
            }
            context['related_files'] = active_feature.related_files
            
            # Get pending tasks
            pending_tasks = active_feature.tasks.filter(status='pending')
            context['pending_tasks'] = [
                {'id': str(t.id), 'title': t.title, 'type': t.task_type}
                for t in pending_tasks
            ]
        
        # Get architectural decisions from memory
        arch_decisions = self.memory_service.get_memories_by_category(
            'architectural_decision', limit=10
        )
        context['architectural_decisions'] = arch_decisions
        
        # Get constraints
        constraints = self.memory_service.get_memories_by_category(
            'constraint', limit=5
        )
        context['constraints'] = constraints
        
        return context
    
    def report_task_completion(self, task_id: str, result: Dict = None) -> Dict[str, Any]:
        """
        Called by executor when a task is completed.
        Updates planning state and suggests next action.
        
        Args:
            task_id: Completed task ID
            result: Task result
            
        Returns:
            Updated state and next suggestion
        """
        task = self.planning_service.complete_task(task_id, result)
        feature = task.feature
        
        # Check if all tasks in feature are done
        pending = feature.tasks.filter(status='pending').count()
        
        if pending == 0:
            # All tasks done - suggest completing feature
            return {
                'task_completed': True,
                'feature_status': 'all_tasks_done',
                'suggestion': {
                    'type': 'complete_feature',
                    'message': f"All tasks complete. Mark '{feature.name}' as done?",
                    'feature_id': str(feature.id)
                }
            }
        else:
            # More tasks remaining
            next_task = feature.tasks.filter(status='pending').first()
            return {
                'task_completed': True,
                'feature_status': 'in_progress',
                'remaining_tasks': pending,
                'suggestion': {
                    'type': 'continue',
                    'message': f"Next task: {next_task.title}",
                    'task_id': str(next_task.id)
                }
            }
    
    def report_task_failure(self, task_id: str, error: str) -> Dict[str, Any]:
        """
        Called by executor when a task fails.
        
        Args:
            task_id: Failed task ID
            error: Error message
            
        Returns:
            Failure response with suggestions
        """
        task = self.planning_service.fail_task(task_id, error)
        
        # Store failure in memory for learning
        self.memory_service.store_long_term(
            key=f"task_failure_{task_id}",
            content={
                'task_title': task.title,
                'feature': task.feature.name,
                'error': error,
                'timestamp': timezone.now().isoformat()
            },
            category='mistake',
            importance=0.6
        )
        
        return {
            'task_failed': True,
            'error': error,
            'suggestion': {
                'type': 'retry_or_skip',
                'message': f"Task '{task.title}' failed. Retry or skip?",
                'task_id': str(task.id)
            }
        }
    
    # ==================== Private Methods ====================
    
    def _retrieve_memory_context(self, message: str) -> Dict[str, Any]:
        """Retrieve relevant memory context for a message."""
        # Semantic search in memory
        relevant_memories = self.memory_service.search_memory(message, top_k=5)
        
        # Get important memories
        important = self.memory_service.get_important_memories(min_importance=0.7, limit=3)
        
        # Get user preferences
        preferences = self.memory_service.get_memories_by_category('user_preference', limit=5)
        
        return {
            'relevant': relevant_memories,
            'important': important,
            'preferences': preferences
        }
    
    def _get_current_planning_state(self) -> Dict[str, Any]:
        """Get current planning state."""
        active_feature = self.planning_service.get_active_feature()
        
        return {
            'active_feature': self.planning_service._feature_to_tree(active_feature) if active_feature else None,
            'plan_summary': self.planning_service.get_plan_summary()
        }
    
    def _get_recent_session_context(self) -> List[Dict]:
        """Get recent session context from memory."""
        # Get recent planning events
        try:
            session_memories = self.memory_service.get_session_memory(
                session_id=str(self.planning_service.plan.id)
            )
            return session_memories[:10]  # Last 10 events
        except Exception:
            return []
    
    def _request_clarification(self, intent_result) -> Dict[str, Any]:
        """Build a clarification request response."""
        clarification_prompts = {
            'feature_name': "What would you like to name this feature?",
            'target_feature': "Which feature are you referring to?",
            'description': "Can you describe what this feature should do?"
        }
        
        questions = [
            clarification_prompts.get(item, f"Please specify: {item}")
            for item in intent_result.context_needed
        ]
        
        return {
            'type': 'clarification_needed',
            'intent': intent_result.intent_type.value,
            'confidence': intent_result.confidence,
            'questions': questions,
            'suggested_action': intent_result.suggested_action
        }
    
    def _execute_planning_action(self, action_mapping: Dict, intent_result) -> Dict[str, Any]:
        """Execute a planning service action."""
        method_name = action_mapping.get('service_method')
        
        if not method_name:
            return {'error': 'No planning action to execute'}
        
        params = action_mapping.get('params', {})
        
        # Handle feature lookup by name
        if action_mapping.get('find_by_name'):
            features = self.planning_service.find_feature_by_name(
                action_mapping['find_by_name']
            )
            if features:
                if 'feature_id' in params:
                    params['feature_id'] = str(features[0].id)
                elif method_name == 'switch_feature':
                    params['to_feature_id'] = str(features[0].id)
        
        # Get the service method
        method = getattr(self.planning_service, method_name, None)
        
        if not method:
            return {'error': f'Unknown planning method: {method_name}'}
        
        try:
            result = method(**params)
            
            # Convert result to serializable format
            if hasattr(result, '__dict__'):
                if hasattr(result, 'id'):
                    return {
                        'success': True,
                        'result_type': type(result).__name__,
                        'id': str(result.id),
                        'data': self.planning_service._feature_to_tree(result) if hasattr(result, 'name') else str(result)
                    }
            elif isinstance(result, tuple):
                return {
                    'success': True,
                    'result': result[1] if len(result) > 1 else None
                }
            else:
                return {'success': True, 'result': result}
                
        except ValueError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': f'Planning action failed: {str(e)}'}
    
    def _delegate_to_executor(self, intent_result, context: Dict) -> Dict[str, Any]:
        """Prepare delegation to executor agent."""
        return {
            'type': 'delegate_to_executor',
            'intent': intent_result.intent_type.value,
            'entities': intent_result.entities,
            'planning_context': self.get_planning_context_for_executor(),
            'suggested_action': intent_result.suggested_action
        }
    
    def _persist_action_to_memory(self, intent_result, result: Dict):
        """Persist the action taken to memory."""
        try:
            self.memory_service.store_short_term(
                session_id=str(self.planning_service.plan.id),
                key=f"action_{timezone.now().timestamp()}",
                content={
                    'intent': intent_result.intent_type.value,
                    'action': intent_result.suggested_action,
                    'success': result.get('success', True),
                    'timestamp': timezone.now().isoformat()
                },
                memory_type='context',
                ttl_seconds=86400
            )
        except Exception:
            pass
    
    def _build_response(self, intent_result, result: Dict, planning_state: Dict) -> Dict[str, Any]:
        """Build the final response."""
        response = {
            'type': 'planning_action',
            'intent': intent_result.intent_type.value,
            'action_taken': intent_result.suggested_action,
            'result': result,
            'current_state': {
                'active_feature': planning_state.get('active_feature'),
                'completion': planning_state.get('plan_summary', {}).get('completion_percentage', 0)
            }
        }
        
        # Add next suggestion
        if result.get('success'):
            active = self.planning_service.get_active_feature()
            if active:
                response['next_suggestion'] = self.planning_service._suggest_next_action(active)
            else:
                suggestions = self.planning_service.get_next_suggested_features(limit=1)
                if suggestions:
                    response['next_suggestion'] = f"Start feature: {suggestions[0]['name']}"
        
        return response
