from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count
from apps.planning.models import ProjectPlan, Feature, Task
from apps.planning.serializers import (
    ProjectPlanSerializer,
    ProjectPlanDetailSerializer,
    FeatureSerializer,
    FeatureCreateSerializer,
    FeatureTreeSerializer,
    TaskSerializer,
    TaskCreateSerializer,
    FeatureStatusUpdateSerializer,
    TaskStatusUpdateSerializer,
    FeatureMoveSerializer,
    PlanGenerationSerializer
)
from apps.planning.services import PlanningService, PlannerOrchestrator
from apps.projects.models import Project


class ProjectPlanViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing project plans.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter plans by user's projects."""
        return ProjectPlan.objects.filter(
            project__user=self.request.user
        ).select_related('project', 'active_feature')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return ProjectPlanDetailSerializer
        return ProjectPlanSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new project plan."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify project ownership
        project_id = serializer.validated_data['project'].id
        try:
            project = Project.objects.get(id=project_id, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if plan already exists
        if hasattr(project, 'plan'):
            return Response(
                {'error': 'Project already has a plan'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        plan = serializer.save()
        
        return Response(
            ProjectPlanDetailSerializer(plan).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['get'])
    def tree(self, request, pk=None):
        """Get the complete feature tree."""
        plan = self.get_object()
        root_features = plan.features.filter(parent=None).order_by('order_index')
        
        tree_data = FeatureTreeSerializer(root_features, many=True).data
        
        return Response({
            'plan_id': plan.id,
            'project_name': plan.project.name,
            'total_features': plan.total_features,
            'completed_features': plan.completed_features,
            'completion_percentage': plan.completion_percentage,
            'tree': tree_data
        })
    
    @action(detail=True, methods=['post'])
    def set_active_feature(self, request, pk=None):
        """Set the currently active feature."""
        plan = self.get_object()
        feature_id = request.data.get('feature_id')
        
        try:
            feature = Feature.objects.get(id=feature_id, plan=plan)
            plan.active_feature = feature
            plan.save()
            
            return Response(
                ProjectPlanDetailSerializer(plan).data,
                status=status.HTTP_200_OK
            )
        except Feature.DoesNotExist:
            return Response(
                {'error': 'Feature not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get plan statistics."""
        plan = self.get_object()
        
        features_by_status = plan.features.values('status').annotate(
            count=Count('id')
        )
        
        tasks_by_status = Task.objects.filter(
            feature__plan=plan
        ).values('status').annotate(
            count=Count('id')
        )
        
        return Response({
            'plan_id': plan.id,
            'total_features': plan.total_features,
            'completed_features': plan.completed_features,
            'completion_percentage': plan.completion_percentage,
            'features_by_status': list(features_by_status),
            'tasks_by_status': list(tasks_by_status),
            'plan_version': plan.plan_version
        })
    
    @action(detail=True, methods=['post'])
    def process_message(self, request, pk=None):
        """
        Process a user message through the planning orchestrator.
        This is the main entry point for AI-assisted planning.
        """
        plan = self.get_object()
        message = request.data.get('message', '')
        session_context = request.data.get('context', {})
        
        if not message:
            return Response(
                {'error': 'Message is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            orchestrator = PlannerOrchestrator(request.user, plan.project)
            result = orchestrator.process_message(message, session_context)
            
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def restore_session(self, request, pk=None):
        """
        Restore a previous planning session.
        Called when user returns to continue work.
        """
        plan = self.get_object()
        
        try:
            orchestrator = PlannerOrchestrator(request.user, plan.project)
            result = orchestrator.restore_session()
            
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def planning_context(self, request, pk=None):
        """
        Get planning context for the executor agent.
        """
        plan = self.get_object()
        
        try:
            orchestrator = PlannerOrchestrator(request.user, plan.project)
            context = orchestrator.get_planning_context_for_executor()
            
            return Response(context, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def report_task_completion(self, request, pk=None):
        """
        Report task completion from executor.
        """
        plan = self.get_object()
        task_id = request.data.get('task_id')
        result = request.data.get('result')
        
        if not task_id:
            return Response(
                {'error': 'task_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            orchestrator = PlannerOrchestrator(request.user, plan.project)
            response = orchestrator.report_task_completion(task_id, result)
            
            return Response(response, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def report_task_failure(self, request, pk=None):
        """
        Report task failure from executor.
        """
        plan = self.get_object()
        task_id = request.data.get('task_id')
        error = request.data.get('error', 'Unknown error')
        
        if not task_id:
            return Response(
                {'error': 'task_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            orchestrator = PlannerOrchestrator(request.user, plan.project)
            response = orchestrator.report_task_failure(task_id, error)
            
            return Response(response, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def switch_feature(self, request, pk=None):
        """
        Switch from one feature to another.
        """
        plan = self.get_object()
        from_feature_id = request.data.get('from_feature_id')
        to_feature_id = request.data.get('to_feature_id')
        
        if not to_feature_id:
            return Response(
                {'error': 'to_feature_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            planning_service = PlanningService(request.user, plan.project)
            
            if from_feature_id:
                result = planning_service.switch_feature(from_feature_id, to_feature_id)
            else:
                # Just resume the target feature
                feature, context = planning_service.resume_feature(to_feature_id)
                result = {
                    'switched': True,
                    'to_feature': {
                        'id': str(feature.id),
                        'name': feature.name,
                        'status': feature.status,
                        'resume_context': context
                    }
                }
            
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def resumable_features(self, request, pk=None):
        """
        Get all features that can be resumed.
        """
        plan = self.get_object()
        
        try:
            planning_service = PlanningService(request.user, plan.project)
            features = planning_service.get_resumable_features()
            
            return Response({
                'resumable_features': features
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def next_suggestions(self, request, pk=None):
        """
        Get suggested features to work on next.
        """
        plan = self.get_object()
        limit = int(request.query_params.get('limit', 5))
        
        try:
            planning_service = PlanningService(request.user, plan.project)
            suggestions = planning_service.get_next_suggested_features(limit=limit)
            
            return Response({
                'suggestions': suggestions
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FeatureViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing features.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter features by user's projects."""
        queryset = Feature.objects.filter(
            plan__project__user=self.request.user
        ).select_related('plan', 'parent')
        
        # Filter by plan
        plan_id = self.request.query_params.get('plan')
        if plan_id:
            queryset = queryset.filter(plan_id=plan_id)
        
        # Filter by status
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by parent (get children of specific feature)
        parent_id = self.request.query_params.get('parent')
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        elif self.request.query_params.get('root_only') == 'true':
            queryset = queryset.filter(parent=None)
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return FeatureCreateSerializer
        return FeatureSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new feature."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify plan ownership
        plan_id = serializer.validated_data['plan'].id
        if not ProjectPlan.objects.filter(
            id=plan_id,
            project__user=request.user
        ).exists():
            return Response(
                {'error': 'Plan not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        feature = serializer.save()
        
        return Response(
            FeatureSerializer(feature).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update feature status."""
        feature = self.get_object()
        serializer = FeatureStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        new_status = serializer.validated_data['status']
        blocking_reason = serializer.validated_data.get('blocking_reason', '')
        
        if new_status == 'in_progress':
            feature.mark_in_progress()
        elif new_status == 'completed':
            feature.mark_completed()
        elif new_status == 'blocked':
            feature.mark_blocked(blocking_reason)
        else:
            feature.status = new_status
            feature.save()
        
        return Response(
            FeatureSerializer(feature).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def move(self, request, pk=None):
        """Move feature to new parent or position."""
        feature = self.get_object()
        serializer = FeatureMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        new_parent_id = serializer.validated_data.get('new_parent')
        new_order = serializer.validated_data['new_order_index']
        
        # Update parent and depth
        if new_parent_id:
            new_parent = Feature.objects.get(id=new_parent_id, plan=feature.plan)
            feature.parent = new_parent
            feature.depth_level = new_parent.depth_level + 1
        else:
            feature.parent = None
            feature.depth_level = 0
        
        feature.order_index = new_order
        feature.save()
        
        return Response(
            FeatureSerializer(feature).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['get'])
    def children(self, request, pk=None):
        """Get all children of a feature."""
        feature = self.get_object()
        children = feature.get_children()
        
        serializer = FeatureSerializer(children, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def descendants(self, request, pk=None):
        """Get all descendants of a feature."""
        feature = self.get_object()
        descendants = feature.get_descendants()
        
        serializer = FeatureSerializer(descendants, many=True)
        return Response(serializer.data)


class TaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tasks.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter tasks by user's projects."""
        queryset = Task.objects.filter(
            feature__plan__project__user=self.request.user
        ).select_related('feature')
        
        # Filter by feature
        feature_id = self.request.query_params.get('feature')
        if feature_id:
            queryset = queryset.filter(feature_id=feature_id)
        
        # Filter by status
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return TaskCreateSerializer
        return TaskSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new task."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Verify feature ownership
        feature_id = serializer.validated_data['feature'].id
        if not Feature.objects.filter(
            id=feature_id,
            plan__project__user=request.user
        ).exists():
            return Response(
                {'error': 'Feature not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        task = serializer.save()
        
        return Response(
            TaskSerializer(task).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update task status."""
        task = self.get_object()
        serializer = TaskStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        new_status = serializer.validated_data['status']
        
        if new_status == 'completed':
            result = serializer.validated_data.get('result')
            task.mark_completed(result)
        elif new_status == 'failed':
            error_message = serializer.validated_data.get('error_message', '')
            task.mark_failed(error_message)
        else:
            task.status = new_status
            
        # Update execution time if provided
        exec_time = serializer.validated_data.get('execution_time_seconds')
        if exec_time:
            task.execution_time_seconds = exec_time
        
        task.save()
        
        return Response(
            TaskSerializer(task).data,
            status=status.HTTP_200_OK
        )
