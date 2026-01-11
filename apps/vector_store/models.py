"""
Vector Store models for managing embeddings and semantic search.
"""
import uuid
from django.db import models
from apps.core.models import TimeStampedModel
from apps.projects.models import Project


class EmbeddingDocument(TimeStampedModel):
    """
    Represents a document chunk stored as an embedding.
    Maps to the local database record that references Pinecone vectors.
    """
    DOCUMENT_TYPES = [
        ('code', 'Code'),
        ('documentation', 'Documentation'),
        ('conversation', 'Conversation'),
        ('memory', 'Memory'),
        ('planning', 'Planning'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='embeddings'
    )
    
    # Document identification
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    source_id = models.CharField(
        max_length=255,
        help_text='ID of the source document (context_file_id, conversation_id, etc.)'
    )
    
    # Content
    content = models.TextField(help_text='The text content that was embedded')
    chunk_index = models.IntegerField(default=0, help_text='Chunk number for large documents')
    
    # Pinecone reference
    pinecone_id = models.CharField(
        max_length=255,
        unique=True,
        help_text='Pinecone vector ID'
    )
    namespace = models.CharField(
        max_length=255,
        default='',
        help_text='Pinecone namespace for isolation'
    )
    
    # Metadata
    metadata = models.JSONField(default=dict)
    token_count = models.IntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'embedding_documents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'document_type']),
            models.Index(fields=['pinecone_id']),
            models.Index(fields=['source_id']),
        ]
    
    def __str__(self):
        return f"{self.document_type}: {self.content[:50]}..."


class EmbeddingsMetadata(models.Model):
    """
    Metadata for embeddings stored in the vector database.
    Maps to embeddings_metadata table in Supabase.
    """
    SOURCE_TYPES = [
        ('code', 'Code'),
        ('document', 'Document'),
        ('conversation', 'Conversation'),
        ('memory', 'Memory'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vector_id = models.CharField(
        max_length=255,
        unique=True,
        help_text='Vector ID in Pinecone'
    )
    source_type = models.CharField(max_length=100, choices=SOURCE_TYPES)
    source_id = models.UUIDField(help_text='ID of the source record')
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='embeddings_metadata',
        null=True,
        blank=True,
        db_column='project_id'
    )
    content_preview = models.TextField(
        blank=True,
        null=True,
        help_text='Preview of the embedded content'
    )
    embedding_model = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Model used for embedding'
    )
    metadata = models.JSONField(default=dict, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    
    class Meta:
        db_table = 'embeddings_metadata'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vector_id']),
            models.Index(fields=['source_type']),
            models.Index(fields=['project']),
        ]
    
    def __str__(self):
        return f"{self.source_type}: {self.vector_id}"


class SemanticSearchLog(TimeStampedModel):
    """
    Logs semantic search queries for analytics and optimization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='search_logs'
    )
    
    # Query information
    query = models.TextField(help_text='The search query text')
    top_k = models.IntegerField(default=5)
    
    # Results
    result_count = models.IntegerField(default=0)
    result_ids = models.JSONField(default=list, help_text='List of returned embedding IDs')
    scores = models.JSONField(default=list, help_text='Similarity scores')
    
    # Performance
    latency_ms = models.IntegerField(null=True, blank=True)
    
    # Context
    namespace = models.CharField(max_length=255, default='')
    filters = models.JSONField(default=dict)
    
    class Meta:
        db_table = 'semantic_search_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
        ]
    
    def __str__(self):
        return f"Search: {self.query[:50]}... ({self.result_count} results)"
