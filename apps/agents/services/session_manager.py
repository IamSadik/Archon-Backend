"""
Session Manager - Manages autonomous agent sessions with real-time updates.
Coordinates between the autonomous executor and WebSocket consumers.
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
from django.utils import timezone
from channels.layers import get_channel_layer

from apps.agents.services.autonomous_executor import (
    AutonomousExecutor,
    ExecutionState,
    ExecutionContext
)

logger = logging.getLogger(__name__)


@dataclass
class AgentSession:
    """Represents an active agent session."""
    session_id: str
    user_id: str
    project_id: str
    channel_name: Optional[str] = None  # WebSocket channel
    executor: Optional[AutonomousExecutor] = None
    created_at: datetime = field(default_factory=timezone.now)
    last_activity: datetime = field(default_factory=timezone.now)
    mode: str = "interactive"  # "interactive" or "autonomous"
    autonomy_level: str = "supervised"  # "supervised", "semi-autonomous", "fully-autonomous"


class SessionManager:
    """
    Manages agent sessions and coordinates autonomous behavior.
    
    This is a singleton that tracks all active sessions and provides
    methods to start/stop autonomous execution, handle WebSocket
    connections, and route messages.
    """
    
    _instance = None
    _sessions: Dict[str, AgentSession] = {}
    _channel_layer = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions = {}
            cls._instance._channel_layer = None
        return cls._instance
    
    @property
    def channel_layer(self):
        if self._channel_layer is None:
            self._channel_layer = get_channel_layer()
        return self._channel_layer
    
    # ==================== Session Management ====================
    
    def create_session(
        self,
        user_id: str,
        project_id: str,
        channel_name: str = None,
        mode: str = "interactive",
        autonomy_level: str = "supervised"
    ) -> AgentSession:
        """Create a new agent session."""
        session_id = str(uuid4())
        
        session = AgentSession(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            channel_name=channel_name,
            mode=mode,
            autonomy_level=autonomy_level
        )
        
        self._sessions[session_id] = session
        logger.info(f"Created session {session_id} for user {user_id}")
        
        return session
    
    def get_session(self, session_id: str) -> Optional[AgentSession]:
        """Get an existing session."""
        return self._sessions.get(session_id)
    
    def get_user_sessions(self, user_id: str) -> List[AgentSession]:
        """Get all sessions for a user."""
        return [s for s in self._sessions.values() if s.user_id == user_id]
    
    def update_channel(self, session_id: str, channel_name: str):
        """Update the WebSocket channel for a session."""
        if session_id in self._sessions:
            self._sessions[session_id].channel_name = channel_name
            self._sessions[session_id].last_activity = timezone.now()
    
    def close_session(self, session_id: str):
        """Close and clean up a session."""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            
            # Stop autonomous execution if running
            if session.executor:
                asyncio.create_task(session.executor.stop("Session closed"))
            
            del self._sessions[session_id]
            logger.info(f"Closed session {session_id}")
    
    # ==================== Autonomous Mode ====================
    
    async def start_autonomous_mode(
        self,
        session_id: str,
        planning_service,
        memory_service,
        code_executor=None,
        initial_goal: str = None,
        autonomy_level: str = None
    ) -> Dict[str, Any]:
        """
        Start autonomous execution for a session.
        
        Args:
            session_id: Session to start autonomous mode for
            planning_service: PlanningService instance
            memory_service: MemoryService instance
            code_executor: Optional code execution service
            initial_goal: Optional specific goal
            autonomy_level: Override session's autonomy level
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        if session.executor and session.executor._running:
            return {
                'status': 'already_running',
                'session_id': session_id
            }
        
        # Update autonomy level if provided
        if autonomy_level:
            session.autonomy_level = autonomy_level
        
        # Create executor with callbacks
        executor = AutonomousExecutor(
            planning_service=planning_service,
            memory_service=memory_service,
            code_executor=code_executor,
            on_status_change=lambda n: self._on_status_change(session_id, n),
            on_action_complete=lambda a: self._on_action_complete(session_id, a),
            on_user_input_needed=lambda r: self._on_user_input_needed(session_id, r)
        )
        
        # Configure based on autonomy level
        self._configure_autonomy(executor, session.autonomy_level)
        
        session.executor = executor
        session.mode = "autonomous"
        
        # Start execution
        context = await executor.start(
            session_id=session_id,
            project_id=session.project_id,
            user_id=session.user_id,
            initial_goal=initial_goal
        )
        
        return {
            'status': 'started',
            'session_id': session_id,
            'state': context.state.value,
            'autonomy_level': session.autonomy_level
        }
    
    async def pause_autonomous_mode(self, session_id: str, reason: str = "User requested") -> Dict[str, Any]:
        """Pause autonomous execution."""
        session = self.get_session(session_id)
        if not session or not session.executor:
            raise ValueError(f"No active executor for session: {session_id}")
        
        context = await session.executor.pause(reason)
        
        return {
            'status': 'paused',
            'session_id': session_id,
            'state': context.state.value,
            'checkpoint': context.checkpoints[-1] if context.checkpoints else None
        }
    
    async def resume_autonomous_mode(self, session_id: str) -> Dict[str, Any]:
        """Resume paused autonomous execution."""
        session = self.get_session(session_id)
        if not session or not session.executor:
            raise ValueError(f"No active executor for session: {session_id}")
        
        context = await session.executor.resume()
        
        return {
            'status': 'resumed',
            'session_id': session_id,
            'state': context.state.value
        }
    
    async def stop_autonomous_mode(self, session_id: str, reason: str = "User requested") -> Dict[str, Any]:
        """Stop autonomous execution completely."""
        session = self.get_session(session_id)
        if not session or not session.executor:
            raise ValueError(f"No active executor for session: {session_id}")
        
        context = await session.executor.stop(reason)
        session.mode = "interactive"
        
        return {
            'status': 'stopped',
            'session_id': session_id,
            'total_actions': len(context.completed_actions),
            'checkpoint': context.checkpoints[-1] if context.checkpoints else None
        }
    
    async def get_autonomous_status(self, session_id: str) -> Dict[str, Any]:
        """Get status of autonomous execution."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        if not session.executor:
            return {
                'session_id': session_id,
                'mode': session.mode,
                'state': 'not_started',
                'autonomy_level': session.autonomy_level
            }
        
        status = await session.executor.get_status()
        status['mode'] = session.mode
        status['autonomy_level'] = session.autonomy_level
        
        return status
    
    async def provide_user_response(
        self,
        session_id: str,
        response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Provide user input to waiting executor."""
        session = self.get_session(session_id)
        if not session or not session.executor:
            raise ValueError(f"No active executor for session: {session_id}")
        
        await session.executor.provide_user_input(response)
        
        return {'status': 'response_received'}
    
    # ==================== Autonomy Configuration ====================
    
    def _configure_autonomy(self, executor: AutonomousExecutor, level: str):
        """Configure executor based on autonomy level."""
        if level == "supervised":
            # Require confirmation for all significant actions
            executor.config['require_confirmation_for'] = [
                executor.config['require_confirmation_for']
            ]
            executor.config['max_iterations'] = 10
            executor.config['checkpoint_interval'] = 3
        
        elif level == "semi-autonomous":
            # Only confirm destructive/code changes
            from apps.agents.services.autonomous_executor import ActionType
            executor.config['require_confirmation_for'] = [
                ActionType.GENERATE_CODE,
                ActionType.REFACTOR
            ]
            executor.config['max_iterations'] = 50
            executor.config['checkpoint_interval'] = 10
        
        elif level == "fully-autonomous":
            # No confirmations, full autonomy
            executor.config['require_confirmation_for'] = []
            executor.config['max_iterations'] = 100
            executor.config['checkpoint_interval'] = 20
    
    # ==================== WebSocket Integration ====================
    
    async def _on_status_change(self, session_id: str, notification: Dict[str, Any]):
        """Handle status change from executor."""
        await self._send_to_session(session_id, {
            'type': 'autonomous_status',
            'event': notification['event'],
            'state': notification['state'],
            'timestamp': notification['timestamp'],
            'details': notification['details']
        })
    
    async def _on_action_complete(self, session_id: str, action: Dict[str, Any]):
        """Handle action completion from executor."""
        await self._send_to_session(session_id, {
            'type': 'autonomous_action',
            'action_id': action['action_id'],
            'action_type': action['action_type'],
            'description': action['description'],
            'result': action['result'],
            'iteration': action['iteration']
        })
    
    async def _on_user_input_needed(self, session_id: str, request: Dict[str, Any]):
        """Handle user input request from executor."""
        await self._send_to_session(session_id, {
            'type': 'autonomous_input_needed',
            'request_type': request['type'],
            'action_id': request.get('action_id'),
            'question': request.get('question'),
            'action': request.get('action')
        })
    
    async def _send_to_session(self, session_id: str, message: Dict[str, Any]):
        """Send a message to a session's WebSocket channel."""
        session = self.get_session(session_id)
        if not session or not session.channel_name:
            logger.warning(f"No channel for session {session_id}")
            return
        
        try:
            await self.channel_layer.send(
                session.channel_name,
                {
                    'type': 'agent.message',
                    'message': message
                }
            )
        except Exception as e:
            logger.error(f"Error sending to session {session_id}: {e}")
    
    # ==================== Broadcast Methods ====================
    
    async def broadcast_to_project(self, project_id: str, message: Dict[str, Any]):
        """Broadcast a message to all sessions for a project."""
        for session in self._sessions.values():
            if session.project_id == project_id and session.channel_name:
                await self._send_to_session(session.session_id, message)
    
    async def broadcast_to_user(self, user_id: str, message: Dict[str, Any]):
        """Broadcast a message to all sessions for a user."""
        for session in self._sessions.values():
            if session.user_id == user_id and session.channel_name:
                await self._send_to_session(session.session_id, message)


# Global instance
session_manager = SessionManager()
