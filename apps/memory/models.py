import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta
from apps.core.models import TimeStampedModel
from apps.authentication.models import User
from apps.projects.models import Project


class ShortTermMemory(models.Model):
    """
    Short-term memory for temporary conversation and execution context.
    Automatically expires after TTL period.
    Maps to Supabase short_term_memory table.
    """
    MEMORY_TYPES = [
        ('conversation', 'Conversation'),
        ('code_snippet', 'Code Snippet'),
        ('decision', 'Decision'),
        ('context', 'Context'),
        ('state', 'State'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='short_term_memories'
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='short_term_memories'
    )
    session_id = models.UUIDField(
        help_text='Reference to chat session or execution session'
    )
    
    # Memory content
    memory_key = models.CharField(max_length=255)
    content = models.JSONField(help_text='Memory content as JSON')
    memory_type = models.CharField(
        max_length=50,
        choices=MEMORY_TYPES,
        default='conversation'
    )
    
    # TTL (Time To Live)
    ttl_seconds = models.IntegerField(
        default=3600,
        help_text='Time to live in seconds (default: 1 hour)'
    )
    expires_at = models.DateTimeField(
        help_text='Automatically set based on TTL'
    )
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    accessed_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'short_term_memory'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['project']),
            models.Index(fields=['session_id']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['memory_key']),
        ]
    
    def save(self, *args, **kwargs):
        """Set expiry time on creation."""
        if not self.expires_at:
            self.expires_at = self.created_at + timedelta(seconds=self.ttl_seconds)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"STM: {self.memory_key} (expires: {self.expires_at})"
    
    @property
    def is_expired(self):
        """Check if memory has expired."""
        return timezone.now() > self.expires_at
    
    def touch(self):
        """Update last accessed timestamp."""
        self.accessed_at = timezone.now()
        self.save(update_fields=['accessed_at'])


class LongTermMemory(TimeStampedModel):
    """
    Long-term memory for persistent knowledge and patterns.
    Includes importance scoring and vector embeddings.
    Maps to Supabase long_term_memory table.
    """
    MEMORY_CATEGORIES = [
        ('architectural_decision', 'Architectural Decision'),
        ('user_preference', 'User Preference'),
        ('constraint', 'Constraint'),
        ('pattern', 'Pattern'),
        ('mistake', 'Mistake'),
        ('best_practice', 'Best Practice'),
        ('lesson_learned', 'Lesson Learned'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='long_term_memories'
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='long_term_memories'
    )
    
    # Memory content
    memory_key = models.CharField(max_length=255)
    content = models.JSONField(help_text='Memory content as JSON')
    memory_category = models.CharField(
        max_length=100,
        choices=MEMORY_CATEGORIES,
        blank=True,
        null=True
    )
    
    # Importance and relevance
    importance_score = models.FloatField(
        default=0.5,
        help_text='Importance score from 0 to 1'
    )
    access_count = models.IntegerField(
        default=0,
        help_text='Number of times this memory has been accessed'
    )
    
    # Vector embeddings (reference to Pinecone)
    embedding_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Reference to Pinecone vector ID'
    )
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    last_accessed_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'long_term_memory'
        ordering = ['-importance_score', '-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['project']),
            models.Index(fields=['memory_category']),
            models.Index(fields=['-importance_score']),
            models.Index(fields=['memory_key']),
        ]
    
    def __str__(self):
        return f"LTM: {self.memory_key} (importance: {self.importance_score})"
    
    def access(self):
        """Increment access count and update timestamp."""
        self.access_count += 1
        self.last_accessed_at = timezone.now()
        self.save(update_fields=['access_count', 'last_accessed_at'])
    
    def boost_importance(self, amount=0.1):
        """Increase importance score (max 1.0)."""
        self.importance_score = min(1.0, self.importance_score + amount)
        self.save(update_fields=['importance_score'])
    
    def decay_importance(self, amount=0.05):
        """Decrease importance score (min 0.0)."""
        self.importance_score = max(0.0, self.importance_score - amount)
        self.save(update_fields=['importance_score'])


class MemorySnapshot(TimeStampedModel):
    """
    Snapshot of memory state at a point in time.
    Used for debugging and memory replay.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='memory_snapshots'
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='memory_snapshots',
        null=True,
        blank=True
    )
    session_id = models.UUIDField(null=True, blank=True)
    
    # Snapshot data
    snapshot_name = models.CharField(max_length=255)
    short_term_data = models.JSONField(default=dict)
    long_term_data = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    
    class Meta:
        db_table = 'memory_snapshots'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Snapshot: {self.snapshot_name} ({self.created_at})"
