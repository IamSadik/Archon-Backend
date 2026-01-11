"""
File Indexer Service - Indexes files and directories for a project.
"""
import os
import fnmatch
from typing import Dict, Any, List, Optional
from pathlib import Path
from apps.context.models import ContextFile, CodeAnalysis, FileIndex
from apps.context.services.file_parser import FileParserService
from apps.vector_store.services import EmbeddingService
from apps.projects.models import Project


class FileIndexerService:
    """
    Service for indexing project files and directories.
    Creates context files and optionally generates embeddings.
    """
    
    def __init__(self, project: Project, embedding_provider: str = 'gemini'):
        """
        Initialize the file indexer service.
        
        Args:
            project: Project to index files for
            embedding_provider: Provider for generating embeddings
        """
        self.project = project
        self.parser = FileParserService()
        self.embedding_service = None
        self.embedding_provider = embedding_provider
    
    def _get_embedding_service(self):
        """Lazy load embedding service."""
        if self.embedding_service is None:
            self.embedding_service = EmbeddingService(provider=self.embedding_provider)
        return self.embedding_service
    
    def index_file(
        self,
        file_path: str,
        content: str = None,
        parent_folder: ContextFile = None,
        analyze_code: bool = True,
        create_embeddings: bool = False
    ) -> Dict[str, Any]:
        """
        Index a single file.
        
        Args:
            file_path: Path to the file
            content: Optional pre-loaded content
            parent_folder: Parent folder ContextFile
            analyze_code: Whether to analyze code structure
            create_embeddings: Whether to create embeddings
            
        Returns:
            Dictionary with indexing result
        """
        # Check if should ignore
        if self.parser.should_ignore(file_path):
            return {'success': False, 'skipped': True, 'reason': 'ignored'}
        
        # Parse the file
        parsed = self.parser.parse_file(file_path, content)
        
        if not parsed.get('success'):
            return parsed
        
        # Check for existing file with same hash (deduplication)
        existing = ContextFile.objects.filter(
            project=self.project,
            content_hash=parsed['content_hash']
        ).first()
        
        if existing:
            return {
                'success': True,
                'skipped': True,
                'reason': 'duplicate',
                'existing_id': str(existing.id)
            }
        
        # Create or update context file
        context_file, created = ContextFile.objects.update_or_create(
            project=self.project,
            file_path=parsed['file_path'],
            defaults={
                'file_name': parsed['file_name'],
                'file_type': parsed['file_type'],
                'file_extension': parsed['file_extension'],
                'content': parsed['content'],
                'content_hash': parsed['content_hash'],
                'file_size_bytes': parsed['file_size_bytes'],
                'language': parsed.get('language'),
                'metadata': parsed.get('metadata', {}),
                'parent_folder': parent_folder,
            }
        )
        
        result = {
            'success': True,
            'created': created,
            'context_file_id': str(context_file.id),
            'file_path': parsed['file_path'],
            'file_type': parsed['file_type'],
        }
        
        # Analyze code if requested
        if analyze_code and parsed['file_type'] == 'code':
            analysis = self._analyze_code(context_file, parsed)
            result['analysis'] = analysis
        
        # Create embeddings if requested
        if create_embeddings:
            embeddings = self._create_embeddings(context_file, parsed)
            result['embeddings_created'] = embeddings
            context_file.is_indexed = True
            context_file.save(update_fields=['is_indexed'])
        
        return result
    
    def index_directory(
        self,
        directory_path: str,
        recursive: bool = True,
        include_patterns: List[str] = None,
        exclude_patterns: List[str] = None,
        analyze_code: bool = True,
        create_embeddings: bool = False,
        max_files: int = 1000
    ) -> Dict[str, Any]:
        """
        Index all files in a directory.
        
        Args:
            directory_path: Path to the directory
            recursive: Whether to index subdirectories
            include_patterns: File patterns to include
            exclude_patterns: File patterns to exclude
            analyze_code: Whether to analyze code structure
            create_embeddings: Whether to create embeddings
            max_files: Maximum number of files to index
            
        Returns:
            Dictionary with indexing results
        """
        if not os.path.isdir(directory_path):
            return {'success': False, 'error': 'Directory not found'}
        
        results = {
            'success': True,
            'files_indexed': 0,
            'files_skipped': 0,
            'files_failed': 0,
            'total_size_bytes': 0,
            'details': []
        }
        
        files_processed = 0
        
        # Walk directory
        for root, dirs, files in os.walk(directory_path):
            # Filter directories
            dirs[:] = [d for d in dirs if not self.parser.should_ignore(os.path.join(root, d))]
            
            if not recursive:
                dirs.clear()
            
            for file_name in files:
                if files_processed >= max_files:
                    results['truncated'] = True
                    break
                
                file_path = os.path.join(root, file_name)
                
                # Apply patterns
                if include_patterns:
                    if not any(fnmatch.fnmatch(file_name, p) for p in include_patterns):
                        continue
                
                if exclude_patterns:
                    if any(fnmatch.fnmatch(file_name, p) for p in exclude_patterns):
                        continue
                
                # Index the file
                try:
                    file_result = self.index_file(
                        file_path,
                        analyze_code=analyze_code,
                        create_embeddings=create_embeddings
                    )
                    
                    if file_result.get('success'):
                        if file_result.get('skipped'):
                            results['files_skipped'] += 1
                        else:
                            results['files_indexed'] += 1
                    else:
                        results['files_failed'] += 1
                    
                    results['details'].append(file_result)
                    files_processed += 1
                    
                except Exception as e:
                    results['files_failed'] += 1
                    results['details'].append({
                        'success': False,
                        'file_path': file_path,
                        'error': str(e)
                    })
            
            if files_processed >= max_files:
                break
        
        return results
    
    def _analyze_code(self, context_file: ContextFile, parsed: Dict) -> Dict[str, Any]:
        """
        Create or update code analysis for a file.
        
        Args:
            context_file: ContextFile instance
            parsed: Parsed file data
            
        Returns:
            Analysis result
        """
        metadata = parsed.get('metadata', {})
        
        analysis, created = CodeAnalysis.objects.update_or_create(
            context_file=context_file,
            defaults={
                'functions': metadata.get('functions', []),
                'classes': metadata.get('classes', []),
                'imports': metadata.get('imports', []),
                'exports': metadata.get('exports', []),
                'lines_of_code': metadata.get('lines_of_code', 0),
                'analyzer_version': '1.0.0'
            }
        )
        
        return {
            'analysis_id': str(analysis.id),
            'created': created,
            'functions_count': len(metadata.get('functions', [])),
            'classes_count': len(metadata.get('classes', [])),
        }
    
    def _create_embeddings(self, context_file: ContextFile, parsed: Dict) -> int:
        """
        Create embeddings for a file's content.
        
        Args:
            context_file: ContextFile instance
            parsed: Parsed file data
            
        Returns:
            Number of embeddings created
        """
        content = parsed.get('content', '')
        if not content:
            return 0
        
        embedding_service = self._get_embedding_service()
        
        # Chunk the content
        chunks = embedding_service.chunk_text(content)
        
        if not chunks:
            return 0
        
        # Prepare documents for bulk embedding
        documents = []
        for chunk in chunks:
            documents.append({
                'content': chunk['content'],
                'document_type': 'code' if parsed['file_type'] == 'code' else 'documentation',
                'source_id': str(context_file.id),
                'chunk_index': chunk['chunk_index'],
                'metadata': {
                    'file_path': parsed['file_path'],
                    'file_name': parsed['file_name'],
                    'language': parsed.get('language'),
                    'start_char': chunk['start_char'],
                    'end_char': chunk['end_char'],
                }
            })
        
        # Store embeddings
        created = embedding_service.store_embeddings_bulk(
            project=self.project,
            documents=documents
        )
        
        # Update context file with embedding reference
        if created:
            context_file.embedding_id = created[0].pinecone_id
            context_file.is_indexed = True
            context_file.save(update_fields=['embedding_id', 'is_indexed'])
        
        return len(created)
    
    def reindex_file(self, context_file: ContextFile, create_embeddings: bool = True) -> Dict[str, Any]:
        """
        Reindex an existing context file.
        
        Args:
            context_file: ContextFile to reindex
            create_embeddings: Whether to recreate embeddings
            
        Returns:
            Reindexing result
        """
        # Delete existing embeddings
        if create_embeddings:
            from apps.vector_store.models import EmbeddingDocument
            EmbeddingDocument.objects.filter(
                source_id=str(context_file.id)
            ).delete()
        
        # Re-parse and reindex
        return self.index_file(
            context_file.file_path,
            content=context_file.content,
            analyze_code=True,
            create_embeddings=create_embeddings
        )
    
    def get_project_stats(self) -> Dict[str, Any]:
        """
        Get indexing statistics for the project.
        
        Returns:
            Project indexing statistics
        """
        files = ContextFile.objects.filter(project=self.project)
        
        return {
            'total_files': files.count(),
            'indexed_files': files.filter(is_indexed=True).count(),
            'code_files': files.filter(file_type='code').count(),
            'document_files': files.exclude(file_type='code').count(),
            'total_size_bytes': sum(f.file_size_bytes or 0 for f in files),
            'languages': list(files.exclude(language__isnull=True).values_list('language', flat=True).distinct()),
        }
