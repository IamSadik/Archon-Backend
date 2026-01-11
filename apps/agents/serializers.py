from rest_framework import serializers
from apps.agents.models import AgentSession, AgentExecution, ToolCall


class ToolCallSerializer(serializers.ModelSerializer):
    """Serializer for tool calls."""
    
    class Meta:
        model = ToolCall
        fields = [
            'id', 'execution', 'tool_name', 'tool_description', 'status',
            'parameters', 'result', 'error_message',
            'started_at', 'completed_at', 'execution_time_ms',
            'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'started_at', 'completed_at', 'execution_time_ms',
            'created_at', 'updated_at'
        ]


class AgentExecutionSerializer(serializers.ModelSerializer):
    """Serializer for agent executions."""
    
    tool_calls = ToolCallSerializer(many=True, read_only=True)
    
    class Meta:
        model = AgentExecution
        fields = [
            'id', 'user', 'project', 'session', 'task', 
            'agent_type', 'step_name', 'step_type', 'step_number',
            'status', 'input_data', 'output_data', 'execution_graph',
            'error_message', 'tokens_used',
            'llm_provider', 'model_name', 'prompt_tokens', 'completion_tokens',
            'total_tokens', 'started_at', 'completed_at', 'execution_time_ms',
            'metadata', 'tool_calls', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'started_at', 'completed_at', 'execution_time_ms',
            'created_at', 'updated_at'
        ]


class AgentSessionSerializer(serializers.ModelSerializer):
    """Serializer for agent sessions."""
    
    project_name = serializers.CharField(source='project.name', read_only=True)
    feature_name = serializers.CharField(source='feature.name', read_only=True, allow_null=True)
    execution_count = serializers.SerializerMethodField()
    
    class Meta:
        model = AgentSession
        fields = [
            'id', 'user', 'project', 'project_name', 'feature', 'feature_name',
            'session_name', 'agent_type', 'status', 'goal', 'context',
            'graph_state', 'checkpoint_id', 'result', 'error_message',
            'started_at', 'completed_at', 'last_activity_at',
            'metadata', 'execution_count', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'started_at', 'completed_at', 'last_activity_at',
            'created_at', 'updated_at'
        ]
    
    def get_execution_count(self, obj):
        """Get count of executions in this session."""
        return obj.executions.count()


class AgentSessionDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for agent sessions with executions."""
    
    project_name = serializers.CharField(source='project.name', read_only=True)
    feature_name = serializers.CharField(source='feature.name', read_only=True, allow_null=True)
    executions = AgentExecutionSerializer(many=True, read_only=True)
    
    class Meta:
        model = AgentSession
        fields = [
            'id', 'user', 'project', 'project_name', 'feature', 'feature_name',
            'session_name', 'agent_type', 'status', 'goal', 'context',
            'graph_state', 'checkpoint_id', 'result', 'error_message',
            'started_at', 'completed_at', 'last_activity_at',
            'metadata', 'executions', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'started_at', 'completed_at', 'last_activity_at',
            'created_at', 'updated_at'
        ]


class AgentSessionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating agent sessions."""
    
    class Meta:
        model = AgentSession
        fields = [
            'project', 'feature', 'session_name', 'agent_type',
            'goal', 'context', 'metadata'
        ]
    
    def create(self, validated_data):
        """Create agent session with current user."""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class AgentExecutionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating agent executions."""
    
    class Meta:
        model = AgentExecution
        fields = [
            'user', 'project', 'session', 'task', 'agent_type',
            'step_name', 'step_type', 'step_number',
            'input_data', 'llm_provider', 'model_name', 'metadata'
        ]


class ToolCallCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating tool calls."""
    
    class Meta:
        model = ToolCall
        fields = [
            'execution', 'tool_name', 'tool_description',
            'parameters', 'metadata'
        ]


class AgentRunSerializer(serializers.Serializer):
    """Serializer for running an agent."""
    
    project = serializers.UUIDField(required=True)
    feature = serializers.UUIDField(required=False, allow_null=True)
    goal = serializers.CharField(required=True)
    agent_type = serializers.CharField(default='general')
    context = serializers.JSONField(default=dict)
    max_iterations = serializers.IntegerField(default=10, min_value=1, max_value=50)
    llm_provider = serializers.ChoiceField(
        choices=['openai', 'anthropic', 'gemini'],
        default='gemini'
    )
    model_name = serializers.CharField(default='gemini-1.5-pro')
    streaming = serializers.BooleanField(default=False)


class AgentStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating agent status."""
    
    status = serializers.ChoiceField(choices=AgentSession.STATUS_CHOICES)
    result = serializers.JSONField(required=False)
    error_message = serializers.CharField(required=False, allow_blank=True)


class ExecutionStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating execution status."""
    
    status = serializers.ChoiceField(choices=AgentExecution.STATUS_CHOICES)
    output_data = serializers.JSONField(required=False)
    error_message = serializers.CharField(required=False, allow_blank=True)
    prompt_tokens = serializers.IntegerField(required=False)
    completion_tokens = serializers.IntegerField(required=False)
    total_tokens = serializers.IntegerField(required=False)
