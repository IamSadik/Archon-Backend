from rest_framework import serializers
from apps.memory.models import ShortTermMemory, LongTermMemory, MemorySnapshot


class ShortTermMemorySerializer(serializers.ModelSerializer):
    """Serializer for short-term memory."""
    
    user_email = serializers.CharField(source='user.email', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = ShortTermMemory
        fields = [
            'id', 'user', 'user_email', 'project', 'project_name',
            'session_id', 'memory_key', 'content', 'memory_type',
            'ttl_seconds', 'expires_at', 'is_expired',
            'created_at', 'accessed_at'
        ]
        read_only_fields = ['id', 'expires_at', 'created_at', 'accessed_at']


class ShortTermMemoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating short-term memory."""
    
    class Meta:
        model = ShortTermMemory
        fields = [
            'project', 'session_id', 'memory_key', 'content',
            'memory_type', 'ttl_seconds'
        ]
    
    def create(self, validated_data):
        """Create memory with user from context."""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class LongTermMemorySerializer(serializers.ModelSerializer):
    """Serializer for long-term memory."""
    
    user_email = serializers.CharField(source='user.email', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    
    class Meta:
        model = LongTermMemory
        fields = [
            'id', 'user', 'user_email', 'project', 'project_name',
            'memory_key', 'content', 'memory_category',
            'importance_score', 'access_count', 'embedding_id',
            'metadata', 'last_accessed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'access_count', 'embedding_id',
            'last_accessed_at', 'created_at', 'updated_at'
        ]


class LongTermMemoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating long-term memory."""
    
    class Meta:
        model = LongTermMemory
        fields = [
            'project', 'memory_key', 'content', 'memory_category',
            'importance_score', 'metadata'
        ]
    
    def create(self, validated_data):
        """Create memory with user from context."""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class MemorySnapshotSerializer(serializers.ModelSerializer):
    """Serializer for memory snapshots."""
    
    user_email = serializers.CharField(source='user.email', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    
    class Meta:
        model = MemorySnapshot
        fields = [
            'id', 'user', 'user_email', 'project', 'project_name',
            'session_id', 'snapshot_name', 'short_term_data',
            'long_term_data', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MemorySearchSerializer(serializers.Serializer):
    """Serializer for memory search requests."""
    
    query = serializers.CharField(required=True)
    project = serializers.UUIDField(required=False)
    memory_type = serializers.ChoiceField(
        choices=['short_term', 'long_term', 'both'],
        default='both'
    )
    category = serializers.ChoiceField(
        choices=LongTermMemory.MEMORY_CATEGORIES,
        required=False
    )
    min_importance = serializers.FloatField(
        required=False,
        min_value=0.0,
        max_value=1.0
    )
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)


class MemoryConsolidationSerializer(serializers.Serializer):
    """Serializer for memory consolidation requests."""
    
    session_id = serializers.UUIDField(required=True)
    project = serializers.UUIDField(required=True)
    importance_threshold = serializers.FloatField(
        default=0.6,
        min_value=0.0,
        max_value=1.0,
        help_text='Minimum importance score for consolidation'
    )
    categories = serializers.ListField(
        child=serializers.ChoiceField(choices=LongTermMemory.MEMORY_CATEGORIES),
        required=False,
        help_text='Categories to consolidate into long-term memory'
    )


class MemoryCleanupSerializer(serializers.Serializer):
    """Serializer for memory cleanup requests."""
    
    project = serializers.UUIDField(required=False)
    cleanup_expired = serializers.BooleanField(
        default=True,
        help_text='Remove expired short-term memories'
    )
    cleanup_low_importance = serializers.BooleanField(
        default=False,
        help_text='Remove low importance long-term memories'
    )
    importance_threshold = serializers.FloatField(
        default=0.2,
        min_value=0.0,
        max_value=1.0,
        help_text='Threshold for low importance cleanup'
    )
