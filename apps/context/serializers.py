from rest_framework import serializers
from apps.context.models import ContextFile, CodeAnalysis, FileIndex


class ContextFileSerializer(serializers.ModelSerializer):
    """Serializer for context files."""
    
    project_name = serializers.CharField(source='project.name', read_only=True)
    is_code_file = serializers.BooleanField(read_only=True)
    is_folder = serializers.BooleanField(read_only=True)
    full_path = serializers.SerializerMethodField()
    
    class Meta:
        model = ContextFile
        fields = [
            'id', 'project', 'project_name', 'file_path', 'file_name',
            'file_type', 'file_extension', 'content', 'content_hash',
            'file_size_bytes', 'language', 'metadata', 'is_indexed',
            'embedding_id', 'parent_folder', 'is_code_file', 'is_folder',
            'full_path', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'content_hash', 'is_indexed', 'embedding_id', 'created_at', 'updated_at']
    
    def get_full_path(self, obj):
        """Get the full hierarchical path."""
        return obj.get_full_path()


class ContextFileListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing context files."""
    
    project_name = serializers.CharField(source='project.name', read_only=True)
    
    class Meta:
        model = ContextFile
        fields = [
            'id', 'project', 'project_name', 'file_path', 'file_name',
            'file_type', 'file_extension', 'file_size_bytes', 'language',
            'is_indexed', 'created_at'
        ]


class ContextFileCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating context files."""
    
    class Meta:
        model = ContextFile
        fields = [
            'project', 'file_path', 'file_name', 'file_type',
            'file_extension', 'content', 'file_size_bytes',
            'language', 'metadata', 'parent_folder'
        ]
    
    def create(self, validated_data):
        """Create context file and compute content hash."""
        import hashlib
        
        content = validated_data.get('content', '')
        if content:
            # Compute SHA-256 hash
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            validated_data['content_hash'] = content_hash
        
        return super().create(validated_data)


class CodeAnalysisSerializer(serializers.ModelSerializer):
    """Serializer for code analysis results."""
    
    file_name = serializers.CharField(source='context_file.file_name', read_only=True)
    file_path = serializers.CharField(source='context_file.file_path', read_only=True)
    
    class Meta:
        model = CodeAnalysis
        fields = [
            'id', 'context_file', 'file_name', 'file_path',
            'functions', 'classes', 'imports', 'exports',
            'lines_of_code', 'complexity_score', 'dependencies',
            'dependent_files', 'analyzer_version', 'analysis_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'analysis_date', 'created_at', 'updated_at']


class FileIndexSerializer(serializers.ModelSerializer):
    """Serializer for file index chunks."""
    
    file_name = serializers.CharField(source='context_file.file_name', read_only=True)
    
    class Meta:
        model = FileIndex
        fields = [
            'id', 'context_file', 'file_name', 'chunk_index',
            'content_chunk', 'start_line', 'end_line',
            'chunk_metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FileUploadSerializer(serializers.Serializer):
    """Serializer for file upload."""
    
    project = serializers.UUIDField()
    file = serializers.FileField()
    file_path = serializers.CharField(required=False)
    parent_folder = serializers.UUIDField(required=False, allow_null=True)
    
    def validate_file(self, value):
        """Validate file size and type."""
        # Max file size: 10MB
        max_size = 10 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size exceeds maximum allowed size of {max_size / (1024*1024)}MB"
            )
        return value


class DirectoryIndexSerializer(serializers.Serializer):
    """Serializer for indexing a directory."""
    
    project = serializers.UUIDField()
    directory_path = serializers.CharField()
    recursive = serializers.BooleanField(default=True)
    include_patterns = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="File patterns to include (e.g., ['*.py', '*.js'])"
    )
    exclude_patterns = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="File patterns to exclude (e.g., ['*.pyc', 'node_modules'])"
    )
    analyze_code = serializers.BooleanField(
        default=True,
        help_text="Whether to perform code analysis"
    )


class FileSearchSerializer(serializers.Serializer):
    """Serializer for searching files."""
    
    query = serializers.CharField(required=True)
    project = serializers.UUIDField(required=False)
    file_type = serializers.ChoiceField(
        choices=ContextFile.FILE_TYPES,
        required=False
    )
    language = serializers.ChoiceField(
        choices=ContextFile.PROGRAMMING_LANGUAGES,
        required=False
    )
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)
