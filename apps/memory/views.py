from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone
from apps.memory.models import ShortTermMemory, LongTermMemory, MemorySnapshot
from apps.memory.serializers import (
    ShortTermMemorySerializer,
    ShortTermMemoryCreateSerializer,
    LongTermMemorySerializer,
    LongTermMemoryCreateSerializer,
    MemorySnapshotSerializer,
    MemorySearchSerializer,
    MemoryConsolidationSerializer,
    MemoryCleanupSerializer
)
from apps.projects.models import Project


class ShortTermMemoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing short-term memory.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter memories by user."""
        queryset = ShortTermMemory.objects.filter(user=self.request.user)
        
        # Filter by project
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        # Filter by session
        session_id = self.request.query_params.get('session_id')
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        
        # Filter by memory type
        memory_type = self.request.query_params.get('memory_type')
        if memory_type:
            queryset = queryset.filter(memory_type=memory_type)
        
        # Exclude expired memories by default
        exclude_expired = self.request.query_params.get('exclude_expired', 'true')
        if exclude_expired.lower() == 'true':
            queryset = queryset.filter(expires_at__gt=timezone.now())
        
        return queryset.select_related('user', 'project')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return ShortTermMemoryCreateSerializer
        return ShortTermMemorySerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new short-term memory."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify project ownership
        project_id = serializer.validated_data['project'].id
        if not Project.objects.filter(id=project_id, user=request.user).exists():
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        memory = serializer.save()
        
        return Response(
            ShortTermMemorySerializer(memory).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def touch(self, request, pk=None):
        """Update last accessed timestamp."""
        memory = self.get_object()
        memory.touch()
        
        return Response(
            ShortTermMemorySerializer(memory).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['post'])
    def cleanup_expired(self, request):
        """Remove expired short-term memories."""
        project_id = request.data.get('project')
        
        queryset = ShortTermMemory.objects.filter(
            user=request.user,
            expires_at__lte=timezone.now()
        )
        
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        count = queryset.count()
        queryset.delete()
        
        return Response(
            {'deleted_count': count, 'message': f'Removed {count} expired memories'},
            status=status.HTTP_200_OK
        )


class LongTermMemoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing long-term memory.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter memories by user."""
        queryset = LongTermMemory.objects.filter(user=self.request.user)
        
        # Filter by project
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        # Filter by category
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(memory_category=category)
        
        # Filter by minimum importance
        min_importance = self.request.query_params.get('min_importance')
        if min_importance:
            queryset = queryset.filter(importance_score__gte=float(min_importance))
        
        return queryset.select_related('user', 'project')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return LongTermMemoryCreateSerializer
        return LongTermMemorySerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new long-term memory."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify project ownership
        project_id = serializer.validated_data['project'].id
        if not Project.objects.filter(id=project_id, user=request.user).exists():
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        memory = serializer.save()
        
        return Response(
            LongTermMemorySerializer(memory).data,
            status=status.HTTP_201_CREATED
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Retrieve memory and increment access count."""
        memory = self.get_object()
        memory.access()
        
        serializer = self.get_serializer(memory)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def boost_importance(self, request, pk=None):
        """Increase importance score."""
        memory = self.get_object()
        amount = request.data.get('amount', 0.1)
        
        memory.boost_importance(amount)
        
        return Response(
            LongTermMemorySerializer(memory).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def decay_importance(self, request, pk=None):
        """Decrease importance score."""
        memory = self.get_object()
        amount = request.data.get('amount', 0.05)
        
        memory.decay_importance(amount)
        
        return Response(
            LongTermMemorySerializer(memory).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['get'])
    def most_important(self, request):
        """Get most important memories."""
        limit = int(request.query_params.get('limit', 10))
        project_id = request.query_params.get('project')
        
        queryset = self.get_queryset()
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        memories = queryset.order_by('-importance_score', '-access_count')[:limit]
        serializer = self.get_serializer(memories, many=True)
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_category(self, request):
        """Get memories grouped by category."""
        project_id = request.query_params.get('project')
        
        queryset = self.get_queryset()
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        # Group by category
        categories = {}
        for memory in queryset:
            category = memory.memory_category or 'uncategorized'
            if category not in categories:
                categories[category] = []
            categories[category].append(LongTermMemorySerializer(memory).data)
        
        return Response(categories)


class MemoryManagementViewSet(viewsets.ViewSet):
    """
    ViewSet for memory management operations.
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def search(self, request):
        """Search across short-term and long-term memory."""
        serializer = MemorySearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        query = serializer.validated_data['query']
        project_id = serializer.validated_data.get('project')
        memory_type = serializer.validated_data.get('memory_type', 'both')
        category = serializer.validated_data.get('category')
        min_importance = serializer.validated_data.get('min_importance')
        limit = serializer.validated_data.get('limit', 20)
        
        results = {'short_term': [], 'long_term': []}
        
        # Search short-term memory
        if memory_type in ['short_term', 'both']:
            stm_queryset = ShortTermMemory.objects.filter(
                user=request.user,
                expires_at__gt=timezone.now()
            )
            
            if project_id:
                stm_queryset = stm_queryset.filter(project_id=project_id)
            
            # Search in memory_key and content
            stm_queryset = stm_queryset.filter(
                Q(memory_key__icontains=query) |
                Q(content__icontains=query)
            )[:limit]
            
            results['short_term'] = ShortTermMemorySerializer(stm_queryset, many=True).data
        
        # Search long-term memory
        if memory_type in ['long_term', 'both']:
            ltm_queryset = LongTermMemory.objects.filter(user=request.user)
            
            if project_id:
                ltm_queryset = ltm_queryset.filter(project_id=project_id)
            
            if category:
                ltm_queryset = ltm_queryset.filter(memory_category=category)
            
            if min_importance:
                ltm_queryset = ltm_queryset.filter(importance_score__gte=min_importance)
            
            # Search in memory_key and content
            ltm_queryset = ltm_queryset.filter(
                Q(memory_key__icontains=query) |
                Q(content__icontains=query)
            )[:limit]
            
            results['long_term'] = LongTermMemorySerializer(ltm_queryset, many=True).data
        
        return Response(results)
    
    @action(detail=False, methods=['post'])
    def consolidate(self, request):
        """Consolidate short-term memories into long-term memory."""
        serializer = MemoryConsolidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        session_id = serializer.validated_data['session_id']
        project_id = serializer.validated_data['project']
        importance_threshold = serializer.validated_data.get('importance_threshold', 0.6)
        categories = serializer.validated_data.get('categories', [])
        
        # Verify project ownership
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get short-term memories for session
        stm_memories = ShortTermMemory.objects.filter(
            user=request.user,
            project=project,
            session_id=session_id
        )
        
        # Filter by categories if specified
        if categories:
            stm_memories = stm_memories.filter(memory_type__in=categories)
        
        consolidated_count = 0
        for stm in stm_memories:
            # Only consolidate important memories
            if stm.memory_type in ['decision', 'context']:
                # Create long-term memory
                LongTermMemory.objects.create(
                    user=request.user,
                    project=project,
                    memory_key=stm.memory_key,
                    content=stm.content,
                    memory_category='pattern',  # Default category
                    importance_score=importance_threshold,
                    metadata={'consolidated_from': str(stm.id), 'session_id': str(session_id)}
                )
                consolidated_count += 1
        
        return Response(
            {
                'consolidated_count': consolidated_count,
                'message': f'Consolidated {consolidated_count} memories into long-term storage'
            },
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['post'])
    def cleanup(self, request):
        """Clean up expired and low-importance memories."""
        serializer = MemoryCleanupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        project_id = serializer.validated_data.get('project')
        cleanup_expired = serializer.validated_data.get('cleanup_expired', True)
        cleanup_low_importance = serializer.validated_data.get('cleanup_low_importance', False)
        importance_threshold = serializer.validated_data.get('importance_threshold', 0.2)
        
        deleted_counts = {'short_term': 0, 'long_term': 0}
        
        # Cleanup expired short-term memories
        if cleanup_expired:
            stm_queryset = ShortTermMemory.objects.filter(
                user=request.user,
                expires_at__lte=timezone.now()
            )
            
            if project_id:
                stm_queryset = stm_queryset.filter(project_id=project_id)
            
            deleted_counts['short_term'] = stm_queryset.count()
            stm_queryset.delete()
        
        # Cleanup low-importance long-term memories
        if cleanup_low_importance:
            ltm_queryset = LongTermMemory.objects.filter(
                user=request.user,
                importance_score__lt=importance_threshold
            )
            
            if project_id:
                ltm_queryset = ltm_queryset.filter(project_id=project_id)
            
            deleted_counts['long_term'] = ltm_queryset.count()
            ltm_queryset.delete()
        
        return Response(
            {
                'deleted_counts': deleted_counts,
                'message': f'Cleaned up {sum(deleted_counts.values())} memories'
            },
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['post'])
    def create_snapshot(self, request):
        """Create a snapshot of current memory state."""
        project_id = request.data.get('project')
        session_id = request.data.get('session_id')
        snapshot_name = request.data.get('snapshot_name', f'Snapshot {timezone.now()}')
        
        # Get current memories
        stm_data = list(
            ShortTermMemory.objects.filter(
                user=request.user,
                project_id=project_id,
                session_id=session_id if session_id else None
            ).values()
        )
        
        ltm_data = list(
            LongTermMemory.objects.filter(
                user=request.user,
                project_id=project_id
            ).values()
        )
        
        # Create snapshot
        snapshot = MemorySnapshot.objects.create(
            user=request.user,
            project_id=project_id,
            session_id=session_id,
            snapshot_name=snapshot_name,
            short_term_data={'memories': stm_data},
            long_term_data={'memories': ltm_data},
            metadata={
                'stm_count': len(stm_data),
                'ltm_count': len(ltm_data)
            }
        )
        
        return Response(
            MemorySnapshotSerializer(snapshot).data,
            status=status.HTTP_201_CREATED
        )


class MemorySnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing memory snapshots.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = MemorySnapshotSerializer
    
    def get_queryset(self):
        """Filter snapshots by user."""
        queryset = MemorySnapshot.objects.filter(user=self.request.user)
        
        # Filter by project
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        return queryset.select_related('user', 'project')
