"""
Memory Service - Manages short-term and long-term memory for Archon.
"""
import uuid
from typing import Dict, Any, List, Optional
from django.utils import timezone
from django.db import models
from datetime import timedelta
from apps.memory.models import ShortTermMemory, LongTermMemory, MemorySnapshot
from apps.projects.models import Project
from apps.vector_store.services import EmbeddingService, SemanticSearchService


class MemoryService:
    """
    Service for managing agent memory.
    Handles short-term (conversation), long-term (persistent), and RAG memory.
    """
    
    def __init__(self, user, project: Project = None):
        """
        Initialize the memory service.
        
        Args:
            user: User instance
            project: Optional project for scoping memory
        """
        self.user = user
        self.project = project
        self.embedding_service = None
        self.search_service = None
    
    def _get_embedding_service(self):
        """Lazy load embedding service."""
        if self.embedding_service is None:
            self.embedding_service = EmbeddingService()
        return self.embedding_service
    
    def _get_search_service(self):
        """Lazy load search service."""
        if self.search_service is None:
            self.search_service = SemanticSearchService()
        return self.search_service
    
    # ==================== Short-Term Memory ====================
    
    def store_short_term(
        self,
        session_id: str,
        key: str,
        content: Dict[str, Any],
        memory_type: str = 'conversation',
        ttl_seconds: int = 3600
    ) -> ShortTermMemory:
        """
        Store short-term memory.
        
        Args:
            session_id: Session identifier
            key: Memory key
            content: Content to store
            memory_type: Type of memory
            ttl_seconds: Time to live in seconds
            
        Returns:
            Created ShortTermMemory instance
        """
        if not self.project:
            raise ValueError("Project is required for memory operations")
        
        # Check for existing memory with same key
        existing = ShortTermMemory.objects.filter(
            user=self.user,
            project=self.project,
            session_id=session_id,
            memory_key=key
        ).first()
        
        if existing:
            existing.content = content
            existing.accessed_at = timezone.now()
            existing.expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
            existing.save()
            return existing
        
        return ShortTermMemory.objects.create(
            user=self.user,
            project=self.project,
            session_id=session_id,
            memory_key=key,
            content=content,
            memory_type=memory_type,
            ttl_seconds=ttl_seconds,
            created_at=timezone.now(),
            expires_at=timezone.now() + timedelta(seconds=ttl_seconds)
        )
    
    def get_short_term(self, session_id: str, key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve short-term memory.
        
        Args:
            session_id: Session identifier
            key: Memory key
            
        Returns:
            Memory content or None
        """
        try:
            memory = ShortTermMemory.objects.get(
                user=self.user,
                project=self.project,
                session_id=session_id,
                memory_key=key,
                expires_at__gt=timezone.now()
            )
            memory.touch()
            return memory.content
        except ShortTermMemory.DoesNotExist:
            return None
    
    def get_session_memory(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all short-term memory for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of memory entries
        """
        memories = ShortTermMemory.objects.filter(
            user=self.user,
            project=self.project,
            session_id=session_id,
            expires_at__gt=timezone.now()
        ).order_by('-created_at')
        
        return [
            {
                'key': m.memory_key,
                'content': m.content,
                'created_at': m.created_at.isoformat(),
                'type': m.memory_type
            }
            for m in memories
        ]
    
    def store_conversation_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        metadata: Dict = None
    ):
        """
        Store a conversation turn in short-term memory.
        
        Args:
            session_id: Session identifier
            user_message: User's message
            assistant_response: Assistant's response
            metadata: Additional metadata
        """
        turn_id = str(uuid.uuid4())[:8]
        
        self.store_short_term(
            session_id=session_id,
            key=f"turn_{turn_id}",
            content={
                'user': user_message,
                'assistant': assistant_response,
                'metadata': metadata or {}
            },
            memory_type='conversation',
            ttl_seconds=7200  # 2 hours
        )
    
    def clear_session_memory(self, session_id: str):
        """
        Clear all short-term memory for a session.
        
        Args:
            session_id: Session identifier
        """
        ShortTermMemory.objects.filter(
            user=self.user,
            project=self.project,
            session_id=session_id
        ).delete()
    
    def cleanup_expired_memory(self):
        """Remove all expired short-term memory."""
        ShortTermMemory.objects.filter(
            user=self.user,
            expires_at__lt=timezone.now()
        ).delete()
    
    # ==================== Long-Term Memory ====================
    
    def store_long_term(
        self,
        key: str,
        content: Dict[str, Any],
        category: str = None,
        importance: float = 0.5,
        create_embedding: bool = True
    ) -> LongTermMemory:
        """
        Store long-term memory.
        
        Args:
            key: Memory key
            content: Content to store
            category: Memory category
            importance: Importance score (0-1)
            create_embedding: Whether to create vector embedding
            
        Returns:
            Created LongTermMemory instance
        """
        if not self.project:
            raise ValueError("Project is required for memory operations")
        
        # Check for existing
        existing = LongTermMemory.objects.filter(
            user=self.user,
            project=self.project,
            memory_key=key
        ).first()
        
        if existing:
            existing.content = content
            existing.importance_score = importance
            if category:
                existing.memory_category = category
            existing.save()
            memory = existing
        else:
            memory = LongTermMemory.objects.create(
                user=self.user,
                project=self.project,
                memory_key=key,
                content=content,
                memory_category=category,
                importance_score=importance
            )
        
        # Create embedding for semantic search
        if create_embedding:
            try:
                embedding_service = self._get_embedding_service()
                content_text = self._content_to_text(content)
                
                embedding_doc = embedding_service.store_embedding(
                    project=self.project,
                    content=content_text,
                    document_type='memory',
                    source_id=str(memory.id),
                    metadata={
                        'memory_key': key,
                        'category': category,
                        'importance': importance
                    }
                )
                
                memory.embedding_id = embedding_doc.pinecone_id
                memory.save(update_fields=['embedding_id'])
            except Exception:
                pass  # Embedding is optional
        
        return memory
    
    def get_long_term(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve long-term memory by key.
        
        Args:
            key: Memory key
            
        Returns:
            Memory content or None
        """
        try:
            memory = LongTermMemory.objects.get(
                user=self.user,
                project=self.project,
                memory_key=key
            )
            memory.access()
            return memory.content
        except LongTermMemory.DoesNotExist:
            return None
    
    def get_memories_by_category(self, category: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get long-term memories by category.
        
        Args:
            category: Memory category
            limit: Maximum results
            
        Returns:
            List of memory entries
        """
        memories = LongTermMemory.objects.filter(
            user=self.user,
            project=self.project,
            memory_category=category
        ).order_by('-importance_score')[:limit]
        
        return [
            {
                'key': m.memory_key,
                'content': m.content,
                'importance': m.importance_score,
                'category': m.memory_category
            }
            for m in memories
        ]
    
    def get_important_memories(self, min_importance: float = 0.7, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get high-importance memories.
        
        Args:
            min_importance: Minimum importance score
            limit: Maximum results
            
        Returns:
            List of memory entries
        """
        memories = LongTermMemory.objects.filter(
            user=self.user,
            project=self.project,
            importance_score__gte=min_importance
        ).order_by('-importance_score')[:limit]
        
        return [
            {
                'key': m.memory_key,
                'content': m.content,
                'importance': m.importance_score,
                'category': m.memory_category
            }
            for m in memories
        ]
    
    def store_user_preference(self, preference_key: str, value: Any, importance: float = 0.8):
        """
        Store a user preference.
        
        Args:
            preference_key: Preference identifier
            value: Preference value
            importance: Importance score
        """
        self.store_long_term(
            key=f"pref_{preference_key}",
            content={'preference': preference_key, 'value': value},
            category='user_preference',
            importance=importance
        )
    
    def store_architectural_decision(
        self,
        decision: str,
        rationale: str,
        alternatives: List[str] = None,
        importance: float = 0.9
    ):
        """
        Store an architectural decision.
        
        Args:
            decision: The decision made
            rationale: Why this decision was made
            alternatives: Alternatives considered
            importance: Importance score
        """
        decision_id = str(uuid.uuid4())[:8]
        
        self.store_long_term(
            key=f"arch_{decision_id}",
            content={
                'decision': decision,
                'rationale': rationale,
                'alternatives': alternatives or [],
                'timestamp': timezone.now().isoformat()
            },
            category='architectural_decision',
            importance=importance
        )
    
    # ==================== RAG Memory (Semantic Search) ====================
    
    def search_memory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search long-term memory (vectors).
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            List of relevant memories
        """
        if not self.project:
            raise ValueError("Project is required for memory search")
            
        search_service = self._get_search_service()
        return search_service.search(
            query=query,
            project=self.project,
            top_k=top_k,
            document_type='memory',
                log_search=False
        )

    def get_context_for_query(self, query: str) -> str:
        """
        Get unified context for a query suitable for LLM injection.
        
        Args:
            query: Search query
            
        Returns:
            String containing formatted context
        """
        if not self.project:
            raise ValueError("Project is required for context retrieval")
            
        search_service = self._get_search_service()
        return search_service.get_context_for_query(
            query=query,
            project=self.project
        )
    
    # ==================== Snapshots ====================
    
    def create_snapshot(self, name: str, session_id: str = None) -> MemorySnapshot:
        """
        Create a snapshot of current memory state.
        
        Args:
            name: Snapshot name
            session_id: Optional session ID
            
        Returns:
            Created MemorySnapshot
        """
        # Gather short-term memory
        stm_data = {}
        if session_id:
            stm_entries = self.get_session_memory(session_id)
            stm_data = {entry['key']: entry for entry in stm_entries}
        
        # Gather long-term memory
        ltm_entries = LongTermMemory.objects.filter(
            user=self.user,
            project=self.project
        ).order_by('-importance_score')[:50]
        
        ltm_data = {
            str(m.id): {
                'key': m.memory_key,
                'content': m.content,
                'category': m.memory_category,
                'importance': m.importance_score
            }
            for m in ltm_entries
        }
        
        return MemorySnapshot.objects.create(
            user=self.user,
            project=self.project,
            session_id=session_id,
            snapshot_name=name,
            short_term_data=stm_data,
            long_term_data=ltm_data
        )
    
    # ==================== Utilities ====================
    
    def _content_to_text(self, content: Dict[str, Any]) -> str:
        """Convert content dict to searchable text."""
        if isinstance(content, str):
            return content
        
        parts = []
        for key, value in content.items():
            if isinstance(value, str):
                parts.append(f"{key}: {value}")
            elif isinstance(value, list):
                parts.append(f"{key}: {', '.join(str(v) for v in value)}")
            else:
                parts.append(f"{key}: {value}")
        
        return "\n".join(parts)
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics for the project."""
        if not self.project:
            return {}
        
        stm_count = ShortTermMemory.objects.filter(
            user=self.user,
            project=self.project,
            expires_at__gt=timezone.now()
        ).count()
        
        ltm_count = LongTermMemory.objects.filter(
            user=self.user,
            project=self.project
        ).count()
        
        ltm_by_category = LongTermMemory.objects.filter(
            user=self.user,
            project=self.project
        ).values('memory_category').annotate(
            count=models.Count('id')
        )
        
        return {
            'short_term_count': stm_count,
            'long_term_count': ltm_count,
            'categories': {item['memory_category']: item['count'] for item in ltm_by_category}
        }
    
    def get_recent_memories(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent memories across all types.
        Used for session restoration and context building.
        
        Args:
            limit: Maximum number of memories to return
            
        Returns:
            List of recent memory entries
        """
        recent_memories = []
        
        # Get recent short-term memories (not expired)
        recent_stm = ShortTermMemory.objects.filter(
            user=self.user,
            project=self.project,
            expires_at__gt=timezone.now()
        ).order_by('-created_at')[:limit // 2]
        
        for m in recent_stm:
            recent_memories.append({
                'id': str(m.id),
                'type': 'short_term',
                'key': m.memory_key,
                'content': m.content,
                'memory_type': m.memory_type,
                'created_at': m.created_at.isoformat()
            })
        
        # Get recent long-term memories
        recent_ltm = LongTermMemory.objects.filter(
            user=self.user,
            project=self.project
        ).order_by('-last_accessed_at')[:limit // 2]
        
        for m in recent_ltm:
            recent_memories.append({
                'id': str(m.id),
                'type': 'long_term',
                'key': m.memory_key,
                'content': m.content,
                'category': m.memory_category,
                'importance': m.importance_score,
                'created_at': m.created_at.isoformat(),
                'last_accessed': m.last_accessed_at.isoformat()
            })
        
        # Sort by created_at and limit
        recent_memories.sort(key=lambda x: x['created_at'], reverse=True)
        return recent_memories[:limit]

    # ==================== Autonomous Executor Support ====================
    
    def search(
        self,
        query: str,
        project_id: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search memories by query.
        Used by AutonomousExecutor.
        
        Args:
            query: Search query
            project_id: Optional project ID (uses self.project if not provided)
            limit: Maximum results
            
        Returns:
            List of matching memories
        """
        results = []
        
        # Search using semantic search
        semantic_results = self.search_memory(query, top_k=limit)
        results.extend(semantic_results)
        
        # Also search long-term memory by content
        ltm_results = LongTermMemory.objects.filter(
            user=self.user,
            project=self.project
        ).order_by('-importance_score')[:limit]
        
        for memory in ltm_results:
            content_text = self._content_to_text(memory.content)
            if query.lower() in content_text.lower():
                results.append({
                    'id': str(memory.id),
                    'key': memory.memory_key,
                    'content': memory.content,
                    'category': memory.memory_category,
                    'importance': memory.importance_score,
                    'source': 'long_term'
                })
        
        # Deduplicate and limit
        seen_keys = set()
        unique_results = []
        for r in results:
            key = r.get('key') or r.get('id')
            if key not in seen_keys:
                seen_keys.add(key)
                unique_results.append(r)
                if len(unique_results) >= limit:
                    break
        
        return unique_results
    
    def get_context(
        self,
        project_id: str = None,
        query: str = "",
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get context for autonomous execution.
        Used by AutonomousExecutor.
        
        Args:
            project_id: Optional project ID
            query: Query to find relevant context
            limit: Maximum items per category
            
        Returns:
            Context dictionary with actions, patterns, project info
        """
        context = {
            'actions': [],
            'patterns': [],
            'project': {}
        }
        
        # Get recent actions from short-term memory
        if self.project:
            recent_stm = ShortTermMemory.objects.filter(
                user=self.user,
                project=self.project,
                memory_type='context',
                expires_at__gt=timezone.now()
            ).order_by('-created_at')[:limit]
            
            context['actions'] = [
                {
                    'key': m.memory_key,
                    'content': m.content,
                    'created_at': m.created_at.isoformat()
                }
                for m in recent_stm
            ]
        
        # Get learned patterns from long-term memory
        patterns = self.get_memories_by_category('lesson_learned', limit=limit)
        context['patterns'] = patterns
        
        # Get project context
        if self.project:
            project_memories = self.get_memories_by_category('project_context', limit=5)
            context['project'] = {
                'name': self.project.name,
                'id': str(self.project.id),
                'memories': project_memories
            }
        
        # Add semantic search results if query provided
        if query:
            semantic_results = self.search_memory(query, top_k=5)
            context['relevant'] = semantic_results
        
        return context
    
    def store(
        self,
        content: Dict[str, Any],
        project_id: str = None,
        metadata: Dict[str, Any] = None
    ) -> LongTermMemory:
        """
        Store content in memory.
        Used by AutonomousExecutor.
        
        Args:
            content: Content to store
            project_id: Optional project ID
            metadata: Additional metadata
            
        Returns:
            Created memory entry
        """
        metadata = metadata or {}
        
        # Generate a key from content type or use UUID
        content_type = content.get('type', 'general')
        key = f"{content_type}_{uuid.uuid4().hex[:8]}"
        
        # Determine category from content
        category_map = {
            'autonomous_action': 'action_log',
            'decision': 'architectural_decision',
            'error': 'error_log',
            'lesson': 'lesson_learned',
            'preference': 'user_preference'
        }
        category = category_map.get(content_type, 'general')
        
        # Merge metadata into content
        if metadata:
            content['_metadata'] = metadata
        
        return self.store_long_term(
            key=key,
            content=content,
            category=category,
            importance=metadata.get('importance', 0.5),
            create_embedding=True
        )
