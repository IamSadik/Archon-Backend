"""
Planning Tools - Tools for interacting with the planning system.
"""
from typing import Dict, Any, List, Optional
from .base import BaseTool, ToolResult, ToolParameter, ToolCategory, ToolRegistry


@ToolRegistry.register
class GetPlanStatusTool(BaseTool):
    """Get current project plan status."""
    
    name = "get_plan_status"
    description = "Get the current status of the project plan including features and progress"
    category = ToolCategory.PLANNING
    parameters = [
        ToolParameter(
            name="include_tree",
            type="boolean",
            description="Whether to include the full feature tree",
            required=False,
            default=False
        ),
    ]
    
    def execute(self, include_tree: bool = False) -> ToolResult:
        """Get plan status."""
        try:
            planning_service = self.context.get('planning_service')
            if not planning_service:
                return ToolResult(success=False, error="Planning service not available")
            
            summary = planning_service.get_plan_summary()
            
            if include_tree:
                summary['feature_tree'] = planning_service.get_feature_tree()
            
            return ToolResult(
                success=True,
                data=summary
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@ToolRegistry.register
class CreateFeatureTool(BaseTool):
    """Create a new feature in the plan."""
    
    name = "create_feature"
    description = "Create a new feature or sub-feature in the project plan"
    category = ToolCategory.PLANNING
    parameters = [
        ToolParameter(
            name="name",
            type="string",
            description="Name of the feature"
        ),
        ToolParameter(
            name="description",
            type="string",
            description="Description of what the feature does",
            required=False,
            default=""
        ),
        ToolParameter(
            name="parent_id",
            type="string",
            description="ID of parent feature (for sub-features)",
            required=False,
            default=None
        ),
        ToolParameter(
            name="priority",
            type="integer",
            description="Priority level (higher = more important)",
            required=False,
            default=0
        ),
        ToolParameter(
            name="estimated_effort",
            type="string",
            description="Effort estimate",
            required=False,
            default=None,
            enum=["small", "medium", "large", "extra_large"]
        ),
    ]
    
    def execute(
        self,
        name: str,
        description: str = "",
        parent_id: str = None,
        priority: int = 0,
        estimated_effort: str = None
    ) -> ToolResult:
        """Create feature."""
        try:
            planning_service = self.context.get('planning_service')
            if not planning_service:
                return ToolResult(success=False, error="Planning service not available")
            
            feature = planning_service.create_feature(
                name=name,
                description=description,
                parent_id=parent_id,
                priority=priority,
                estimated_effort=estimated_effort
            )
            
            return ToolResult(
                success=True,
                data={
                    'id': str(feature.id),
                    'name': feature.name,
                    'description': feature.description,
                    'status': feature.status,
                    'depth_level': feature.depth_level,
                    'created': True
                }
            )
            
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@ToolRegistry.register
class UpdateFeatureStatusTool(BaseTool):
    """Update the status of a feature."""
    
    name = "update_feature_status"
    description = "Update the status of a feature (start, complete, pause, block)"
    category = ToolCategory.PLANNING
    parameters = [
        ToolParameter(
            name="feature_id",
            type="string",
            description="ID of the feature to update"
        ),
        ToolParameter(
            name="action",
            type="string",
            description="Action to perform",
            enum=["start", "complete", "pause", "resume", "block", "unblock"]
        ),
        ToolParameter(
            name="reason",
            type="string",
            description="Reason (required for pause/block)",
            required=False,
            default=""
        ),
    ]
    
    def execute(
        self,
        feature_id: str,
        action: str,
        reason: str = ""
    ) -> ToolResult:
        """Update feature status."""
        try:
            planning_service = self.context.get('planning_service')
            if not planning_service:
                return ToolResult(success=False, error="Planning service not available")
            
            result = None
            
            if action == "start":
                feature = planning_service.start_feature(feature_id)
                result = {'status': feature.status, 'started': True}
                
            elif action == "complete":
                feature = planning_service.complete_feature(feature_id)
                result = {'status': feature.status, 'completed': True}
                
            elif action == "pause":
                feature, context = planning_service.pause_feature(feature_id, reason)
                result = {'status': feature.status, 'paused': True, 'context': context}
                
            elif action == "resume":
                feature, context = planning_service.resume_feature(feature_id)
                result = {'status': feature.status, 'resumed': True, 'context': context}
                
            elif action == "block":
                if not reason:
                    return ToolResult(success=False, error="Reason required for blocking")
                feature = planning_service.block_feature(feature_id, reason)
                result = {'status': feature.status, 'blocked': True}
                
            elif action == "unblock":
                feature = planning_service.get_feature(feature_id)
                if feature:
                    feature.unblock()
                    result = {'status': feature.status, 'unblocked': True}
                else:
                    return ToolResult(success=False, error="Feature not found")
            
            return ToolResult(
                success=True,
                data={
                    'feature_id': feature_id,
                    'action': action,
                    **result
                }
            )
            
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@ToolRegistry.register
class CreateTaskTool(BaseTool):
    """Create a task within a feature."""
    
    name = "create_task"
    description = "Create a new task within a feature"
    category = ToolCategory.PLANNING
    parameters = [
        ToolParameter(
            name="feature_id",
            type="string",
            description="ID of the feature to add task to"
        ),
        ToolParameter(
            name="title",
            type="string",
            description="Task title"
        ),
        ToolParameter(
            name="description",
            type="string",
            description="Task description",
            required=False,
            default=""
        ),
        ToolParameter(
            name="task_type",
            type="string",
            description="Type of task",
            required=False,
            default=None,
            enum=["code_generation", "code_modification", "research", "review", "testing", "documentation"]
        ),
    ]
    
    def execute(
        self,
        feature_id: str,
        title: str,
        description: str = "",
        task_type: str = None
    ) -> ToolResult:
        """Create task."""
        try:
            planning_service = self.context.get('planning_service')
            if not planning_service:
                return ToolResult(success=False, error="Planning service not available")
            
            task = planning_service.create_task(
                feature_id=feature_id,
                title=title,
                description=description,
                task_type=task_type
            )
            
            return ToolResult(
                success=True,
                data={
                    'id': str(task.id),
                    'title': task.title,
                    'description': task.description,
                    'task_type': task.task_type,
                    'status': task.status,
                    'created': True
                }
            )
            
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=str(e))
