from rest_framework import serializers
from apps.planning.models import ProjectPlan, Feature, Task


class TaskSerializer(serializers.ModelSerializer):
    """Serializer for tasks."""
    
    class Meta:
        model = Task
        fields = [
            'id', 'feature', 'title', 'description', 'task_type',
            'status', 'order_index', 'result', 'error_message',
            'execution_time_seconds', 'completed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'completed_at', 'created_at', 'updated_at']


class FeatureSerializer(serializers.ModelSerializer):
    """Serializer for features with nested tasks."""
    
    tasks = TaskSerializer(many=True, read_only=True)
    children_count = serializers.SerializerMethodField()
    is_root = serializers.BooleanField(read_only=True)
    is_leaf = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Feature
        fields = [
            'id', 'plan', 'parent', 'name', 'description', 'status',
            'depth_level', 'order_index', 'priority', 'estimated_effort',
            'actual_effort_minutes', 'dependencies', 'blocking_reason',
            'related_files', 'related_memories', 'metadata',
            'started_at', 'completed_at', 'last_activity_at',
            'tasks', 'children_count', 'is_root', 'is_leaf',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'started_at', 'completed_at', 'last_activity_at',
            'created_at', 'updated_at'
        ]
    
    def get_children_count(self, obj):
        """Get count of child features."""
        return obj.children.count()


class FeatureTreeSerializer(serializers.ModelSerializer):
    """Serializer for feature tree with recursive children."""
    
    children = serializers.SerializerMethodField()
    tasks = TaskSerializer(many=True, read_only=True)
    
    class Meta:
        model = Feature
        fields = [
            'id', 'name', 'description', 'status', 'priority',
            'estimated_effort', 'depth_level', 'order_index',
            'children', 'tasks', 'started_at', 'completed_at'
        ]
    
    def get_children(self, obj):
        """Recursively serialize children."""
        children = obj.get_children()
        return FeatureTreeSerializer(children, many=True).data


class ProjectPlanSerializer(serializers.ModelSerializer):
    """Serializer for project plans."""
    
    project_name = serializers.CharField(source='project.name', read_only=True)
    completion_percentage = serializers.FloatField(read_only=True)
    
    class Meta:
        model = ProjectPlan
        fields = [
            'id', 'project', 'project_name', 'plan_version',
            'tree_structure', 'total_features', 'completed_features',
            'active_feature', 'metadata', 'completion_percentage',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_features', 'completed_features',
            'completion_percentage', 'created_at', 'updated_at'
        ]


class ProjectPlanDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for project plans with root features."""
    
    project_name = serializers.CharField(source='project.name', read_only=True)
    completion_percentage = serializers.FloatField(read_only=True)
    root_features = serializers.SerializerMethodField()
    
    class Meta:
        model = ProjectPlan
        fields = [
            'id', 'project', 'project_name', 'plan_version',
            'tree_structure', 'total_features', 'completed_features',
            'active_feature', 'metadata', 'completion_percentage',
            'root_features', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_features', 'completed_features',
            'completion_percentage', 'created_at', 'updated_at'
        ]
    
    def get_root_features(self, obj):
        """Get all root-level features."""
        root_features = obj.features.filter(parent=None).order_by('order_index')
        return FeatureTreeSerializer(root_features, many=True).data


class FeatureCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating features."""
    
    class Meta:
        model = Feature
        fields = [
            'plan', 'parent', 'name', 'description', 'priority',
            'estimated_effort', 'order_index', 'dependencies',
            'related_files', 'related_memories', 'metadata'
        ]
    
    def create(self, validated_data):
        """Create feature and set depth level."""
        parent = validated_data.get('parent')
        if parent:
            validated_data['depth_level'] = parent.depth_level + 1
        else:
            validated_data['depth_level'] = 0
        
        feature = super().create(validated_data)
        
        # Update plan statistics
        feature.plan.update_stats()
        
        return feature


class TaskCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating tasks."""
    
    class Meta:
        model = Task
        fields = [
            'feature', 'title', 'description', 'task_type', 'order_index'
        ]


class FeatureStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating feature status."""
    
    status = serializers.ChoiceField(choices=Feature.STATUS_CHOICES)
    blocking_reason = serializers.CharField(required=False, allow_blank=True)


class TaskStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating task status."""
    
    status = serializers.ChoiceField(choices=Task.STATUS_CHOICES)
    result = serializers.JSONField(required=False)
    error_message = serializers.CharField(required=False, allow_blank=True)
    execution_time_seconds = serializers.IntegerField(required=False)


class FeatureMoveSerializer(serializers.Serializer):
    """Serializer for moving features in the tree."""
    
    new_parent = serializers.UUIDField(required=False, allow_null=True)
    new_order_index = serializers.IntegerField(required=True)


class PlanGenerationSerializer(serializers.Serializer):
    """Serializer for AI-generated plan creation."""
    
    project = serializers.UUIDField(required=True)
    user_requirements = serializers.CharField(required=True)
    include_tasks = serializers.BooleanField(default=True)
    max_features = serializers.IntegerField(default=10, min_value=1, max_value=50)
