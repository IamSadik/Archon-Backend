import uuid
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel
from apps.projects.models import Project


class ProjectPlan(TimeStampedModel):
    """
    Root-level project plan containing the feature tree structure.
    Maps to Supabase project_plans table.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='plan'
    )
    
    # Plan metadata
    plan_version = models.IntegerField(default=1)
    tree_structure = models.JSONField(
        default=dict,
        help_text='Full hierarchical structure for quick access'
    )
    
    # Statistics
    total_features = models.IntegerField(default=0)
    completed_features = models.IntegerField(default=0)
    active_feature = models.ForeignKey(
        'Feature',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='active_in_plan'
    )
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'project_plans'
    
    def __str__(self):
        return f"Plan for {self.project.name} (v{self.plan_version})"
    
    @property
    def completion_percentage(self):
        """Calculate completion percentage."""
        if self.total_features == 0:
            return 0
        return (self.completed_features / self.total_features) * 100
    
    def update_stats(self):
        """Update plan statistics."""
        features = self.features.all()
        self.total_features = features.count()
        self.completed_features = features.filter(status='completed').count()
        self.save(update_fields=['total_features', 'completed_features'])


class Feature(TimeStampedModel):
    """
    Feature in the project plan tree structure.
    Can have parent features (hierarchical).
    Maps to Supabase features table.
    """
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('blocked', 'Blocked'),
    ]
    
    EFFORT_CHOICES = [
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('extra_large', 'Extra Large'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(
        ProjectPlan,
        on_delete=models.CASCADE,
        related_name='features'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    
    # Feature details
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='not_started'
    )
    
    # Hierarchy
    depth_level = models.IntegerField(
        default=0,
        help_text='0 = root feature, 1 = sub-feature, etc.'
    )
    order_index = models.IntegerField(
        default=0,
        help_text='Order within siblings'
    )
    
    # Priority and effort
    priority = models.IntegerField(
        default=0,
        help_text='Higher number = higher priority'
    )
    estimated_effort = models.CharField(
        max_length=50,
        choices=EFFORT_CHOICES,
        blank=True,
        null=True
    )
    actual_effort_minutes = models.IntegerField(
        null=True,
        blank=True,
        help_text='Actual time spent in minutes'
    )
    
    # Dependencies and blocking
    dependencies = models.JSONField(
        default=list,
        help_text='Array of feature IDs this depends on'
    )
    blocking_reason = models.TextField(blank=True)
    
    # Related data
    related_files = models.JSONField(
        default=list,
        help_text='Array of file IDs'
    )
    related_memories = models.JSONField(
        default=list,
        help_text='Array of memory IDs'
    )
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'features'
        ordering = ['plan', '-priority', 'order_index']
        indexes = [
            models.Index(fields=['plan']),
            models.Index(fields=['parent']),
            models.Index(fields=['status']),
            models.Index(fields=['-priority']),
            models.Index(fields=['order_index']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.status})"
    
    def get_children(self):
        """Get all child features."""
        return self.children.all().order_by('order_index')
    
    def get_descendants(self):
        """Get all descendant features recursively."""
        descendants = []
        for child in self.get_children():
            descendants.append(child)
            descendants.extend(child.get_descendants())
        return descendants
    
    def mark_in_progress(self):
        """Mark feature as in progress."""
        if not self.started_at:
            self.started_at = timezone.now()
        self.status = 'in_progress'
        self.last_activity_at = timezone.now()
        self.save()
    
    def mark_completed(self):
        """Mark feature as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.last_activity_at = timezone.now()
        self.save()
        
        # Update plan statistics
        self.plan.update_stats()
    
    def mark_blocked(self, reason):
        """Mark feature as blocked."""
        self.status = 'blocked'
        self.blocking_reason = reason
        self.last_activity_at = timezone.now()
        self.save()
    
    def unblock(self):
        """Remove blocked status."""
        if self.status == 'blocked':
            self.status = 'not_started' if not self.started_at else 'in_progress'
            self.blocking_reason = ''
            self.last_activity_at = timezone.now()
            self.save()
    
    @property
    def is_root(self):
        """Check if this is a root feature."""
        return self.parent is None
    
    @property
    def is_leaf(self):
        """Check if this is a leaf feature (no children)."""
        return not self.children.exists()


class Task(TimeStampedModel):
    """
    Granular task within a feature.
    Maps to Supabase tasks table.
    """
    TASK_TYPES = [
        ('code_generation', 'Code Generation'),
        ('code_modification', 'Code Modification'),
        ('research', 'Research'),
        ('review', 'Review'),
        ('testing', 'Testing'),
        ('documentation', 'Documentation'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    
    # Task details
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    task_type = models.CharField(
        max_length=50,
        choices=TASK_TYPES,
        blank=True,
        null=True
    )
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='pending'
    )
    order_index = models.IntegerField(default=0)
    
    # Execution results
    result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    execution_time_seconds = models.IntegerField(null=True, blank=True)
    
    # Timestamp
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'tasks'
        ordering = ['feature', 'order_index']
        indexes = [
            models.Index(fields=['feature']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.status})"
    
    def mark_completed(self, result=None):
        """Mark task as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if result:
            self.result = result
        self.save()
    
    def mark_failed(self, error_message):
        """Mark task as failed."""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save()
