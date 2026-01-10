from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel


class Project(TimeStampedModel):
    """
    Project model - maps to existing Supabase projects table.
    Represents a user's codebase/repository that Archon works with.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='projects',
        db_column='user_id'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    repository_path = models.TextField(blank=True, null=True, help_text='Local file path')
    repository_url = models.TextField(blank=True, null=True, help_text='Git repository URL')
    
    # Programming context
    language = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        help_text='Primary programming language'
    )
    framework = models.CharField(max_length=100, blank=True, null=True)
    
    # Status tracking
    status = models.CharField(
        max_length=50,
        default='active',
        choices=[
            ('active', 'Active'),
            ('archived', 'Archived'),
            ('deleted', 'Deleted'),
        ]
    )
    
    # Additional settings stored as JSON
    settings = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'projects'  # Use existing Supabase table
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.user.email})"
    
    @property
    def is_active(self):
        """Check if project is active."""
        return self.status == 'active'
    
    def archive(self):
        """Archive the project."""
        self.status = 'archived'
        self.save(update_fields=['status', 'updated_at'])
    
    def activate(self):
        """Activate the project."""
        self.status = 'active'
        self.save(update_fields=['status', 'updated_at'])


class ProjectSettings(models.Model):
    """
    Extended project settings for fine-grained control.
    This is a helper model, data stored in Project.settings JSON field.
    """
    # This is just a reference model for documentation
    # Actual data lives in Project.settings JSONField
    
    # Example settings structure:
    # {
    #     "auto_index_files": true,
    #     "max_files": 1000,
    #     "excluded_paths": ["node_modules", ".git", "__pycache__"],
    #     "included_extensions": [".py", ".js", ".ts", ".jsx", ".tsx"],
    #     "enable_git_tracking": true,
    #     "context_window_size": 100000,
    #     "embedding_batch_size": 100
    # }
    
    class Meta:
        managed = False  # This is just a reference model
