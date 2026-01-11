"""
Vector Store serializers for API endpoints.
"""
from rest_framework import serializers
from apps.vector_store.models import EmbeddingDocument, SemanticSearchLog


class EmbeddingDocumentSerializer(serializers.ModelSerializer):
    """Serializer for embedding documents."""
    
    project_name = serializers.CharField(source='project.name', read_only=True)
    
    class Meta:
        model = EmbeddingDocument
        fields = [
            'id', 'project', 'project_name', 'document_type', 'source_id',
            'content', 'chunk_index', 'pinecone_id', 'namespace',
            'metadata', 'token_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'pinecone_id', 'created_at', 'updated_at']


class EmbeddingDocumentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing embeddings."""
    
    class Meta:
        model = EmbeddingDocument
        fields = [
            'id', 'project', 'document_type', 'source_id',
            'chunk_index', 'pinecone_id', 'created_at'
        ]


class EmbeddingCreateSerializer(serializers.Serializer):
    """Serializer for creating embeddings."""
    
    project = serializers.UUIDField()
    content = serializers.CharField()
    document_type = serializers.ChoiceField(choices=EmbeddingDocument.DOCUMENT_TYPES)
    source_id = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)
    namespace = serializers.CharField(required=False, allow_blank=True)


class BulkEmbeddingCreateSerializer(serializers.Serializer):
    """Serializer for bulk embedding creation."""
    
    project = serializers.UUIDField()
    documents = serializers.ListField(
        child=serializers.DictField(),
        help_text='List of documents with content, document_type, and optional metadata'
    )
    namespace = serializers.CharField(required=False, allow_blank=True)


class SemanticSearchSerializer(serializers.Serializer):
    """Serializer for semantic search requests."""
    
    query = serializers.CharField(required=True)
    project = serializers.UUIDField(required=True)
    top_k = serializers.IntegerField(default=5, min_value=1, max_value=100)
    document_type = serializers.ChoiceField(
        choices=EmbeddingDocument.DOCUMENT_TYPES,
        required=False
    )
    namespace = serializers.CharField(required=False, allow_blank=True)
    filters = serializers.JSONField(required=False, default=dict)
    include_content = serializers.BooleanField(default=True)


class SemanticSearchResultSerializer(serializers.Serializer):
    """Serializer for semantic search results."""
    
    id = serializers.UUIDField()
    pinecone_id = serializers.CharField()
    content = serializers.CharField()
    document_type = serializers.CharField()
    source_id = serializers.CharField()
    score = serializers.FloatField()
    metadata = serializers.JSONField()


class SemanticSearchLogSerializer(serializers.ModelSerializer):
    """Serializer for search logs."""
    
    class Meta:
        model = SemanticSearchLog
        fields = [
            'id', 'project', 'query', 'top_k', 'result_count',
            'result_ids', 'scores', 'latency_ms', 'namespace',
            'filters', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
