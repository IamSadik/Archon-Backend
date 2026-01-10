from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Project
from .serializers import (
    ProjectSerializer, CreateProjectSerializer, 
    UpdateProjectSerializer, ProjectListSerializer
)


class ProjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing projects.
    Provides CRUD operations and additional actions.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return projects for authenticated user only."""
        return Project.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return CreateProjectSerializer
        elif self.action in ['update', 'partial_update']:
            return UpdateProjectSerializer
        elif self.action == 'list':
            return ProjectListSerializer
        return ProjectSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new project."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        
        return Response(
            ProjectSerializer(project).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Archive a project."""
        project = self.get_object()
        project.archive()
        
        return Response({
            'message': 'Project archived successfully',
            'project': ProjectSerializer(project).data
        })
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate an archived project."""
        project = self.get_object()
        project.activate()
        
        return Response({
            'message': 'Project activated successfully',
            'project': ProjectSerializer(project).data
        })
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active projects."""
        projects = self.get_queryset().filter(status='active')
        serializer = ProjectListSerializer(projects, many=True)
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def archived(self, request):
        """Get all archived projects."""
        projects = self.get_queryset().filter(status='archived')
        serializer = ProjectListSerializer(projects, many=True)
        
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get project statistics."""
        project = self.get_object()
        
        # You can expand this with actual stats from related models
        stats = {
            'project_id': str(project.id),
            'name': project.name,
            'status': project.status,
            'created_at': project.created_at,
            'settings': project.settings,
        }
        
        return Response(stats)
