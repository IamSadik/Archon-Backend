"""
Memory Tools - Tools for interacting with the memory system.
"""
from typing import Dict, Any, List, Optional
from .base import BaseTool, ToolResult, ToolParameter, ToolCategory, ToolRegistry


@ToolRegistry.register
class SearchMemoryTool(BaseTool):
    """Search through memory for relevant information."""
    
    name = "search_memory"
    description = "Search memory for information related to a query"
    category = ToolCategory.MEMORY
    parameters = [
        ToolParameter(
            name="query",
            type="string",
            description="Search query to find relevant memories"
        ),
        ToolParameter(
            name="memory_type",
            type="string",
            description="Type of memory to search: 'all', 'short_term', 'long_term'",
            required=False,
            default="all",
            enum=["all", "short_term", "long_term"]
        ),
        ToolParameter(
            name="category",
            type="string",
            description="Filter by memory category",
            required=False,
            default=None
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum number of results",
            required=False,
            default=10
        ),
    ]
    
    def execute(
        self,
        query: str,
        memory_type: str = "all",
        category: str = None,
        limit: int = 10
    ) -> ToolResult:
        """Search memory."""
        try:
            memory_service = self.context.get('memory_service')
            if not memory_service:
                return ToolResult(success=False, error="Memory service not available")
            
            results = []
            
            # Semantic search
            if memory_type in ["all", "long_term"]:
                semantic_results = memory_service.search_memory(query, top_k=limit)
                results.extend(semantic_results)
            
            # Category filter
            if category:
                category_results = memory_service.get_memories_by_category(category, limit=limit)
                results.extend(category_results)
            
            # Deduplicate
            seen = set()
            unique_results = []
            for r in results:
                key = r.get('key') or r.get('id') or str(r.get('content', ''))[:50]
                if key not in seen:
                    seen.add(key)
                    unique_results.append(r)
            
            return ToolResult(
                success=True,
                data={
                    'results': unique_results[:limit],
                    'count': len(unique_results[:limit]),
                    'query': query
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@ToolRegistry.register
class StoreMemoryTool(BaseTool):
    """Store information in memory."""
    
    name = "store_memory"
    description = "Store information in long-term memory"
    category = ToolCategory.MEMORY
    parameters = [
        ToolParameter(
            name="key",
            type="string",
            description="Unique key for this memory"
        ),
        ToolParameter(
            name="content",
            type="object",
            description="Content to store (as JSON object)"
        ),
        ToolParameter(
            name="category",
            type="string",
            description="Memory category",
            required=False,
            default="general",
            enum=["architectural_decision", "user_preference", "constraint", "pattern", 
                  "mistake", "best_practice", "lesson_learned", "general"]
        ),
        ToolParameter(
            name="importance",
            type="string",
            description="Importance level: 'low', 'medium', 'high', 'critical'",
            required=False,
            default="medium",
            enum=["low", "medium", "high", "critical"]
        ),
    ]
    
    def execute(
        self,
        key: str,
        content: Dict[str, Any],
        category: str = "general",
        importance: str = "medium"
    ) -> ToolResult:
        """Store in memory."""
        try:
            memory_service = self.context.get('memory_service')
            if not memory_service:
                return ToolResult(success=False, error="Memory service not available")
            
            # Map importance string to score
            importance_map = {
                'low': 0.3,
                'medium': 0.5,
                'high': 0.7,
                'critical': 0.9
            }
            importance_score = importance_map.get(importance, 0.5)
            
            memory = memory_service.store_long_term(
                key=key,
                content=content,
                category=category,
                importance=importance_score
            )
            
            return ToolResult(
                success=True,
                data={
                    'id': str(memory.id),
                    'key': key,
                    'category': category,
                    'importance': importance_score,
                    'stored': True
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@ToolRegistry.register
class RecallDecisionTool(BaseTool):
    """Recall architectural decisions from memory."""
    
    name = "recall_decision"
    description = "Recall architectural decisions made for the project"
    category = ToolCategory.MEMORY
    parameters = [
        ToolParameter(
            name="topic",
            type="string",
            description="Topic or area to recall decisions for",
            required=False,
            default=""
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum number of decisions to return",
            required=False,
            default=5
        ),
    ]
    
    def execute(self, topic: str = "", limit: int = 5) -> ToolResult:
        """Recall decisions."""
        try:
            memory_service = self.context.get('memory_service')
            if not memory_service:
                return ToolResult(success=False, error="Memory service not available")
            
            # Get architectural decisions
            decisions = memory_service.get_memories_by_category(
                'architectural_decision',
                limit=limit * 2  # Get more to filter
            )
            
            # Filter by topic if provided
            if topic:
                topic_lower = topic.lower()
                decisions = [
                    d for d in decisions
                    if topic_lower in str(d.get('content', '')).lower()
                    or topic_lower in d.get('key', '').lower()
                ]
            
            return ToolResult(
                success=True,
                data={
                    'decisions': decisions[:limit],
                    'count': len(decisions[:limit]),
                    'topic': topic or 'all'
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
