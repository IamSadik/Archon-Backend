from django.db import models
import uuid


class TimeStampedModel(models.Model):
    """Abstract base model with created and updated timestamps."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class ActivityLog(models.Model):
    """
    Activity log for tracking user and system activities.
    Maps to activity_logs table in Supabase.
    """
    ACTIVITY_TYPES = [
        ('project_created', 'Project Created'),
        ('project_updated', 'Project Updated'),
        ('project_deleted', 'Project Deleted'),
        ('session_started', 'Session Started'),
        ('session_completed', 'Session Completed'),
        ('code_generated', 'Code Generated'),
        ('memory_created', 'Memory Created'),
        ('file_indexed', 'File Indexed'),
        ('search_performed', 'Search Performed'),
        ('user_login', 'User Login'),
        ('user_logout', 'User Logout'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='activity_logs',
        db_column='user_id'
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='activity_logs',
        null=True,
        blank=True,
        db_column='project_id'
    )
    activity_type = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    
    class Meta:
        db_table = 'activity_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['project']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.activity_type} by {self.user.email}"
