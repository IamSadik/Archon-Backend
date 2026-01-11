import uuid
from django.db import models
from apps.core.models import TimeStampedModel
from apps.projects.models import Project


class ContextFile(TimeStampedModel):
    """
    Represents a file or folder in a project's context.
    Maps to Supabase context_files table.
    """
    FILE_TYPES = [
        ('code', 'Code'),
        ('pdf', 'PDF Document'),
        ('doc', 'Document'),
        ('txt', 'Text File'),
        ('md', 'Markdown'),
        ('json', 'JSON'),
        ('yaml', 'YAML'),
        ('xml', 'XML'),
        ('image', 'Image'),
        ('other', 'Other'),
    ]
    
    PROGRAMMING_LANGUAGES = [
        ('python', 'Python'),
        ('javascript', 'JavaScript'),
        ('typescript', 'TypeScript'),
        ('java', 'Java'),
        ('cpp', 'C++'),
        ('csharp', 'C#'),
        ('go', 'Go'),
        ('rust', 'Rust'),
        ('php', 'PHP'),
        ('ruby', 'Ruby'),
        ('swift', 'Swift'),
        ('kotlin', 'Kotlin'),
        ('sql', 'SQL'),
        ('html', 'HTML'),
        ('css', 'CSS'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='context_files'
    )
    
    # File information
    file_path = models.TextField(help_text='Full path to the file')
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50, choices=FILE_TYPES)
    file_extension = models.CharField(max_length=10, blank=True)
    
    # Content
    content = models.TextField(blank=True, null=True, help_text='File content')
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text='SHA-256 hash for deduplication'
    )
    file_size_bytes = models.BigIntegerField(null=True, blank=True)
    
    # Programming language
    language = models.CharField(
        max_length=50,
        choices=PROGRAMMING_LANGUAGES,
        blank=True,
        null=True,
        help_text='Programming language for code files'
    )
    
    # Metadata and indexing
    metadata = models.JSONField(default=dict, blank=True)
    is_indexed = models.BooleanField(default=False)
    embedding_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Reference to Pinecone vector ID'
    )
    
    # Hierarchical structure (for folders)
    parent_folder = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    
    class Meta:
        db_table = 'context_files'
        ordering = ['file_path']
        indexes = [
            models.Index(fields=['project']),
            models.Index(fields=['file_type']),
            models.Index(fields=['is_indexed']),
            models.Index(fields=['content_hash']),
            models.Index(fields=['parent_folder']),
        ]
    
    def __str__(self):
        return f"{self.file_name} ({self.project.name})"
    
    @property
    def is_code_file(self):
        """Check if this is a code file."""
        return self.file_type == 'code'
    
    @property
    def is_folder(self):
        """Check if this is a folder."""
        return self.file_type == 'folder'
    
    def get_children(self):
        """Get all child files/folders."""
        return self.children.all()
    
    def get_full_path(self):
        """Get the full hierarchical path."""
        if self.parent_folder:
            return f"{self.parent_folder.get_full_path()}/{self.file_name}"
        return self.file_name


class CodeGeneration(models.Model):
    """
    Code generation records from agent executions.
    Maps to code_generations table in Supabase.
    """
    OPERATION_CHOICES = [
        ('create', 'Create'),
        ('modify', 'Modify'),
        ('delete', 'Delete'),
        ('rename', 'Rename'),
    ]
    
    REVIEW_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('modified', 'Modified'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='code_generations',
        db_column='project_id'
    )
    feature = models.ForeignKey(
        'planning.Feature',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='code_generations',
        db_column='feature_id'
    )
    execution = models.ForeignKey(
        'agents.AgentExecution',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='code_generations',
        db_column='execution_id'
    )
    
    # File information
    file_path = models.TextField(help_text='Path to the file')
    operation = models.CharField(
        max_length=50,
        choices=OPERATION_CHOICES,
        null=True,
        blank=True
    )
    
    # Content
    old_content = models.TextField(blank=True, null=True, help_text='Original content before change')
    new_content = models.TextField(blank=True, null=True, help_text='New content after change')
    diff = models.TextField(blank=True, null=True, help_text='Unified diff of changes')
    language = models.CharField(max_length=50, blank=True, null=True)
    
    # Application status
    is_applied = models.BooleanField(default=False, null=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    
    # Review status
    review_status = models.CharField(
        max_length=50,
        choices=REVIEW_STATUS_CHOICES,
        default='pending',
        null=True
    )
    review_notes = models.TextField(blank=True, null=True)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    
    class Meta:
        db_table = 'code_generations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project']),
            models.Index(fields=['feature']),
            models.Index(fields=['is_applied']),
        ]
    
    def __str__(self):
        return f"{self.operation or 'Change'}: {self.file_path}"


class CodeAnalysis(TimeStampedModel):
    """
    Stores analysis results for code files.
    Extended metadata about code structure, dependencies, etc.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    context_file = models.OneToOneField(
        ContextFile,
        on_delete=models.CASCADE,
        related_name='analysis'
    )
    
    # Code structure
    functions = models.JSONField(default=list, help_text='List of functions found')
    classes = models.JSONField(default=list, help_text='List of classes found')
    imports = models.JSONField(default=list, help_text='List of imports/dependencies')
    exports = models.JSONField(default=list, help_text='List of exports')
    
    # Metrics
    lines_of_code = models.IntegerField(default=0)
    complexity_score = models.FloatField(null=True, blank=True)
    
    # Dependencies
    dependencies = models.JSONField(
        default=list,
        help_text='List of file dependencies'
    )
    dependent_files = models.JSONField(
        default=list,
        help_text='List of files that depend on this file'
    )
    
    # Analysis metadata
    analyzer_version = models.CharField(max_length=50, blank=True)
    analysis_date = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'code_analysis'
        verbose_name_plural = 'Code analyses'
    
    def __str__(self):
        return f"Analysis: {self.context_file.file_name}"


class FileIndex(TimeStampedModel):
    """
    Index of searchable content from files.
    For quick text search without vector embeddings.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    context_file = models.ForeignKey(
        ContextFile,
        on_delete=models.CASCADE,
        related_name='indices'
    )
    
    # Searchable content
    chunk_index = models.IntegerField(default=0, help_text='Chunk number for large files')
    content_chunk = models.TextField(help_text='Text chunk for searching')
    start_line = models.IntegerField(null=True, blank=True)
    end_line = models.IntegerField(null=True, blank=True)
    
    # Metadata
    chunk_metadata = models.JSONField(default=dict)
    
    class Meta:
        db_table = 'file_indices'
        ordering = ['context_file', 'chunk_index']
        indexes = [
            models.Index(fields=['context_file', 'chunk_index']),
        ]
    
    def __str__(self):
        return f"{self.context_file.file_name} - Chunk {self.chunk_index}"
