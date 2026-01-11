"""
Vector Store views for embedding and semantic search API endpoints.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.vector_store.models import EmbeddingDocument, SemanticSearchLog
from apps.vector_store.serializers import (
    EmbeddingDocumentSerializer,
    EmbeddingDocumentListSerializer,
    EmbeddingCreateSerializer,
    BulkEmbeddingCreateSerializer,
    SemanticSearchSerializer,
    SemanticSearchResultSerializer,
    SemanticSearchLogSerializer,
)
from apps.vector_store.services import EmbeddingService, SemanticSearchService
from apps.projects.models import Project


class EmbeddingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing embeddings.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter embeddings by user's projects."""
        queryset = EmbeddingDocument.objects.filter(
            project__user=self.request.user
        ).select_related('project')
        
        # Filter by project
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        # Filter by document type
        document_type = self.request.query_params.get('document_type')
        if document_type:
            queryset = queryset.filter(document_type=document_type)
        
        # Filter by source_id
        source_id = self.request.query_params.get('source_id')
        if source_id:
            queryset = queryset.filter(source_id=source_id)
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return EmbeddingDocumentListSerializer
        return EmbeddingDocumentSerializer
    
    @action(detail=False, methods=['post'])
    def create_embedding(self, request):
        """
        Create a new embedding from text content.
        """
        serializer = EmbeddingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify project ownership
        project_id = serializer.validated_data['project']
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create embedding
        try:
            embedding_service = EmbeddingService()
            embedding_doc = embedding_service.store_embedding(
                project=project,
                content=serializer.validated_data['content'],
                document_type=serializer.validated_data['document_type'],
                source_id=serializer.validated_data.get('source_id', ''),
                metadata=serializer.validated_data.get('metadata', {}),
                namespace=serializer.validated_data.get('namespace', '')
            )
            
            return Response(
                EmbeddingDocumentSerializer(embedding_doc).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def create_bulk(self, request):
        """
        Create multiple embeddings in bulk.
        """
        serializer = BulkEmbeddingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify project ownership
        project_id = serializer.validated_data['project']
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create embeddings
        try:
            embedding_service = EmbeddingService()
            embedding_docs = embedding_service.store_embeddings_bulk(
                project=project,
                documents=serializer.validated_data['documents'],
                namespace=serializer.validated_data.get('namespace', '')
            )
            
            return Response({
                'created': len(embedding_docs),
                'embeddings': EmbeddingDocumentListSerializer(embedding_docs, many=True).data
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'])
    def similar(self, request, pk=None):
        """
        Find similar embeddings to this one.
        """
        embedding_doc = self.get_object()
        top_k = int(request.query_params.get('top_k', 5))
        
        try:
            search_service = SemanticSearchService()
            results = search_service.search_similar(
                embedding_doc=embedding_doc,
                top_k=top_k
            )
            
            return Response({
                'source_id': str(embedding_doc.id),
                'results': results
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['delete'])
    def delete_with_vector(self, request, pk=None):
        """
        Delete embedding from both database and Pinecone.
        """
        embedding_doc = self.get_object()
        
        try:
            embedding_service = EmbeddingService()
            embedding_service.delete_embedding(embedding_doc)
            
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SemanticSearchViewSet(viewsets.ViewSet):
    """
    ViewSet for semantic search operations.
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def search(self, request):
        """
        Perform semantic search.
        """
        serializer = SemanticSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify project ownership
        project_id = serializer.validated_data['project']
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Perform search
        try:
            search_service = SemanticSearchService()
            results = search_service.search(
                query=serializer.validated_data['query'],
                project=project,
                top_k=serializer.validated_data.get('top_k', 5),
                document_type=serializer.validated_data.get('document_type'),
                namespace=serializer.validated_data.get('namespace'),
                filters=serializer.validated_data.get('filters', {}),
                include_content=serializer.validated_data.get('include_content', True)
            )
            
            return Response({
                'query': serializer.validated_data['query'],
                'result_count': len(results),
                'results': results
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def hybrid_search(self, request):
        """
        Perform hybrid search (semantic + keyword).
        """
        serializer = SemanticSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify project ownership
        project_id = serializer.validated_data['project']
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Perform hybrid search
        try:
            search_service = SemanticSearchService()
            results = search_service.hybrid_search(
                query=serializer.validated_data['query'],
                project=project,
                top_k=serializer.validated_data.get('top_k', 5)
            )
            
            return Response({
                'query': serializer.validated_data['query'],
                'result_count': len(results),
                'results': results
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def get_context(self, request):
        """
        Get relevant context for a query (formatted for LLM).
        """
        serializer = SemanticSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify project ownership
        project_id = serializer.validated_data['project']
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get context
        try:
            search_service = SemanticSearchService()
            context = search_service.get_context_for_query(
                query=serializer.validated_data['query'],
                project=project,
                max_tokens=request.data.get('max_tokens', 4000)
            )
            
            return Response({
                'query': serializer.validated_data['query'],
                'context': context
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SearchLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing search logs.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SemanticSearchLogSerializer
    
    def get_queryset(self):
        """Filter search logs by user's projects."""
        queryset = SemanticSearchLog.objects.filter(
            project__user=self.request.user
        ).select_related('project')
        
        # Filter by project
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        return queryset
