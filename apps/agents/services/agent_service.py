"""
Agent Service - Core orchestration for agent execution.
Manages agent sessions, graph execution, and database persistence.
"""
import asyncio
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import models
from asgiref.sync import sync_to_async
from langchain_core.load import dumpd, load
from apps.agents.models import AgentSession, AgentExecution
from apps.agents.graphs import CoderAgentGraph, PlannerAgentGraph
from apps.agents.services.llm_service import LLMService


class AgentService:
    """
    Main service for managing agent operations.
    Handles session creation, execution, and result persistence.
    """
    
    # Map agent types to graph classes
    AGENT_GRAPH_MAP = {
        'coder': CoderAgentGraph,
        'planner': PlannerAgentGraph,
        'general': CoderAgentGraph,  # Default to coder for now
    }
    
    @staticmethod
    def create_session(
        user,
        project,
        goal: str,
        agent_type: str = 'coder',
        session_name: str = None,
        feature=None,
        context: Dict = None
    ) -> AgentSession:
        """
        Create a new agent session.
        
        Args:
            user: User instance
            project: Project instance
            goal: The goal for the agent to accomplish
            agent_type: Type of agent ('coder', 'planner', etc.)
            session_name: Optional name for the session
            feature: Optional feature this session is related to
            context: Additional context for the agent
            
        Returns:
            Created AgentSession instance
        """
        if session_name is None:
            session_name = f"{agent_type.title()} Session - {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        
        session = AgentSession.objects.create(
            user=user,
            project=project,
            feature=feature,
            session_name=session_name,
            agent_type=agent_type,
            goal=goal,
            context=context or {},
            status='active',
            graph_state={}
        )
        
        return session
    
    @staticmethod
    def get_agent_graph(agent_type: str, user):
        """
        Get the appropriate agent graph for the agent type.
        
        Args:
            agent_type: Type of agent
            user: User instance for LLM preferences
            
        Returns:
            Configured agent graph instance
        """
        graph_class = AgentService.AGENT_GRAPH_MAP.get(agent_type, CoderAgentGraph)
        
        # Get user's preferred LLM
        llm = LLMService.get_user_preferred_llm(user)
        
        # Create and return graph instance
        return graph_class(llm=llm, checkpoint=True)
    
    @staticmethod
    async def execute_session_async(session: AgentSession, user) -> Dict[str, Any]:
        """
        Execute an agent session asynchronously.
        
        Args:
            session: AgentSession instance to execute
            user: User instance
            
        Returns:
            Execution results
        """
        try:
            # Update session status (wrap in sync_to_async)
            session.status = 'active'
            session.started_at = timezone.now()
            await sync_to_async(session.save)()
            
            # Get the appropriate agent graph
            agent_graph = AgentService.get_agent_graph(session.agent_type, user)
            
            # Create initial state
            initial_state = agent_graph.create_initial_state(
                session_id=str(session.id),
                project_id=str(session.project.id),
                goal=session.goal,
                max_iterations=session.context.get('max_iterations', 50)
            )
            
            # Track execution (wrap in sync_to_async)
            execution = await sync_to_async(AgentExecution.objects.create)(
                session=session,
                user=user,
                agent_type=session.agent_type,  # Add agent_type from session
                step_name='Agent Execution',
                step_type='reasoning',
                step_number=1,
                status='running',
                input_data={'initial_state': session.goal}
            )
            await sync_to_async(execution.mark_running)()
            
            # Execute the graph
            final_state = await agent_graph.arun(initial_state)
            
            # Extract final result
            final_result = final_state.get('final_result', {})
            
            # Serialize the final_state using dumpd before saving
            serialized_state = dumpd(final_state)
            
            # Update session with results (wrap in sync_to_async)
            await sync_to_async(session.mark_completed)(result=final_result)
            session.graph_state = serialized_state  # Use serialized state
            await sync_to_async(session.save)()
            
            # Update execution (wrap in sync_to_async)
            await sync_to_async(execution.mark_completed)(output_data=final_result)
            
            return {
                'success': True,
                'session_id': str(session.id),
                'result': final_result,
                'status': 'completed'
            }
            
        except Exception as e:
            # Handle errors (wrap in sync_to_async)
            error_message = str(e)
            
            # Don't save the session object with non-serialized state
            try:
                # Refresh session from database to clear any non-serializable data
                await sync_to_async(session.refresh_from_db)()
                await sync_to_async(session.mark_failed)(error_message)
            except Exception as save_error:
                # If we still can't save, log the error but don't crash
                print(f"Failed to save session error state: {save_error}")
            
            if 'execution' in locals():
                try:
                    await sync_to_async(execution.mark_failed)(error_message)
                except Exception as exec_error:
                    print(f"Failed to save execution error state: {exec_error}")
            
            return {
                'success': False,
                'session_id': str(session.id),
                'error': error_message,
                'status': 'failed'
            }
    
    @staticmethod
    def execute_session(session: AgentSession, user) -> Dict[str, Any]:
        """
        Execute an agent session synchronously.
        Wraps async execution for synchronous contexts.
        
        Args:
            session: AgentSession instance to execute
            user: User instance
            
        Returns:
            Execution results
        """
        # Create new event loop for async execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                AgentService.execute_session_async(session, user)
            )
            return result
        finally:
            loop.close()
    
    @staticmethod
    def resume_session(session: AgentSession, user) -> Dict[str, Any]:
        """
        Resume a paused agent session from checkpoint.
        
        Args:
            session: AgentSession instance to resume
            user: User instance
            
        Returns:
            Execution results
        """
        if session.status not in ['paused', 'active']:
            return {
                'success': False,
                'error': f'Cannot resume session with status: {session.status}'
            }
        
        # Load the serialized state back into LangChain objects
        if session.graph_state:
            try:
                # Convert JSON dictionaries back into LangChain message objects
                session.graph_state = load(session.graph_state)
            except Exception as e:
                print(f"Failed to deserialize graph state: {e}")
        
        # Update session status
        session.status = 'active'
        session.last_activity_at = timezone.now()
        session.save()
        
        # Execute from checkpoint
        return AgentService.execute_session(session, user)
    
    @staticmethod
    def pause_session(session: AgentSession):
        """
        Pause an active agent session.
        
        Args:
            session: AgentSession instance to pause
        """
        if session.status == 'active':
            session.status = 'paused'
            session.save()
    
    @staticmethod
    def cancel_session(session: AgentSession):
        """
        Cancel an agent session.
        
        Args:
            session: AgentSession instance to cancel
        """
        session.status = 'cancelled'
        session.completed_at = timezone.now()
        session.save()
    
    @staticmethod
    def get_session_progress(session: AgentSession) -> Dict[str, Any]:
        """
        Get progress information for a session.
        
        Args:
            session: AgentSession instance
            
        Returns:
            Progress information
        """
        executions = session.executions.all()
        
        return {
            'session_id': str(session.id),
            'status': session.status,
            'iterations': session.graph_state.get('iteration_count', 0),
            'total_executions': executions.count(),
            'completed_executions': executions.filter(status='completed').count(),
            'failed_executions': executions.filter(status='failed').count(),
            'tool_calls': session.executions.aggregate(
                total=models.Count('tool_calls')
            )['total'] or 0,
            'started_at': session.started_at,
            'last_activity': session.last_activity_at,
            'duration_seconds': (
                (session.completed_at or timezone.now()) - session.started_at
            ).total_seconds() if session.started_at else 0
        }
