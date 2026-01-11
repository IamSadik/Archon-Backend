"""
Semantic Search Service - Handles vector similarity search using Pinecone.
"""
import time
from typing import List, Dict, Any, Optional
from django.conf import settings
from apps.vector_store.models import EmbeddingDocument, SemanticSearchLog
from apps.vector_store.services.embedding_service import EmbeddingService
from apps.projects.models import Project
from integrations.pinecone_config import get_pinecone_index


class SemanticSearchService:
    """
    Service for performing semantic search across embeddings.
    Uses Pinecone for vector similarity search.
    """
    
    def __init__(self, embedding_provider: str = 'gemini'):
        """
        Initialize the semantic search service.
        
        Args:
            embedding_provider: Provider for generating query embeddings
        """
        self.embedding_service = EmbeddingService(provider=embedding_provider)
        self.index = None
    
    def _get_index(self):
        """Lazy load Pinecone index."""
        if self.index is None:
            self.index = get_pinecone_index()
        return self.index
    
    def search(
        self,
        query: str,
        project: Project,
        top_k: int = 5,
        document_type: str = None,
        namespace: str = None,
        filters: Dict = None,
        include_content: bool = True,
        log_search: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search.
        
        Args:
            query: Search query text
            project: Project to search within
            top_k: Number of results to return
            document_type: Filter by document type
            namespace: Pinecone namespace (defaults to project namespace)
            filters: Additional metadata filters
            include_content: Whether to include full content in results
            log_search: Whether to log this search
            
        Returns:
            List of search results with scores
        """
        start_time = time.time()
        
        # Generate query embedding
        query_vector = self.embedding_service.embed_text(query)
        
        # Prepare namespace
        namespace = namespace or f"project_{project.id}"
        
        # Build filter
        pinecone_filter = {'project_id': str(project.id)}
        if document_type:
            pinecone_filter['document_type'] = document_type
        if filters:
            pinecone_filter.update(filters)
        
        # Query Pinecone
        index = self._get_index()
        results = index.query(
            vector=query_vector,
            top_k=top_k,
            namespace=namespace,
            filter=pinecone_filter,
            include_metadata=True
        )
        
        # Process results
        search_results = []
        result_ids = []
        scores = []
        
        for match in results.get('matches', []):
            pinecone_id = match['id']
            score = match['score']
            metadata = match.get('metadata', {})
            
            result_ids.append(pinecone_id)
            scores.append(score)
            
            result = {
                'pinecone_id': pinecone_id,
                'score': score,
                'document_type': metadata.get('document_type'),
                'source_id': metadata.get('source_id'),
                'metadata': metadata
            }
            
            # Include content if requested
            if include_content:
                # Try to get full content from database
                try:
                    embedding_doc = EmbeddingDocument.objects.get(pinecone_id=pinecone_id)
                    result['id'] = str(embedding_doc.id)
                    result['content'] = embedding_doc.content
                except EmbeddingDocument.DoesNotExist:
                    result['content'] = metadata.get('content_preview', '')
            
            search_results.append(result)
        
        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Log search if enabled
        if log_search:
            SemanticSearchLog.objects.create(
                project=project,
                query=query,
                top_k=top_k,
                result_count=len(search_results),
                result_ids=result_ids,
                scores=scores,
                latency_ms=latency_ms,
                namespace=namespace,
                filters=pinecone_filter
            )
        
        return search_results
    
    def search_similar(
        self,
        embedding_doc: EmbeddingDocument,
        top_k: int = 5,
        exclude_self: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find documents similar to a given embedding.
        
        Args:
            embedding_doc: Source embedding document
            top_k: Number of results to return
            exclude_self: Whether to exclude the source document
            
        Returns:
            List of similar documents
        """
        # Get the original embedding from Pinecone
        index = self._get_index()
        
        # Fetch the vector
        fetch_result = index.fetch(
            ids=[embedding_doc.pinecone_id],
            namespace=embedding_doc.namespace
        )
        
        vectors = fetch_result.get('vectors', {})
        if embedding_doc.pinecone_id not in vectors:
            return []
        
        source_vector = vectors[embedding_doc.pinecone_id]['values']
        
        # Search for similar
        actual_top_k = top_k + 1 if exclude_self else top_k
        
        results = index.query(
            vector=source_vector,
            top_k=actual_top_k,
            namespace=embedding_doc.namespace,
            filter={'project_id': str(embedding_doc.project.id)},
            include_metadata=True
        )
        
        # Process results
        search_results = []
        for match in results.get('matches', []):
            if exclude_self and match['id'] == embedding_doc.pinecone_id:
                continue
            
            result = {
                'pinecone_id': match['id'],
                'score': match['score'],
                'metadata': match.get('metadata', {})
            }
            
            # Get full content
            try:
                doc = EmbeddingDocument.objects.get(pinecone_id=match['id'])
                result['id'] = str(doc.id)
                result['content'] = doc.content
                result['document_type'] = doc.document_type
            except EmbeddingDocument.DoesNotExist:
                result['content'] = match.get('metadata', {}).get('content_preview', '')
            
            search_results.append(result)
            
            if len(search_results) >= top_k:
                break
        
        return search_results
    
    def hybrid_search(
        self,
        query: str,
        project: Project,
        top_k: int = 5,
        keyword_weight: float = 0.3,
        semantic_weight: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining keyword and semantic search.
        
        Args:
            query: Search query
            project: Project to search within
            top_k: Number of results
            keyword_weight: Weight for keyword matching
            semantic_weight: Weight for semantic similarity
            
        Returns:
            Combined and re-ranked results
        """
        # Semantic search
        semantic_results = self.search(
            query=query,
            project=project,
            top_k=top_k * 2,  # Get more for re-ranking
            log_search=False
        )
        
        # Keyword search from database
        from django.db.models import Q
        keyword_matches = EmbeddingDocument.objects.filter(
            project=project
        ).filter(
            Q(content__icontains=query) |
            Q(metadata__icontains=query)
        )[:top_k * 2]
        
        # Score combination
        combined_scores = {}
        
        # Add semantic scores
        for result in semantic_results:
            doc_id = result.get('pinecone_id')
            combined_scores[doc_id] = {
                'semantic_score': result['score'] * semantic_weight,
                'keyword_score': 0,
                'data': result
            }
        
        # Add keyword scores
        for doc in keyword_matches:
            doc_id = doc.pinecone_id
            if doc_id in combined_scores:
                combined_scores[doc_id]['keyword_score'] = keyword_weight
            else:
                combined_scores[doc_id] = {
                    'semantic_score': 0,
                    'keyword_score': keyword_weight,
                    'data': {
                        'id': str(doc.id),
                        'pinecone_id': doc.pinecone_id,
                        'content': doc.content,
                        'document_type': doc.document_type,
                        'source_id': doc.source_id,
                        'metadata': doc.metadata
                    }
                }
        
        # Calculate combined scores and sort
        results = []
        for doc_id, scores in combined_scores.items():
            total_score = scores['semantic_score'] + scores['keyword_score']
            result = scores['data'].copy()
            result['score'] = total_score
            result['semantic_score'] = scores['semantic_score']
            result['keyword_score'] = scores['keyword_score']
            results.append(result)
        
        # Sort by combined score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results[:top_k]
    
    def get_context_for_query(
        self,
        query: str,
        project: Project,
        max_tokens: int = 4000,
        document_types: List[str] = None
    ) -> str:
        """
        Get relevant context for a query, formatted for LLM consumption.
        
        Args:
            query: Query to find context for
            project: Project to search within
            max_tokens: Maximum tokens to include
            document_types: Types of documents to include
            
        Returns:
            Formatted context string
        """
        # Search for relevant content
        results = []
        
        if document_types:
            for doc_type in document_types:
                type_results = self.search(
                    query=query,
                    project=project,
                    top_k=5,
                    document_type=doc_type,
                    log_search=False
                )
                results.extend(type_results)
        else:
            results = self.search(
                query=query,
                project=project,
                top_k=10,
                log_search=False
            )
        
        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # Build context string within token limit
        context_parts = []
        current_tokens = 0
        
        for result in results:
            content = result.get('content', '')
            doc_type = result.get('document_type', 'unknown')
            
            # Estimate tokens (rough approximation)
            content_tokens = len(content.split())
            
            if current_tokens + content_tokens > max_tokens:
                # Truncate if needed
                remaining_tokens = max_tokens - current_tokens
                if remaining_tokens > 100:
                    words = content.split()[:remaining_tokens]
                    content = ' '.join(words) + '...'
                else:
                    break
            
            context_parts.append(f"[{doc_type.upper()}] (relevance: {result['score']:.2f})\n{content}")
            current_tokens += content_tokens
        
        return "\n\n---\n\n".join(context_parts)
