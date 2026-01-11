"""
Chat models for Archon.
Handles chat sessions and messages.
"""
import uuid
from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel


class ChatSession(TimeStampedModel):
    """
    Represents a chat session between a user and an agent.
    Maps to chat_sessions table in Supabase.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_sessions'
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='chat_sessions',
        null=True,
        blank=True
    )
    agent_session = models.ForeignKey(
        'agents.AgentSession',
        on_delete=models.SET_NULL,
        related_name='chat_sessions',
        null=True,
        blank=True,
        help_text='Associated agent session if this chat is part of an agent workflow'
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Title of the chat session'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        help_text='Additional metadata for the chat session'
    )
    is_active = models.BooleanField(
        default=True,
        null=True,
        help_text='Whether this chat session is currently active'
    )
    last_message_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of the last message'
    )
    
    class Meta:
        db_table = 'chat_sessions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['is_active', '-created_at']),
        ]
    
    def __str__(self):
        return f"ChatSession {self.id} - {self.user.email} - {self.title or 'Untitled'}"
    
    @property
    def message_count(self):
        """Get the number of messages in this session."""
        return self.messages.count()
    
    @property
    def last_message(self):
        """Get the last message in this session."""
        return self.messages.order_by('-created_at').first()


class ChatMessage(models.Model):
    """
    Represents a single message in a chat session.
    Maps to chat_messages table in Supabase.
    """
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
        ('function', 'Function'),
    ]
    
    CONTENT_TYPE_CHOICES = [
        ('text', 'Text'),
        ('code', 'Code'),
        ('markdown', 'Markdown'),
        ('json', 'JSON'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES,
        help_text='Role of the message sender'
    )
    content = models.TextField(
        help_text='Content of the message'
    )
    content_type = models.CharField(
        max_length=50,
        choices=CONTENT_TYPE_CHOICES,
        default='text',
        null=True,
        help_text='Type of content in the message'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        help_text='Additional metadata like tool calls, function results, etc.'
    )
    tokens_used = models.IntegerField(
        null=True,
        blank=True,
        help_text='Number of tokens used for this message'
    )
    model_used = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='LLM model used for generating this message'
    )
    execution_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text='Time taken to generate response in milliseconds'
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    
    class Meta:
        db_table = 'chat_messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['session', 'created_at']),
            models.Index(fields=['role', 'created_at']),
        ]
    
    def __str__(self):
        content_preview = self.content[:50] + '...' if len(self.content) > 50 else self.content
        return f"{self.role}: {content_preview}"
