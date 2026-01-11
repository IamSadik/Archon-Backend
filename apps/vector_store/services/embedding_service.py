"""
Embedding Service - Handles text embedding generation and storage in Pinecone.
"""
import uuid
import time
from typing import List, Dict, Any, Optional
from django.conf import settings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openai import OpenAIEmbeddings
from integrations.pinecone_config import get_pinecone_index
from apps.vector_store.models import EmbeddingDocument
from apps.projects.models import Project


class EmbeddingService:
    """
    Service for generating and managing embeddings.
    Uses Gemini or OpenAI for embedding generation and Pinecone for storage.
    """
    
    # Chunk settings
    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 200
    
    def __init__(self, provider: str = 'gemini'):
        """
        Initialize the embedding service.
        
        Args:
            provider: Embedding provider ('gemini' or 'openai')
        """
        self.provider = provider
        self.embeddings = self._get_embeddings_model(provider)
        self.index = None  # Lazy load Pinecone index
    
    def _get_embeddings_model(self, provider: str):
        """Get the embeddings model based on provider."""
        if provider == 'openai':
            return OpenAIEmbeddings(
                openai_api_key=settings.OPENAI_API_KEY,
                model="text-embedding-3-small"
            )
        else:  # Default to Gemini
            return GoogleGenerativeAIEmbeddings(
                model="models/text-embedding-004",
                google_api_key=settings.GEMINI_API_KEY
            )
    
    def _get_index(self):
        """Lazy load Pinecone index."""
        if self.index is None:
            self.index = get_pinecone_index()
        return self.index
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        return self.embeddings.embed_query(text)
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        return self.embeddings.embed_documents(texts)
    
    def chunk_text(
        self,
        text: str,
        chunk_size: int = None,
        chunk_overlap: int = None
    ) -> List[Dict[str, Any]]:
        """
        Split text into chunks for embedding.
        
        Args:
            text: Text to chunk
            chunk_size: Maximum chunk size in characters
            chunk_overlap: Overlap between chunks
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        chunk_size = chunk_size or self.DEFAULT_CHUNK_SIZE
        chunk_overlap = chunk_overlap or self.DEFAULT_CHUNK_OVERLAP
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]
            
            # Try to break at sentence or word boundary
            if end < len(text):
                # Look for sentence boundary
                last_period = chunk_text.rfind('.')
                last_newline = chunk_text.rfind('\n')
                break_point = max(last_period, last_newline)
                
                if break_point > chunk_size * 0.5:  # Only break if we're past halfway
                    chunk_text = chunk_text[:break_point + 1]
                    end = start + break_point + 1
            
            chunks.append({
                'content': chunk_text.strip(),
                'chunk_index': chunk_index,
                'start_char': start,
                'end_char': end,
                'token_count': len(chunk_text.split())  # Approximate token count
            })
            
            start = end - chunk_overlap
            chunk_index += 1
        
        return chunks
    
    def store_embedding(
        self,
        project: Project,
        content: str,
        document_type: str,
        source_id: str = '',
        metadata: Dict = None,
        namespace: str = ''
    ) -> EmbeddingDocument:
        """
        Generate embedding and store in Pinecone.
        
        Args:
            project: Project instance
            content: Text content to embed
            document_type: Type of document
            source_id: ID of source document
            metadata: Additional metadata
            namespace: Pinecone namespace
            
        Returns:
            Created EmbeddingDocument instance
        """
        # Generate embedding
        embedding_vector = self.embed_text(content)
        
        # Generate unique Pinecone ID
        pinecone_id = f"{project.id}_{document_type}_{uuid.uuid4().hex[:12]}"
        
        # Prepare metadata for Pinecone
        pinecone_metadata = {
            'project_id': str(project.id),
            'document_type': document_type,
            'source_id': source_id,
            'content_preview': content[:500] if len(content) > 500 else content,
            **(metadata or {})
        }
        
        # Store in Pinecone
        index = self._get_index()
        namespace = namespace or f"project_{project.id}"
        
        index.upsert(
            vectors=[{
                'id': pinecone_id,
                'values': embedding_vector,
                'metadata': pinecone_metadata
            }],
            namespace=namespace
        )
        
        # Create database record
        embedding_doc = EmbeddingDocument.objects.create(
            project=project,
            document_type=document_type,
            source_id=source_id,
            content=content,
            pinecone_id=pinecone_id,
            namespace=namespace,
            metadata=metadata or {},
            token_count=len(content.split())
        )
        
        return embedding_doc
    
    def store_embeddings_bulk(
        self,
        project: Project,
        documents: List[Dict[str, Any]],
        namespace: str = ''
    ) -> List[EmbeddingDocument]:
        """
        Store multiple embeddings in bulk.
        
        Args:
            project: Project instance
            documents: List of document dicts with content, document_type, etc.
            namespace: Pinecone namespace
            
        Returns:
            List of created EmbeddingDocument instances
        """
        if not documents:
            return []
        
        # Extract contents for batch embedding
        contents = [doc['content'] for doc in documents]
        
        # Generate embeddings in batch
        embedding_vectors = self.embed_texts(contents)
        
        # Prepare Pinecone vectors
        namespace = namespace or f"project_{project.id}"
        pinecone_vectors = []
        db_records = []
        
        for i, (doc, vector) in enumerate(zip(documents, embedding_vectors)):
            pinecone_id = f"{project.id}_{doc.get('document_type', 'unknown')}_{uuid.uuid4().hex[:12]}"
            
            pinecone_metadata = {
                'project_id': str(project.id),
                'document_type': doc.get('document_type', 'unknown'),
                'source_id': doc.get('source_id', ''),
                'content_preview': doc['content'][:500] if len(doc['content']) > 500 else doc['content'],
                **(doc.get('metadata', {}))
            }
            
            pinecone_vectors.append({
                'id': pinecone_id,
                'values': vector,
                'metadata': pinecone_metadata
            })
            
            db_records.append(EmbeddingDocument(
                project=project,
                document_type=doc.get('document_type', 'unknown'),
                source_id=doc.get('source_id', ''),
                content=doc['content'],
                chunk_index=doc.get('chunk_index', i),
                pinecone_id=pinecone_id,
                namespace=namespace,
                metadata=doc.get('metadata', {}),
                token_count=len(doc['content'].split())
            ))
        
        # Batch upsert to Pinecone (in batches of 100)
        index = self._get_index()
        batch_size = 100
        
        for i in range(0, len(pinecone_vectors), batch_size):
            batch = pinecone_vectors[i:i + batch_size]
            index.upsert(vectors=batch, namespace=namespace)
        
        # Bulk create database records
        created_docs = EmbeddingDocument.objects.bulk_create(db_records)
        
        return created_docs
    
    def delete_embedding(self, embedding_doc: EmbeddingDocument):
        """
        Delete embedding from Pinecone and database.
        
        Args:
            embedding_doc: EmbeddingDocument instance to delete
        """
        # Delete from Pinecone
        index = self._get_index()
        index.delete(ids=[embedding_doc.pinecone_id], namespace=embedding_doc.namespace)
        
        # Delete from database
        embedding_doc.delete()
    
    def delete_embeddings_by_source(
        self,
        project: Project,
        source_id: str,
        namespace: str = ''
    ):
        """
        Delete all embeddings for a source document.
        
        Args:
            project: Project instance
            source_id: Source document ID
            namespace: Pinecone namespace
        """
        namespace = namespace or f"project_{project.id}"
        
        # Get all embeddings for this source
        embeddings = EmbeddingDocument.objects.filter(
            project=project,
            source_id=source_id
        )
        
        # Delete from Pinecone
        pinecone_ids = list(embeddings.values_list('pinecone_id', flat=True))
        if pinecone_ids:
            index = self._get_index()
            index.delete(ids=pinecone_ids, namespace=namespace)
        
        # Delete from database
        embeddings.delete()
    
    def update_embedding(
        self,
        embedding_doc: EmbeddingDocument,
        new_content: str
    ) -> EmbeddingDocument:
        """
        Update an existing embedding with new content.
        
        Args:
            embedding_doc: EmbeddingDocument instance to update
            new_content: New text content
            
        Returns:
            Updated EmbeddingDocument instance
        """
        # Generate new embedding
        embedding_vector = self.embed_text(new_content)
        
        # Update in Pinecone
        index = self._get_index()
        pinecone_metadata = {
            'project_id': str(embedding_doc.project.id),
            'document_type': embedding_doc.document_type,
            'source_id': embedding_doc.source_id,
            'content_preview': new_content[:500] if len(new_content) > 500 else new_content,
            **embedding_doc.metadata
        }
        
        index.upsert(
            vectors=[{
                'id': embedding_doc.pinecone_id,
                'values': embedding_vector,
                'metadata': pinecone_metadata
            }],
            namespace=embedding_doc.namespace
        )
        
        # Update database record
        embedding_doc.content = new_content
        embedding_doc.token_count = len(new_content.split())
        embedding_doc.save()
        
        return embedding_doc
