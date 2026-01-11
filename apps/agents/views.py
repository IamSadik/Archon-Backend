from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Avg, Sum
from apps.agents.models import AgentSession, AgentExecution, ToolCall
from apps.agents.serializers import (
    AgentSessionSerializer,
    AgentSessionDetailSerializer,
    AgentSessionCreateSerializer,
    AgentExecutionSerializer,
    AgentExecutionCreateSerializer,
    ToolCallSerializer,
    ToolCallCreateSerializer,
    AgentRunSerializer,
    AgentStatusUpdateSerializer,
    ExecutionStatusUpdateSerializer,
)
from apps.projects.models import Project
from apps.agents.services import AgentService


class AgentSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing agent sessions.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter sessions by user's projects."""
        queryset = AgentSession.objects.filter(
            project__user=self.request.user
        ).select_related('project', 'feature')
        
        # Filter by project
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        # Filter by status
        session_status = self.request.query_params.get('status')
        if session_status:
            queryset = queryset.filter(status=session_status)
        
        # Filter by agent type
        agent_type = self.request.query_params.get('agent_type')
        if agent_type:
            queryset = queryset.filter(agent_type=agent_type)
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return AgentSessionDetailSerializer
        elif self.action == 'create':
            return AgentSessionCreateSerializer
        return AgentSessionSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new agent session and optionally start execution."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get and verify project
        project_id = serializer.validated_data['project'].id
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create session using AgentService
        session = AgentService.create_session(
            user=request.user,
            project=project,
            goal=serializer.validated_data['goal'],
            agent_type=serializer.validated_data.get('agent_type', 'coder'),
            session_name=serializer.validated_data.get('session_name'),
            feature=serializer.validated_data.get('feature'),
            context=serializer.validated_data.get('context', {})
        )
        
        # Check if auto-start is requested
        auto_start = request.data.get('auto_start', False)
        if auto_start:
            # Execute in background (for production, use Celery)
            try:
                result = AgentService.execute_session(session, request.user)
                return Response({
                    'session': AgentSessionDetailSerializer(session).data,
                    'execution_result': result
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({
                    'session': AgentSessionDetailSerializer(session).data,
                    'execution_error': str(e),
                    'note': 'Session created but execution failed'
                }, status=status.HTTP_201_CREATED)
        
        return Response(
            AgentSessionDetailSerializer(session).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Execute or resume an agent session."""
        session = self.get_object()
        
        if session.status == 'completed':
            return Response(
                {'error': 'Cannot execute a completed session'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if session.status == 'failed':
            return Response(
                {'error': 'Cannot execute a failed session'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Execute the session using AgentService
            result = AgentService.execute_session(session, request.user)
            
            # Refresh session from database
            session.refresh_from_db()
            
            return Response({
                'session': AgentSessionDetailSerializer(session).data,
                'result': result
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {'error': f'Execution failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update session status."""
        session = self.get_object()
        serializer = AgentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        new_status = serializer.validated_data['status']
        
        if new_status == 'completed':
            result = serializer.validated_data.get('result')
            session.mark_completed(result)
        elif new_status == 'failed':
            error_message = serializer.validated_data.get('error_message', '')
            session.mark_failed(error_message)
        else:
            session.status = new_status
            session.save()
        
        return Response(
            AgentSessionSerializer(session).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause an active session."""
        session = self.get_object()
        
        if session.status != 'active':
            return Response(
                {'error': 'Can only pause active sessions'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        AgentService.pause_session(session)
        
        return Response(
            AgentSessionSerializer(session).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Resume a paused session."""
        session = self.get_object()
        
        if session.status != 'paused':
            return Response(
                {'error': 'Can only resume paused sessions'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            result = AgentService.resume_session(session, request.user)
            session.refresh_from_db()
            
            return Response({
                'session': AgentSessionSerializer(session).data,
                'result': result
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': f'Resume failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a session."""
        session = self.get_object()
        
        AgentService.cancel_session(session)
        
        return Response(
            AgentSessionSerializer(session).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['get'])
    def progress(self, request, pk=None):
        """Get session progress information."""
        session = self.get_object()
        
        progress = AgentService.get_session_progress(session)
        
        return Response(progress, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get session statistics."""
        session = self.get_object()
        
        executions = session.executions.all()
        tool_calls = ToolCall.objects.filter(execution__session=session)
        
        stats = {
            'session_id': session.id,
            'status': session.status,
            'total_executions': executions.count(),
            'completed_executions': executions.filter(status='completed').count(),
            'failed_executions': executions.filter(status='failed').count(),
            'total_tool_calls': tool_calls.count(),
            'successful_tool_calls': tool_calls.filter(status='completed').count(),
            'failed_tool_calls': tool_calls.filter(status='failed').count(),
            'total_tokens': executions.aggregate(Sum('total_tokens'))['total_tokens__sum'] or 0,
            'avg_execution_time_ms': executions.aggregate(Avg('execution_time_ms'))['execution_time_ms__avg'] or 0,
            'duration_seconds': (session.last_activity_at - session.started_at).total_seconds(),
        }
        
        return Response(stats)
    
    @action(detail=False, methods=['post'])
    def run(self, request):
        """Quick-run an agent with the specified goal (creates session and executes)."""
        serializer = AgentRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get and verify project
        project_id = serializer.validated_data['project']
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create and execute session
        session = AgentService.create_session(
            user=request.user,
            project=project,
            goal=serializer.validated_data['goal'],
            agent_type=serializer.validated_data.get('agent_type', 'coder'),
            context=serializer.validated_data.get('context', {})
        )
        
        try:
            result = AgentService.execute_session(session, request.user)
            session.refresh_from_db()
            
            return Response({
                'session': AgentSessionDetailSerializer(session).data,
                'result': result
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'session': AgentSessionDetailSerializer(session).data,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentExecutionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing agent executions.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter executions by user's projects."""
        queryset = AgentExecution.objects.filter(
            session__project__user=self.request.user
        ).select_related('session', 'task')
        
        # Filter by session
        session_id = self.request.query_params.get('session')
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        
        # Filter by status
        exec_status = self.request.query_params.get('status')
        if exec_status:
            queryset = queryset.filter(status=exec_status)
        
        # Filter by step type
        step_type = self.request.query_params.get('step_type')
        if step_type:
            queryset = queryset.filter(step_type=step_type)
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return AgentExecutionCreateSerializer
        return AgentExecutionSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new agent execution."""
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            # Verify session ownership
            session_id = serializer.validated_data['session'].id
            session = AgentSession.objects.filter(
                id=session_id,
                project__user=request.user
            ).first()
            
            if not session:
                return Response(
                    {'error': 'Session not found or access denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Save with user and inherit agent_type from session if not set
            # The model default for agent_type is 'general', but we prefer the session's agent_type
            execution = serializer.save(
                user=request.user,
                agent_type=session.agent_type or 'general'
            )
            
            return Response(
                AgentExecutionSerializer(execution).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            # Catch DB integrity errors or other save issues
            import traceback
            traceback.print_exc()
            return Response(
                {'error': str(e), 'type': type(e).__name__},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update execution status."""
        execution = self.get_object()
        serializer = ExecutionStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        new_status = serializer.validated_data['status']
        
        if new_status == 'running':
            execution.mark_running()
        elif new_status == 'completed':
            output_data = serializer.validated_data.get('output_data')
            execution.mark_completed(output_data)
        elif new_status == 'failed':
            error_message = serializer.validated_data.get('error_message', '')
            execution.mark_failed(error_message)
        else:
            execution.status = new_status
            execution.save()
        
        # Update token counts if provided
        if 'prompt_tokens' in serializer.validated_data:
            execution.prompt_tokens = serializer.validated_data['prompt_tokens']
        if 'completion_tokens' in serializer.validated_data:
            execution.completion_tokens = serializer.validated_data['completion_tokens']
        if 'total_tokens' in serializer.validated_data:
            execution.total_tokens = serializer.validated_data['total_tokens']
        
        execution.save()
        
        return Response(
            AgentExecutionSerializer(execution).data,
            status=status.HTTP_200_OK
        )


class ToolCallViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tool calls.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter tool calls by user's projects."""
        queryset = ToolCall.objects.filter(
            execution__session__project__user=self.request.user
        ).select_related('execution')
        
        # Filter by execution
        execution_id = self.request.query_params.get('execution')
        if execution_id:
            queryset = queryset.filter(execution_id=execution_id)
        
        # Filter by tool name
        tool_name = self.request.query_params.get('tool_name')
        if tool_name:
            queryset = queryset.filter(tool_name=tool_name)
        
        # Filter by status
        tool_status = self.request.query_params.get('status')
        if tool_status:
            queryset = queryset.filter(status=tool_status)
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return ToolCallCreateSerializer
        return ToolCallSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new tool call."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify execution ownership
        execution_id = serializer.validated_data['execution'].id
        if not AgentExecution.objects.filter(
            id=execution_id,
            session__project__user=request.user
        ).exists():
            return Response(
                {'error': 'Execution not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        tool_call = serializer.save()
        
        return Response(
            ToolCallSerializer(tool_call).data,
            status=status.HTTP_201_CREATED
        )
