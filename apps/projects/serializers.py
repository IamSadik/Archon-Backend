from rest_framework import serializers
from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for Project model."""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Project
        fields = [
            'id', 'user', 'user_email', 'name', 'description',
            'repository_path', 'repository_url', 'language', 'framework',
            'status', 'is_active', 'settings', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
    
    def validate_settings(self, value):
        """Validate settings JSON structure."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Settings must be a dictionary")
        return value


class CreateProjectSerializer(serializers.ModelSerializer):
    """Serializer for creating a new project."""
    
    class Meta:
        model = Project
        fields = [
            'name', 'description', 'repository_path', 'repository_url',
            'language', 'framework', 'settings'
        ]
    
    def create(self, validated_data):
        """Create project with authenticated user."""
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)


class UpdateProjectSerializer(serializers.ModelSerializer):
    """Serializer for updating project details."""
    
    class Meta:
        model = Project
        fields = [
            'name', 'description', 'repository_path', 'repository_url',
            'language', 'framework', 'settings', 'status'
        ]


class ProjectListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing projects."""
    
    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'language', 'framework',
            'status', 'created_at', 'updated_at'
        ]
