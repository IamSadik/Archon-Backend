import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.core.models import TimeStampedModel
from apps.projects.models import Project
from apps.planning.models import Feature, Task

User = get_user_model()


class AgentSession(TimeStampedModel):
    """
    Agent execution session tracking.
    Maps to agent_sessions table in Supabase.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='agent_sessions',
        null=True,
        blank=True
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='agent_sessions'
    )
    feature = models.ForeignKey(
        Feature,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_sessions'
    )
    
    # Session details
    session_name = models.CharField(max_length=255)
    agent_type = models.CharField(
        max_length=100,
        default='general',
        null=True,
        help_text='Type of agent: general, coder, planner, etc.'
    )
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='active',
        null=True
    )
    
    # Goals and context
    goal = models.TextField(help_text='Primary goal for this session')
    context = models.JSONField(
        default=dict,
        null=True,
        help_text='Additional context for the agent'
    )
    
    # State management
    graph_state = models.JSONField(
        default=dict,
        null=True,
        help_text='Current LangGraph state'
    )
    checkpoint_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='LangGraph checkpoint ID for resuming'
    )
    
    # Results
    result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    
    # Timestamps
    started_at = models.DateTimeField(default=timezone.now, null=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now, null=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True, null=True)
    
    class Meta:
        db_table = 'agent_sessions'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['project']),
            models.Index(fields=['status']),
            models.Index(fields=['-started_at']),
        ]
    
    def __str__(self):
        return f"{self.session_name} ({self.status})"
    
    def mark_completed(self, result=None):
        """Mark session as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if result:
            self.result = result
        self.save()
    
    def mark_failed(self, error_message):
        """Mark session as failed."""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save()
    
    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity_at = timezone.now()
        self.save(update_fields=['last_activity_at'])


class AgentExecution(TimeStampedModel):
    """
    Individual agent execution step within a session.
    Maps to agent_executions table in Supabase.
    """
    STEP_TYPES = [
        ('planning', 'Planning'),
        ('reasoning', 'Reasoning'),
        ('tool_call', 'Tool Call'),
        ('code_generation', 'Code Generation'),
        ('decision', 'Decision'),
        ('reflection', 'Reflection'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='agent_executions',
        db_column='user_id'
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='agent_executions',
        null=True,
        blank=True,
        db_column='project_id'
    )
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name='executions',
        null=True,
        blank=True,
        db_column='session_id'
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_executions',
        db_column='task_id'
    )
    
    # Execution details
    agent_type = models.CharField(
        max_length=100,
        help_text='Type of agent: planner, executor, retriever, reviewer'
    )
    step_name = models.CharField(max_length=255, null=True, blank=True)
    step_type = models.CharField(max_length=50, choices=STEP_TYPES, null=True, blank=True)
    step_number = models.IntegerField(default=0, null=True)
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='running',
        null=True
    )
    
    # Input/Output
    input_data = models.JSONField(default=dict, null=True)
    output_data = models.JSONField(null=True, blank=True)
    execution_graph = models.JSONField(null=True, blank=True, help_text='Execution graph state')
    error_message = models.TextField(blank=True, null=True)
    
    # Token tracking (legacy field)
    tokens_used = models.IntegerField(null=True, blank=True, help_text='Total tokens used (legacy)')
    
    # LLM details
    llm_provider = models.CharField(max_length=50, blank=True, default='')
    model_name = models.CharField(max_length=100, blank=True, default='')
    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)
    total_tokens = models.IntegerField(null=True, blank=True)
    
    # Timing
    started_at = models.DateTimeField(null=True, blank=True, default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True, null=True)
    
    class Meta:
        db_table = 'agent_executions'
        ordering = ['session', 'step_number']
        indexes = [
            models.Index(fields=['session']),
            models.Index(fields=['status']),
            models.Index(fields=['step_number']),
        ]
    
    def __str__(self):
        return f"{self.step_name or self.agent_type} ({self.status})"
    
    def mark_running(self):
        """Mark execution as running."""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save()
    
    def mark_completed(self, output_data=None):
        """Mark execution as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if output_data:
            self.output_data = output_data
        
        # Calculate execution time
        if self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            self.execution_time_ms = int(duration * 1000)
        
        self.save()
    
    def mark_failed(self, error_message):
        """Mark execution as failed."""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = timezone.now()
        
        # Calculate execution time
        if self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            self.execution_time_ms = int(duration * 1000)
        
        self.save()


class ToolCall(TimeStampedModel):
    """
    Tool calls made by the agent during execution.
    Maps to tool_calls table in Supabase.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(
        AgentExecution,
        on_delete=models.CASCADE,
        related_name='tool_calls',
        db_column='execution_id'
    )
    
    # Tool details
    tool_name = models.CharField(max_length=255)
    tool_description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='pending',
        null=True
    )
    
    # Input/Output
    parameters = models.JSONField(default=dict, null=True)
    result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    
    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True, null=True)
    
    class Meta:
        db_table = 'tool_calls'
        ordering = ['execution', 'created_at']
        indexes = [
            models.Index(fields=['execution']),
            models.Index(fields=['tool_name']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.tool_name} ({self.status})"
    
    def mark_running(self):
        """Mark tool call as running."""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save()
    
    def mark_completed(self, result=None):
        """Mark tool call as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if result:
            self.result = result
        
        # Calculate execution time
        if self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            self.execution_time_ms = int(duration * 1000)
        
        self.save()
    
    def mark_failed(self, error_message):
        """Mark tool call as failed."""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = timezone.now()
        
        # Calculate execution time
        if self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            self.execution_time_ms = int(duration * 1000)
        
        self.save()


class AgentCheckpoint(TimeStampedModel):
    """
    Checkpoints for autonomous agent execution.
    Allows resuming execution after interruptions.
    Note: This table may not exist in DB yet - used for future implementation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name='checkpoints'
    )
    
    # State details
    iteration = models.IntegerField(default=0)
    state = models.CharField(max_length=50)  # ExecutionState enum value
    current_goal = models.TextField()
    
    # Action tracking
    completed_actions = models.JSONField(default=list)  # List of action IDs
    pending_actions = models.JSONField(default=list)    # List of action IDs
    
    # Context
    context_snapshot = models.JSONField(default=dict)   # Full context state
    memory_snapshot = models.JSONField(default=dict)    # Working memory state
    
    class Meta:
        db_table = 'agent_checkpoints'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['session']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"Checkpoint {self.iteration} for {self.session.session_name}"
