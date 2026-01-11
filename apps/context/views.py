from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from apps.context.models import ContextFile, CodeAnalysis, FileIndex
from apps.context.serializers import (
    ContextFileSerializer,
    ContextFileListSerializer,
    ContextFileCreateSerializer,
    CodeAnalysisSerializer,
    FileIndexSerializer,
    FileUploadSerializer,
    DirectoryIndexSerializer,
    FileSearchSerializer
)
from apps.projects.models import Project


class ContextFileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing context files.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter files by user's projects."""
        user = self.request.user
        queryset = ContextFile.objects.filter(project__user=user)
        
        # Filter by project
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        # Filter by file type
        file_type = self.request.query_params.get('file_type')
        if file_type:
            queryset = queryset.filter(file_type=file_type)
        
        # Filter by language
        language = self.request.query_params.get('language')
        if language:
            queryset = queryset.filter(language=language)
        
        # Filter by indexed status
        is_indexed = self.request.query_params.get('is_indexed')
        if is_indexed is not None:
            queryset = queryset.filter(is_indexed=is_indexed.lower() == 'true')
        
        return queryset.select_related('project')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return ContextFileListSerializer
        elif self.action == 'create':
            return ContextFileCreateSerializer
        return ContextFileSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new context file."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify project ownership
        project_id = serializer.validated_data['project'].id
        if not Project.objects.filter(id=project_id, user=request.user).exists():
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        context_file = serializer.save()
        
        return Response(
            ContextFileSerializer(context_file).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['post'])
    def upload(self, request):
        """
        Upload a file to the context.
        """
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        project_id = serializer.validated_data['project']
        uploaded_file = serializer.validated_data['file']
        file_path = serializer.validated_data.get('file_path', uploaded_file.name)
        parent_folder_id = serializer.validated_data.get('parent_folder')
        
        # Verify project ownership
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Read file content and handle binary files
        try:
            content = uploaded_file.read().decode('utf-8', errors='replace')
            # Remove NULL bytes that can cause database issues
            content = content.replace('\x00', '')
        except Exception as e:
            return Response(
                {'error': f'Failed to read file content: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine file type and language
        import os
        file_extension = os.path.splitext(uploaded_file.name)[1].lstrip('.')
        file_type = self._determine_file_type(file_extension)
        language = self._determine_language(file_extension) if file_type == 'code' else None
        
        # Compute content hash
        import hashlib
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        # Create context file
        context_file = ContextFile.objects.create(
            project=project,
            file_path=file_path,
            file_name=uploaded_file.name,
            file_type=file_type,
            file_extension=file_extension,
            content=content,
            content_hash=content_hash,
            file_size_bytes=uploaded_file.size,
            language=language,
            parent_folder_id=parent_folder_id
        )
        
        return Response(
            ContextFileSerializer(context_file).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['post'])
    def index_directory(self, request):
        """
        Index all files in a directory.
        """
        serializer = DirectoryIndexSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        project_id = serializer.validated_data['project']
        directory_path = serializer.validated_data['directory_path']
        recursive = serializer.validated_data.get('recursive', True)
        include_patterns = serializer.validated_data.get('include_patterns', [])
        exclude_patterns = serializer.validated_data.get('exclude_patterns', [])
        analyze_code = serializer.validated_data.get('analyze_code', True)
        
        # Verify project ownership
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Index directory (this will be implemented in the service layer)
        from apps.context.services.file_indexer import FileIndexerService
        
        try:
            indexer = FileIndexerService(project)
            result = indexer.index_directory(
                directory_path,
                recursive=recursive,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                analyze_code=analyze_code
            )
            
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def search(self, request):
        """
        Search for files by content or metadata.
        """
        serializer = FileSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        query = serializer.validated_data['query']
        project_id = serializer.validated_data.get('project')
        file_type = serializer.validated_data.get('file_type')
        language = serializer.validated_data.get('language')
        limit = serializer.validated_data.get('limit', 20)
        
        # Build query
        queryset = ContextFile.objects.filter(project__user=request.user)
        
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        if file_type:
            queryset = queryset.filter(file_type=file_type)
        
        if language:
            queryset = queryset.filter(language=language)
        
        # Search in file name, path, and content
        queryset = queryset.filter(
            Q(file_name__icontains=query) |
            Q(file_path__icontains=query) |
            Q(content__icontains=query)
        )[:limit]
        
        serializer = ContextFileListSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def analysis(self, request, pk=None):
        """
        Get code analysis for a file.
        """
        context_file = self.get_object()
        
        try:
            analysis = context_file.analysis
            serializer = CodeAnalysisSerializer(analysis)
            return Response(serializer.data)
        except CodeAnalysis.DoesNotExist:
            return Response(
                {'error': 'No analysis available for this file'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def analyze(self, request, pk=None):
        """
        Trigger code analysis for a file.
        """
        context_file = self.get_object()
        
        if not context_file.is_code_file:
            return Response(
                {'error': 'Can only analyze code files'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Trigger analysis (this will be implemented in the service layer)
        from apps.context.services.code_analyzer import CodeAnalyzerService
        
        try:
            analyzer = CodeAnalyzerService()
            analysis = analyzer.analyze_file(context_file)
            
            serializer = CodeAnalysisSerializer(analysis)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'])
    def children(self, request, pk=None):
        """
        Get all children of a folder.
        """
        context_file = self.get_object()
        
        if not context_file.is_folder:
            return Response(
                {'error': 'This is not a folder'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        children = context_file.get_children()
        serializer = ContextFileListSerializer(children, many=True)
        return Response(serializer.data)
    
    def _determine_file_type(self, extension):
        """Determine file type from extension."""
        code_extensions = {
            'py', 'js', 'ts', 'java', 'cpp', 'c', 'h', 'cs', 'go',
            'rs', 'php', 'rb', 'swift', 'kt', 'scala', 'html', 'css',
            'jsx', 'tsx', 'vue', 'sql'
        }
        
        if extension in code_extensions:
            return 'code'
        elif extension == 'pdf':
            return 'pdf'
        elif extension in ['doc', 'docx']:
            return 'doc'
        elif extension == 'md':
            return 'md'
        elif extension == 'json':
            return 'json'
        elif extension in ['yaml', 'yml']:
            return 'yaml'
        elif extension == 'xml':
            return 'xml'
        elif extension in ['png', 'jpg', 'jpeg', 'gif', 'svg']:
            return 'image'
        elif extension == 'txt':
            return 'txt'
        else:
            return 'other'
    
    def _determine_language(self, extension):
        """Determine programming language from extension."""
        language_map = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'java': 'java',
            'cpp': 'cpp',
            'c': 'cpp',
            'h': 'cpp',
            'cs': 'csharp',
            'go': 'go',
            'rs': 'rust',
            'php': 'php',
            'rb': 'ruby',
            'swift': 'swift',
            'kt': 'kotlin',
            'sql': 'sql',
            'html': 'html',
            'css': 'css',
        }
        
        return language_map.get(extension, 'other')


class CodeAnalysisViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing code analysis results.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CodeAnalysisSerializer
    
    def get_queryset(self):
        """Filter analyses by user's projects."""
        return CodeAnalysis.objects.filter(
            context_file__project__user=self.request.user
        ).select_related('context_file', 'context_file__project')
