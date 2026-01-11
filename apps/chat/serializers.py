"""
Chat serializers for API endpoints.
"""
from rest_framework import serializers
from apps.chat.models import ChatSession, ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    """Serializer for chat messages."""
    
    class Meta:
        model = ChatMessage
        fields = [
            'id', 'session', 'role', 'content', 'content_type',
            'metadata', 'tokens_used', 'model_used', 'execution_time_ms',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ChatMessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating chat messages."""
    
    class Meta:
        model = ChatMessage
        fields = ['session', 'role', 'content', 'content_type', 'metadata']


class ChatSessionSerializer(serializers.ModelSerializer):
    """Serializer for chat sessions."""
    
    message_count = serializers.IntegerField(read_only=True)
    last_message_preview = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True)
    
    class Meta:
        model = ChatSession
        fields = [
            'id', 'user', 'project', 'project_name', 'agent_session',
            'title', 'metadata', 'is_active', 'message_count',
            'last_message_preview', 'last_message_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
    
    def get_last_message_preview(self, obj):
        """Get preview of last message."""
        last_msg = obj.last_message
        if last_msg:
            content = last_msg.content
            return content[:100] + '...' if len(content) > 100 else content
        return None


class ChatSessionDetailSerializer(ChatSessionSerializer):
    """Detailed serializer for chat sessions including messages."""
    
    messages = ChatMessageSerializer(many=True, read_only=True)
    
    class Meta(ChatSessionSerializer.Meta):
        fields = ChatSessionSerializer.Meta.fields + ['messages']


class ChatSessionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating chat sessions."""
    
    class Meta:
        model = ChatSession
        fields = ['project', 'title', 'metadata']
    
    def create(self, validated_data):
        """Create chat session with current user."""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class SendMessageSerializer(serializers.Serializer):
    """Serializer for sending a message and getting a response."""
    
    message = serializers.CharField(required=True)
    session_id = serializers.UUIDField(required=False, allow_null=True)
    project_id = serializers.UUIDField(required=False, allow_null=True)
    include_context = serializers.BooleanField(default=True)
    include_memory = serializers.BooleanField(default=True)
    stream = serializers.BooleanField(default=False)


class ChatResponseSerializer(serializers.Serializer):
    """Serializer for chat responses."""
    
    session_id = serializers.UUIDField()
    message_id = serializers.UUIDField()
    role = serializers.CharField()
    content = serializers.CharField()
    metadata = serializers.JSONField()
    tokens_used = serializers.IntegerField(allow_null=True)


class ConversationHistorySerializer(serializers.Serializer):
    """Serializer for conversation history request."""
    
    session_id = serializers.UUIDField(required=True)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=200)
    before_id = serializers.UUIDField(required=False, allow_null=True)
