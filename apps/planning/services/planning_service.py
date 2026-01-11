"""
Planning Service - Core orchestration for the hierarchical planning system.
This is the "brain" of Archon that manages project plans, features, and tasks.
"""
import uuid
from typing import Dict, Any, List, Optional, Tuple
from django.utils import timezone
from django.db import transaction
from apps.planning.models import ProjectPlan, Feature, Task
from apps.projects.models import Project
from apps.memory.services import MemoryService
from apps.agents.services.llm_service import LLMService
from langchain_core.messages import HumanMessage, SystemMessage


class PlanningService:
    """
    Central planning service that manages the tree-structured project plan.
    Handles feature lifecycle, context switching, and planning state persistence.
    """
    
    def __init__(self, user, project: Project):
        """
        Initialize the planning service.
        
        Args:
            user: User instance
            project: Project to manage planning for
        """
        self.user = user
        self.project = project
        self.memory_service = MemoryService(user, project)
        self._plan = None
    
    @property
    def plan(self) -> ProjectPlan:
        """Get or create the project plan."""
        if self._plan is None:
            self._plan, created = ProjectPlan.objects.get_or_create(
                project=self.project,
                defaults={'tree_structure': {}}
            )
            if created:
                self._persist_to_memory('plan_created', {
                    'project_id': str(self.project.id),
                    'project_name': self.project.name
                })
        return self._plan
    
    # ==================== Feature Management ====================
    
    def create_feature(
        self,
        name: str,
        description: str = '',
        parent_id: str = None,
        priority: int = 0,
        estimated_effort: str = None,
        dependencies: List[str] = None,
        related_files: List[str] = None,
        metadata: Dict = None,
        check_similarity: bool = True
    ) -> Feature:
        """
        Create a new feature in the plan tree.
        
        Args:
            name: Feature name
            description: Feature description
            parent_id: Parent feature ID (None for root features)
            priority: Priority level (higher = more important)
            estimated_effort: Effort estimate
            dependencies: List of feature IDs this depends on
            related_files: List of related file IDs
            metadata: Additional metadata
            check_similarity: Whether to check for semantically similar features
            
        Returns:
            Created Feature instance
        """
        # Check for duplicates (Name based)
        if self._check_duplicate_feature(name, parent_id):
            raise ValueError(f"Feature '{name}' already exists at this level")
            
        # Check for semantic duplicates
        if check_similarity:
            similar = self._find_similar_existing_features(name, description)
            if similar:
                # If very similar, we might want to block or warn
                # For now, we'll log it and include in metadata
                metadata = metadata or {}
                metadata['potential_duplicates'] = [
                    {'id': s['id'], 'name': s['name'], 'score': s['score']} 
                    for s in similar
                ]

        # Get parent if specified
        parent = None
        depth_level = 0
        if parent_id:
            try:
                parent = Feature.objects.get(id=parent_id, plan=self.plan)
                depth_level = parent.depth_level + 1
            except Feature.DoesNotExist:
                raise ValueError(f"Parent feature {parent_id} not found")
        
        # Calculate order index
        siblings = Feature.objects.filter(plan=self.plan, parent=parent)
        order_index = siblings.count()
        
        with transaction.atomic():
            feature = Feature.objects.create(
                plan=self.plan,
                parent=parent,
                name=name,
                description=description,
                status='not_started',
                depth_level=depth_level,
                order_index=order_index,
                priority=priority,
                estimated_effort=estimated_effort,
                dependencies=dependencies or [],
                related_files=related_files or [],
                metadata=metadata or {}
            )
            
            # Update plan statistics
            self.plan.update_stats()
            
            # Update tree structure
            self._update_tree_structure()
            
            # Persist to memory
            self._persist_to_memory('feature_created', {
                'feature_id': str(feature.id),
                'feature_name': name,
                'parent_id': parent_id,
                'description': description
            })
            
            # Store in Long Term Memory for semantic retrieval
            self.memory_service.store_long_term(
                key=f"feature_def_{feature.id}",
                content={
                    'type': 'feature_definition',
                    'name': name,
                    'description': description,
                    'feature_id': str(feature.id)
                },
                category='project_structure',
                importance=0.8
            )
        
        return feature
    
    def _find_similar_existing_features(self, name: str, description: str) -> List[Dict]:
        """Find semantically similar features in the project."""
        query = f"Feature: {name}. {description}"
        
        results = self.memory_service.search_memory(query, top_k=3)
        
        similar_features = []
        for result in results:
            content = result.get('content', {})
            # Check if this memory represents a feature definition
            if isinstance(content, dict) and content.get('type') == 'feature_definition':
                if result.get('score', 0) > 0.85: # High similarity threshold
                    similar_features.append({
                        'id': content.get('feature_id'),
                        'name': content.get('name'),
                        'score': result.get('score')
                    })
                    
        return similar_features

    def get_feature(self, feature_id: str) -> Optional[Feature]:
        """Get a feature by ID."""
        try:
            return Feature.objects.get(id=feature_id, plan=self.plan)
        except Feature.DoesNotExist:
            return None
    
    def get_feature_tree(self, root_only: bool = False) -> List[Dict]:
        """
        Get the feature tree structure.
        
        Args:
            root_only: If True, only return root features
            
        Returns:
            List of feature dictionaries with nested children
        """
        if root_only:
            features = Feature.objects.filter(plan=self.plan, parent=None)
        else:
            features = Feature.objects.filter(plan=self.plan, parent=None)
        
        return [self._feature_to_tree(f) for f in features.order_by('order_index')]
    
    def _feature_to_tree(self, feature: Feature) -> Dict:
        """Convert a feature to tree dictionary with children."""
        children = feature.children.all().order_by('order_index')
        
        return {
            'id': str(feature.id),
            'name': feature.name,
            'description': feature.description,
            'status': feature.status,
            'depth_level': feature.depth_level,
            'priority': feature.priority,
            'estimated_effort': feature.estimated_effort,
            'dependencies': feature.dependencies,
            'related_files': feature.related_files,
            'started_at': feature.started_at.isoformat() if feature.started_at else None,
            'completed_at': feature.completed_at.isoformat() if feature.completed_at else None,
            'last_activity_at': feature.last_activity_at.isoformat(),
            'children': [self._feature_to_tree(c) for c in children],
            'task_count': feature.tasks.count(),
            'completed_tasks': feature.tasks.filter(status='completed').count()
        }
    
    def update_feature(
        self,
        feature_id: str,
        **updates
    ) -> Feature:
        """
        Update a feature's properties.
        
        Args:
            feature_id: Feature ID
            **updates: Fields to update
            
        Returns:
            Updated Feature instance
        """
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")
        
        allowed_fields = {
            'name', 'description', 'priority', 'estimated_effort',
            'dependencies', 'related_files', 'metadata', 'related_memories'
        }
        
        for field, value in updates.items():
            if field in allowed_fields:
                setattr(feature, field, value)
        
        feature.last_activity_at = timezone.now()
        feature.save()
        
        self._update_tree_structure()
        
        return feature
    
    def delete_feature(self, feature_id: str, cascade: bool = True):
        """
        Delete a feature and optionally its children.
        
        Args:
            feature_id: Feature ID
            cascade: If True, delete children; if False, move children up
        """
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")
        
        with transaction.atomic():
            if not cascade:
                # Move children to parent level
                for child in feature.children.all():
                    child.parent = feature.parent
                    child.depth_level = feature.depth_level
                    child.save()
            
            feature.delete()
            self.plan.update_stats()
            self._update_tree_structure()
    
    # ==================== Feature Status Management ====================
    
    def start_feature(self, feature_id: str) -> Feature:
        """Start working on a feature."""
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")
        
        # Check dependencies
        unmet = self._get_unmet_dependencies(feature)
        if unmet:
            raise ValueError(f"Cannot start: unmet dependencies: {unmet}")
        
        feature.mark_in_progress()
        
        # Set as active feature in plan
        self.plan.active_feature = feature
        self.plan.save()
        
        self._persist_to_memory('feature_started', {
            'feature_id': str(feature.id),
            'feature_name': feature.name
        })
        
        return feature
    
    def complete_feature(self, feature_id: str, result: Dict = None) -> Feature:
        """Mark a feature as completed."""
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")
        
        # Check if all children are completed
        incomplete_children = feature.children.exclude(status='completed')
        if incomplete_children.exists():
            names = [c.name for c in incomplete_children[:3]]
            raise ValueError(f"Cannot complete: children not done: {names}")
        
        feature.mark_completed()
        
        # Store completion in long-term memory
        self.memory_service.store_long_term(
            key=f"feature_completed_{feature.id}",
            content={
                'feature_name': feature.name,
                'description': feature.description,
                'result': result,
                'completed_at': timezone.now().isoformat()
            },
            category='lesson_learned',
            importance=0.7
        )
        
        # Clear active feature if this was it
        if self.plan.active_feature == feature:
            self.plan.active_feature = None
            self.plan.save()
        
        return feature
    
    def pause_feature(self, feature_id: str, reason: str = None) -> Tuple[Feature, Dict]:
        """
        Pause a feature and capture its context for later resumption.
        
        Args:
            feature_id: Feature ID
            reason: Optional reason for pausing
            
        Returns:
            Tuple of (Feature, context_snapshot)
        """
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")
        
        # Capture current context
        context_snapshot = {
            'feature_id': str(feature.id),
            'feature_name': feature.name,
            'status_before_pause': feature.status,
            'paused_at': timezone.now().isoformat(),
            'reason': reason,
            'last_task': self._get_last_task_context(feature),
            'pending_tasks': self._get_pending_tasks(feature),
            'related_memories': feature.related_memories,
            'next_suggested_action': self._suggest_next_action(feature)
        }
        
        # Update feature status
        feature.status = 'paused'
        feature.metadata['pause_context'] = context_snapshot
        feature.last_activity_at = timezone.now()
        feature.save()
        
        # Store in short-term memory for quick resumption
        self.memory_service.store_short_term(
            session_id=str(feature.id),
            key=f"pause_context_{feature.id}",
            content=context_snapshot,
            memory_type='context',
            ttl_seconds=86400 * 7  # Keep for 7 days
        )
        
        # Clear active feature
        if self.plan.active_feature == feature:
            self.plan.active_feature = None
            self.plan.save()
        
        return feature, context_snapshot
    
    def resume_feature(self, feature_id: str) -> Tuple[Feature, Dict]:
        """
        Resume a paused feature and restore its context.
        
        Args:
            feature_id: Feature ID
            
        Returns:
            Tuple of (Feature, restored_context)
        """
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")
        
        # Retrieve pause context
        pause_context = feature.metadata.get('pause_context', {})
        
        # Also check short-term memory
        stm_context = self.memory_service.get_short_term(
            session_id=str(feature.id),
            key=f"pause_context_{feature.id}"
        )
        
        if stm_context:
            pause_context.update(stm_context)
        
        # Restore status
        previous_status = pause_context.get('status_before_pause', 'in_progress')
        feature.status = previous_status if previous_status != 'paused' else 'in_progress'
        feature.last_activity_at = timezone.now()
        
        # Add resume info to metadata
        feature.metadata['last_resumed_at'] = timezone.now().isoformat()
        feature.save()
        
        # Set as active feature
        self.plan.active_feature = feature
        self.plan.save()
        
        # Build restoration context
        restored_context = {
            'feature': self._feature_to_tree(feature),
            'pause_context': pause_context,
            'next_action': pause_context.get('next_suggested_action'),
            'pending_tasks': pause_context.get('pending_tasks', []),
            'related_files': feature.related_files,
            'related_memories': self._get_related_memory_content(feature)
        }
        
        self._persist_to_memory('feature_resumed', {
            'feature_id': str(feature.id),
            'feature_name': feature.name
        })
        
        return feature, restored_context
    
    def block_feature(self, feature_id: str, reason: str) -> Feature:
        """Mark a feature as blocked."""
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")
        
        feature.mark_blocked(reason)
        
        self._persist_to_memory('feature_blocked', {
            'feature_id': str(feature.id),
            'feature_name': feature.name,
            'reason': reason
        })
        
        return feature
    
    # ==================== Context Switching ====================
    
    def switch_feature(self, from_feature_id: str, to_feature_id: str) -> Dict:
        """
        Switch from one feature to another, preserving context.
        
        Args:
            from_feature_id: Current feature ID
            to_feature_id: Target feature ID
            
        Returns:
            Switch result with contexts
        """
        # Pause current feature
        from_feature, pause_context = self.pause_feature(
            from_feature_id,
            reason=f"Switching to feature {to_feature_id}"
        )
        
        # Resume target feature
        to_feature, resume_context = self.resume_feature(to_feature_id)
        
        return {
            'switched': True,
            'from_feature': {
                'id': str(from_feature.id),
                'name': from_feature.name,
                'status': from_feature.status,
                'pause_context': pause_context
            },
            'to_feature': {
                'id': str(to_feature.id),
                'name': to_feature.name,
                'status': to_feature.status,
                'resume_context': resume_context
            }
        }
    
    def get_active_feature(self) -> Optional[Feature]:
        """Get the currently active feature."""
        return self.plan.active_feature
    
    def get_resumable_features(self) -> List[Dict]:
        """Get all features that can be resumed."""
        features = Feature.objects.filter(
            plan=self.plan,
            status__in=['paused', 'in_progress']
        ).order_by('-last_activity_at')
        
        return [{
            'id': str(f.id),
            'name': f.name,
            'status': f.status,
            'last_activity': f.last_activity_at.isoformat(),
            'has_pause_context': bool(f.metadata.get('pause_context'))
        } for f in features]
    
    # ==================== Task Management ====================
    
    def create_task(
        self,
        feature_id: str,
        title: str,
        description: str = '',
        task_type: str = None,
        order_index: int = None
    ) -> Task:
        """Create a task within a feature."""
        feature = self.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")
        
        if order_index is None:
            order_index = feature.tasks.count()
        
        task = Task.objects.create(
            feature=feature,
            title=title,
            description=description,
            task_type=task_type,
            order_index=order_index,
            status='pending'
        )
        
        return task
    
    def complete_task(self, task_id: str, result: Dict = None) -> Task:
        """Mark a task as completed."""
        try:
            task = Task.objects.get(id=task_id, feature__plan=self.plan)
        except Task.DoesNotExist:
            raise ValueError(f"Task {task_id} not found")
        
        task.mark_completed(result)
        
        # Update feature's last activity
        task.feature.last_activity_at = timezone.now()
        task.feature.save()
        
        return task
    
    def fail_task(self, task_id: str, error_message: str) -> Task:
        """Mark a task as failed."""
        try:
            task = Task.objects.get(id=task_id, feature__plan=self.plan)
        except Task.DoesNotExist:
            raise ValueError(f"Task {task_id} not found")
        
        task.mark_failed(error_message)
        
        return task
    
    # ==================== Plan Analysis ====================
    
    def get_plan_summary(self) -> Dict:
        """Get a summary of the entire plan."""
        features = Feature.objects.filter(plan=self.plan)
        
        status_counts = {}
        for status, _ in Feature.STATUS_CHOICES:
            status_counts[status] = features.filter(status=status).count()
        
        return {
            'project_id': str(self.project.id),
            'project_name': self.project.name,
            'plan_version': self.plan.plan_version,
            'total_features': self.plan.total_features,
            'completed_features': self.plan.completed_features,
            'completion_percentage': self.plan.completion_percentage,
            'status_breakdown': status_counts,
            'active_feature': self._feature_to_tree(self.plan.active_feature) if self.plan.active_feature else None,
            'root_features': len(features.filter(parent=None)),
            'blocked_features': list(features.filter(status='blocked').values('id', 'name', 'blocking_reason'))
        }
    
    def get_next_suggested_features(self, limit: int = 5) -> List[Dict]:
        """Get suggested features to work on next."""
        # Get features that are ready to start
        ready_features = []
        
        for feature in Feature.objects.filter(
            plan=self.plan,
            status='not_started'
        ).order_by('-priority'):
            unmet = self._get_unmet_dependencies(feature)
            if not unmet:
                ready_features.append({
                    'id': str(feature.id),
                    'name': feature.name,
                    'description': feature.description,
                    'priority': feature.priority,
                    'estimated_effort': feature.estimated_effort,
                    'reason': 'All dependencies met'
                })
                if len(ready_features) >= limit:
                    break
        
        return ready_features
    
    def find_feature_by_name(self, name: str, fuzzy: bool = True) -> List[Feature]:
        """Find features by name."""
        if fuzzy:
            return list(Feature.objects.filter(
                plan=self.plan,
                name__icontains=name
            ))
        return list(Feature.objects.filter(plan=self.plan, name=name))
    
    # ==================== Helper Methods ====================
    
    def _check_duplicate_feature(self, name: str, parent_id: str = None) -> bool:
        """Check if a feature with this name exists at the same level."""
        parent = None
        if parent_id:
            try:
                parent = Feature.objects.get(id=parent_id)
            except Feature.DoesNotExist:
                return False
        
        return Feature.objects.filter(
            plan=self.plan,
            parent=parent,
            name__iexact=name
        ).exists()
    
    def _get_unmet_dependencies(self, feature: Feature) -> List[str]:
        """Get list of unmet dependency IDs."""
        unmet = []
        for dep_id in feature.dependencies:
            try:
                dep = Feature.objects.get(id=dep_id)
                if dep.status != 'completed':
                    unmet.append(dep_id)
            except Feature.DoesNotExist:
                pass
        return unmet
    
    def _get_last_task_context(self, feature: Feature) -> Optional[Dict]:
        """Get context of the last worked-on task."""
        last_task = feature.tasks.exclude(
            status='pending'
        ).order_by('-completed_at').first()
        
        if last_task:
            return {
                'id': str(last_task.id),
                'title': last_task.title,
                'status': last_task.status,
                'result': last_task.result
            }
        return None
    
    def _get_pending_tasks(self, feature: Feature) -> List[Dict]:
        """Get list of pending tasks."""
        return [{
            'id': str(t.id),
            'title': t.title,
            'order_index': t.order_index
        } for t in feature.tasks.filter(status='pending').order_by('order_index')]
    
    def _suggest_next_action(self, feature: Feature) -> str:
        """Suggest the next action for a feature."""
        pending_tasks = feature.tasks.filter(status='pending').order_by('order_index')
        
        if pending_tasks.exists():
            next_task = pending_tasks.first()
            return f"Continue with task: {next_task.title}"
        
        incomplete_children = feature.children.exclude(status='completed')
        if incomplete_children.exists():
            child = incomplete_children.first()
            return f"Work on sub-feature: {child.name}"
        
        return "All tasks complete - ready to mark feature as done"
    
    def _get_related_memory_content(self, feature: Feature) -> List[Dict]:
        """Get content of related memories."""
        memories = []
        for memory_id in feature.related_memories:
            content = self.memory_service.get_long_term(memory_id)
            if content:
                memories.append({'id': memory_id, 'content': content})
        return memories
    
    def _update_tree_structure(self):
        """Update the cached tree structure in the plan."""
        self.plan.tree_structure = {
            'updated_at': timezone.now().isoformat(),
            'features': self.get_feature_tree()
        }
        self.plan.save(update_fields=['tree_structure'])
    
    def _persist_to_memory(self, event_type: str, data: Dict):
        """Persist planning events to memory."""
        try:
            self.memory_service.store_short_term(
                session_id=str(self.plan.id),
                key=f"planning_{event_type}_{timezone.now().timestamp()}",
                content={
                    'event_type': event_type,
                    'timestamp': timezone.now().isoformat(),
                    **data
                },
                memory_type='context',
                ttl_seconds=86400  # 24 hours
            )
        except Exception:
            pass  # Memory storage is best-effort

    # ==================== Autonomous Executor Support ====================
    
    def create_plan(
        self,
        goal: str,
        project_id: str = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Create an execution plan for a goal.
        Used by AutonomousExecutor.
        """
        context = context or {}
        
        # Build planning prompt
        system_prompt = f"""You are an expert technical project manager and architect.
Your goal is to break down a high-level goal into specific, actionable technical tasks.
The current project is: {self.project.name}

Current Status:
- {self.plan.total_features} total features
- {self.plan.completed_features} completed

Return a JSON object with this exact structure:
{{
    "goal": "original goal",
    "tasks": [
        {{
            "id": "unique_id",
            "type": "one of: analyze, plan, research, generate_code, refactor, test, debug, document, review",
            "title": "Short title",
            "description": "Detailed description description",
            "priority": 1-10,
            "requires_confirmation": boolean,
            "input": {{ "key": "value" }}
        }}
    ],
    "estimated_duration": "string",
    "success_criteria": ["string"]
}}"""

        user_prompt = f"""Create a detailed execution plan for: {goal}

Additional Context:
{context}
"""
        
        try:
            llm = LLMService.get_user_preferred_llm(self.user)
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            content = response.content
            # Clean up potential markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            import json
            plan = json.loads(content)
            
            # Ensure required fields
            plan.setdefault('goal', goal)
            plan.setdefault('tasks', [])
            plan.setdefault('created_at', timezone.now().isoformat())
            
            return plan
            
        except Exception as e:
            # Return a basic plan on error
            return {
                'goal': goal,
                'tasks': [
                    {
                        'id': 'task_analyze',
                        'type': 'analyze',
                        'title': f'Analyze: {goal}',
                        'description': f'Analyze the requirements for: {goal}',
                        'priority': 10,
                        'requires_confirmation': False,
                        'input': {}
                    }
                ],
                'error': str(e),
                'created_at': timezone.now().isoformat()
            }
    
    def analyze_codebase(
        self,
        project_id: str,
        query: str
    ) -> Dict[str, Any]:
        """Analyze the codebase for a specific query."""
        # Get project context from memory
        context = self.memory_service.get_context(
            query=query,
            limit=10
        )
        
        prompt = f"""Analyze the following in the context of project {self.project.name}:

Query: {query}

Available Context:
{context}

Current Plan State:
- Total Features: {self.plan.total_features}
- Active Feature: {self.plan.active_feature.name if self.plan.active_feature else 'None'}

Provide a detailed analysis including:
1. Current state assessment
2. Relevant patterns or issues found
3. Recommendations
4. Next steps
"""
        
        try:
            llm = LLMService.get_user_preferred_llm(self.user)
            response = llm.invoke([HumanMessage(content=prompt)])
            
            return {
                'query': query,
                'analysis': response.content,
                'context_used': len(context) if isinstance(context, list) else 1,
                'timestamp': timezone.now().isoformat()
            }
        except Exception as e:
            return {
                'query': query,
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            }
    
    def assess_completion(
        self,
        goal: str,
        completed_actions: List[str],
        project_id: str = None
    ) -> Dict[str, Any]:
        """Assess if a goal has been completed based on actions taken."""
        
        prompt = f"""Assess whether the following goal has been completed:

Goal: {goal}

Completed Actions:
{chr(10).join(f'- {action}' for action in completed_actions)}

Evaluate:
1. Has the goal been fully achieved?
2. Are there remaining tasks?
3. What is the completion percentage?

Return JSON:
{{
    "goal_complete": true/false,
    "completion_percentage": 0-100,
    "remaining_tasks": ["..."],
    "assessment": "..."
}}
"""
        
        try:
            llm = LLMService.get_user_preferred_llm(self.user)
            response = llm.invoke([HumanMessage(content=prompt)])
            
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            import json
            assessment = json.loads(content)
            
            return assessment
            
        except Exception as e:
            # Conservative: assume not complete on error
            return {
                'goal_complete': False,
                'completion_percentage': len(completed_actions) * 10,  # Rough estimate
                'remaining_tasks': ['Unable to assess - continuing'],
                'error': str(e)
            }
    
    def generate_code_for_task(
        self,
        task_description: str,
        project_id: str = None
    ) -> Dict[str, Any]:
        """Generate code for a task."""
        
        prompt = f"""Generate code for the following task:

Task: {task_description}

Project: {self.project.name}

Requirements:
1. Follow best practices
2. Include appropriate comments
3. Handle errors properly
4. Be production-ready

Provide:
1. The code
2. File path suggestion
3. Any dependencies needed
4. Usage example
"""
        
        try:
            llm = LLMService.get_user_preferred_llm(self.user)
            response = llm.invoke([HumanMessage(content=prompt)])
            
            return {
                'task': task_description,
                'code': response.content,
                'generated_at': timezone.now().isoformat()
            }
        except Exception as e:
            return {
                'task': task_description,
                'error': str(e),
                'generated_at': timezone.now().isoformat()
            }
    
    def suggest_refactoring(
        self,
        project_id: str,
        target: str,
        refactor_type: str = 'improve'
    ) -> Dict[str, Any]:
        """Suggest refactoring for code."""
        
        prompt = f"""Suggest refactoring for the following:

Target: {target}
Refactoring Type: {refactor_type}

Provide:
1. Issues identified
2. Suggested improvements
3. Refactored code (if applicable)
4. Benefits of changes
"""
        
        try:
            llm = LLMService.get_user_preferred_llm(self.user)
            response = llm.invoke([HumanMessage(content=prompt)])
            
            return {
                'target': target,
                'refactor_type': refactor_type,
                'suggestions': response.content,
                'generated_at': timezone.now().isoformat()
            }
        except Exception as e:
            return {
                'target': target,
                'error': str(e)
            }
    
    def analyze_error(
        self,
        error: str,
        project_id: str = None
    ) -> Dict[str, Any]:
        """Analyze an error and suggest fixes."""
        
        prompt = f"""Analyze the following error and suggest fixes:

Error:
{error}

Project: {self.project.name}

Provide:
1. Root cause analysis
2. Step-by-step fix instructions
3. Code fixes if applicable
4. Prevention recommendations
"""
        
        try:
            llm = LLMService.get_user_preferred_llm(self.user)
            response = llm.invoke([HumanMessage(content=prompt)])
            
            return {
                'error': error,
                'analysis': response.content,
                'analyzed_at': timezone.now().isoformat()
            }
        except Exception as e:
            return {
                'error': error,
                'analysis_error': str(e)
            }
    
    def generate_documentation(
        self,
        target: str,
        project_id: str = None
    ) -> Dict[str, Any]:
        """Generate documentation for code."""
        
        prompt = f"""Generate comprehensive documentation for:

Target: {target}

Include:
1. Overview/Purpose
2. Usage examples
3. API reference (if applicable)
4. Parameters/Arguments
5. Return values
6. Error handling
7. Related components
"""
        
        try:
            llm = LLMService.get_user_preferred_llm(self.user)
            response = llm.invoke([HumanMessage(content=prompt)])
            
            return {
                'target': target,
                'documentation': response.content,
                'generated_at': timezone.now().isoformat()
            }
        except Exception as e:
            return {
                'target': target,
                'error': str(e)
            }
    
    def review_code(
        self,
        code: str,
        project_id: str = None
    ) -> Dict[str, Any]:
        """Review code and provide feedback."""
        
        prompt = f"""Perform a thorough code review:

Code:
```
{code}
```

Review for:
1. Code quality and readability
2. Potential bugs
3. Security issues
4. Performance concerns
5. Best practices
6. Suggestions for improvement

Provide specific, actionable feedback.
"""
        
        try:
            llm = LLMService.get_user_preferred_llm(self.user)
            response = llm.invoke([HumanMessage(content=prompt)])
            
            return {
                'review': response.content,
                'reviewed_at': timezone.now().isoformat()
            }
        except Exception as e:
            return {
                'error': str(e)
            }
