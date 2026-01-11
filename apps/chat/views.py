"""
Chat views for API endpoints.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count
from apps.chat.models import ChatSession, ChatMessage
from apps.chat.serializers import (
    ChatSessionSerializer,
    ChatSessionDetailSerializer,
    ChatSessionCreateSerializer,
    ChatMessageSerializer,
    ChatMessageCreateSerializer,
    SendMessageSerializer,
    ConversationHistorySerializer,
)
from apps.chat.services import ChatService
from apps.projects.models import Project


class ChatSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing chat sessions.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter sessions by user."""
        queryset = ChatSession.objects.filter(
            user=self.request.user
        ).annotate(
            message_count=Count('messages')
        ).select_related('project', 'agent_session')
        
        # Filter by project
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset.order_by('-updated_at')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return ChatSessionDetailSerializer
        elif self.action == 'create':
            return ChatSessionCreateSerializer
        return ChatSessionSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new chat session."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify project ownership if project is specified
        project_id = request.data.get('project')
        if project_id:
            try:
                Project.objects.get(id=project_id, user=request.user)
            except Project.DoesNotExist:
                return Response(
                    {'error': 'Project not found or access denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        session = serializer.save()
        
        return Response(
            ChatSessionSerializer(session).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['post'])
    def send_message(self, request):
        """
        Send a message and get a response.
        Creates a session if one doesn't exist.
        """
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get project if specified
        project = None
        project_id = serializer.validated_data.get('project_id')
        if project_id:
            try:
                project = Project.objects.get(id=project_id, user=request.user)
            except Project.DoesNotExist:
                return Response(
                    {'error': 'Project not found or access denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Get session if specified
        session = None
        session_id = serializer.validated_data.get('session_id')
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, user=request.user)
                project = session.project
            except ChatSession.DoesNotExist:
                return Response(
                    {'error': 'Session not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Create chat service and send message
        chat_service = ChatService(user=request.user, project=project)
        
        try:
            response = chat_service.send_message(
                message=serializer.validated_data['message'],
                session=session,
                include_context=serializer.validated_data.get('include_context', True),
                include_memory=serializer.validated_data.get('include_memory', True)
            )
            
            return Response(response, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """
        Get messages for a session.
        """
        session = self.get_object()
        
        limit = int(request.query_params.get('limit', 50))
        before_id = request.query_params.get('before_id')
        
        messages = session.messages.all()
        
        if before_id:
            try:
                before_msg = ChatMessage.objects.get(id=before_id)
                messages = messages.filter(created_at__lt=before_msg.created_at)
            except ChatMessage.DoesNotExist:
                pass
        
        messages = messages.order_by('-created_at')[:limit]
        messages = list(reversed(messages))
        
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def clear(self, request, pk=None):
        """
        Clear all messages in a session.
        """
        session = self.get_object()
        
        chat_service = ChatService(user=request.user, project=session.project)
        chat_service.clear_session(session)
        
        return Response({'status': 'cleared'}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def end(self, request, pk=None):
        """
        End a chat session.
        """
        session = self.get_object()
        
        chat_service = ChatService(user=request.user, project=session.project)
        chat_service.end_session(session)
        
        return Response(
            ChatSessionSerializer(session).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def regenerate(self, request, pk=None):
        """
        Regenerate the last assistant response.
        """
        session = self.get_object()
        
        # Get the last assistant message
        last_message = session.messages.filter(role='assistant').order_by('-created_at').first()
        
        if not last_message:
            return Response(
                {'error': 'No assistant message to regenerate'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        chat_service = ChatService(user=request.user, project=session.project)
        
        try:
            response = chat_service.regenerate_response(str(last_message.id))
            return Response(response, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ChatMessageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing chat messages.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ChatMessageSerializer
    
    def get_queryset(self):
        """Filter messages by user's sessions."""
        queryset = ChatMessage.objects.filter(
            session__user=self.request.user
        ).select_related('session')
        
        # Filter by session
        session_id = self.request.query_params.get('session')
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        
        # Filter by role
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)
        
        return queryset.order_by('created_at')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return ChatMessageCreateSerializer
        return ChatMessageSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new message (manual creation, not through chat service)."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify session ownership
        session_id = serializer.validated_data['session'].id
        if not ChatSession.objects.filter(id=session_id, user=request.user).exists():
            return Response(
                {'error': 'Session not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        message = serializer.save()
        
        return Response(
            ChatMessageSerializer(message).data,
            status=status.HTTP_201_CREATED
        )
