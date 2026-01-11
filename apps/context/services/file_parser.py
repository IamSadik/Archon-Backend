"""
File Parser Service - Parses various file types for content extraction.
"""
import os
import hashlib
from typing import Dict, Any, List, Optional
from pathlib import Path


class FileParserService:
    """
    Service for parsing files and extracting content.
    Supports code files, documentation, and other text-based formats.
    """
    
    # File extensions to ignore
    IGNORE_EXTENSIONS = {
        '.pyc', '.pyo', '.so', '.dll', '.exe', '.bin',
        '.jpg', '.jpeg', '.png', '.gif', '.ico', '.svg', '.bmp',
        '.mp3', '.mp4', '.avi', '.mov', '.wav',
        '.zip', '.tar', '.gz', '.rar', '.7z',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx',
        '.db', '.sqlite', '.sqlite3',
        '.lock', '.log'
    }
    
    # Directories to ignore
    IGNORE_DIRS = {
        '__pycache__', '.git', '.svn', '.hg',
        'node_modules', 'venv', '.venv', 'env',
        '.idea', '.vscode', '.vs',
        'dist', 'build', '.next', '.nuxt',
        'coverage', '.pytest_cache', '.mypy_cache',
        'eggs', '.eggs', '*.egg-info',
    }
    
    # Code file extensions and their languages
    LANGUAGE_MAP = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.h': 'cpp',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.scala': 'scala',
        '.sql': 'sql',
        '.html': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.less': 'less',
        '.vue': 'vue',
        '.svelte': 'svelte',
    }
    
    # File type mapping
    FILE_TYPE_MAP = {
        '.md': 'md',
        '.markdown': 'md',
        '.txt': 'txt',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.xml': 'xml',
        '.toml': 'toml',
        '.ini': 'ini',
        '.cfg': 'ini',
        '.conf': 'ini',
        '.env': 'ini',
    }
    
    def __init__(self):
        """Initialize the file parser service."""
        pass
    
    def should_ignore(self, path: str) -> bool:
        """
        Check if a file or directory should be ignored.
        
        Args:
            path: File or directory path
            
        Returns:
            True if should be ignored
        """
        path_obj = Path(path)
        
        # Check directory names
        for part in path_obj.parts:
            if part in self.IGNORE_DIRS:
                return True
            # Check glob patterns
            for pattern in self.IGNORE_DIRS:
                if '*' in pattern and path_obj.match(pattern):
                    return True
        
        # Check file extensions
        if path_obj.suffix.lower() in self.IGNORE_EXTENSIONS:
            return True
        
        # Check hidden files
        if path_obj.name.startswith('.') and path_obj.name not in ('.env', '.gitignore'):
            return True
        
        return False
    
    def parse_file(self, file_path: str, content: str = None) -> Dict[str, Any]:
        """
        Parse a file and extract its content and metadata.
        
        Args:
            file_path: Path to the file
            content: Optional pre-loaded content
            
        Returns:
            Dictionary with parsed file information
        """
        path_obj = Path(file_path)
        
        # Read content if not provided
        if content is None:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    # Remove NULL bytes
                    content = content.replace('\x00', '')
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Failed to read file: {str(e)}'
                }
        
        # Get file info
        extension = path_obj.suffix.lower()
        file_name = path_obj.name
        
        # Determine file type
        if extension in self.LANGUAGE_MAP:
            file_type = 'code'
            language = self.LANGUAGE_MAP[extension]
        elif extension in self.FILE_TYPE_MAP:
            file_type = self.FILE_TYPE_MAP[extension]
            language = None
        else:
            file_type = 'other'
            language = None
        
        # Calculate content hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        # Get file size
        try:
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else len(content.encode())
        except:
            file_size = len(content.encode())
        
        # Extract metadata
        metadata = self._extract_metadata(content, file_type, language)
        
        return {
            'success': True,
            'file_path': str(file_path),
            'file_name': file_name,
            'file_extension': extension.lstrip('.'),
            'file_type': file_type,
            'language': language,
            'content': content,
            'content_hash': content_hash,
            'file_size_bytes': file_size,
            'metadata': metadata
        }
    
    def _extract_metadata(self, content: str, file_type: str, language: str) -> Dict[str, Any]:
        """
        Extract metadata from file content.
        
        Args:
            content: File content
            file_type: Type of file
            language: Programming language
            
        Returns:
            Metadata dictionary
        """
        metadata = {
            'lines_of_code': len(content.splitlines()),
            'character_count': len(content),
        }
        
        if file_type == 'code':
            metadata.update(self._extract_code_metadata(content, language))
        
        return metadata
    
    def _extract_code_metadata(self, content: str, language: str) -> Dict[str, Any]:
        """
        Extract code-specific metadata.
        
        Args:
            content: Code content
            language: Programming language
            
        Returns:
            Code metadata dictionary
        """
        metadata = {
            'functions': [],
            'classes': [],
            'imports': [],
            'exports': [],
        }
        
        lines = content.splitlines()
        
        if language == 'python':
            metadata.update(self._parse_python_quick(lines))
        elif language in ('javascript', 'typescript'):
            metadata.update(self._parse_javascript_quick(lines))
        elif language == 'java':
            metadata.update(self._parse_java_quick(lines))
        
        return metadata
    
    def _parse_python_quick(self, lines: List[str]) -> Dict[str, Any]:
        """Quick parse Python for basic metadata."""
        metadata = {
            'functions': [],
            'classes': [],
            'imports': [],
        }
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if stripped.startswith('def '):
                # Extract function name
                name_end = stripped.find('(')
                if name_end > 4:
                    metadata['functions'].append({
                        'name': stripped[4:name_end],
                        'line': i + 1
                    })
            
            elif stripped.startswith('class '):
                # Extract class name
                name_end = stripped.find('(') if '(' in stripped else stripped.find(':')
                if name_end > 6:
                    metadata['classes'].append({
                        'name': stripped[6:name_end],
                        'line': i + 1
                    })
            
            elif stripped.startswith('import ') or stripped.startswith('from '):
                metadata['imports'].append({
                    'statement': stripped,
                    'line': i + 1
                })
        
        return metadata
    
    def _parse_javascript_quick(self, lines: List[str]) -> Dict[str, Any]:
        """Quick parse JavaScript/TypeScript for basic metadata."""
        metadata = {
            'functions': [],
            'classes': [],
            'imports': [],
            'exports': [],
        }
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if 'function ' in stripped:
                # Try to extract function name
                start = stripped.find('function ') + 9
                end = stripped.find('(', start)
                if end > start:
                    name = stripped[start:end].strip()
                    if name:
                        metadata['functions'].append({
                            'name': name,
                            'line': i + 1
                        })
            
            elif stripped.startswith('class '):
                # Extract class name
                parts = stripped[6:].split()
                if parts:
                    name = parts[0].rstrip('{').rstrip()
                    metadata['classes'].append({
                        'name': name,
                        'line': i + 1
                    })
            
            elif stripped.startswith('import '):
                metadata['imports'].append({
                    'statement': stripped,
                    'line': i + 1
                })
            
            elif stripped.startswith('export '):
                metadata['exports'].append({
                    'statement': stripped,
                    'line': i + 1
                })
        
        return metadata
    
    def _parse_java_quick(self, lines: List[str]) -> Dict[str, Any]:
        """Quick parse Java for basic metadata."""
        metadata = {
            'functions': [],
            'classes': [],
            'imports': [],
        }
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if stripped.startswith('import '):
                metadata['imports'].append({
                    'statement': stripped,
                    'line': i + 1
                })
            
            elif 'class ' in stripped and not stripped.startswith('//'):
                # Try to extract class name
                start = stripped.find('class ') + 6
                end = len(stripped)
                for char in ['{', ' ', '<']:
                    pos = stripped.find(char, start)
                    if pos > start:
                        end = min(end, pos)
                
                name = stripped[start:end].strip()
                if name:
                    metadata['classes'].append({
                        'name': name,
                        'line': i + 1
                    })
        
        return metadata
    
    def get_file_summary(self, parsed: Dict[str, Any]) -> str:
        """
        Generate a summary of parsed file.
        
        Args:
            parsed: Parsed file data
            
        Returns:
            Summary string
        """
        parts = [
            f"File: {parsed['file_name']}",
            f"Type: {parsed['file_type']}",
        ]
        
        if parsed.get('language'):
            parts.append(f"Language: {parsed['language']}")
        
        metadata = parsed.get('metadata', {})
        parts.append(f"Lines: {metadata.get('lines_of_code', 0)}")
        
        if metadata.get('functions'):
            func_names = [f['name'] for f in metadata['functions'][:5]]
            parts.append(f"Functions: {', '.join(func_names)}")
        
        if metadata.get('classes'):
            class_names = [c['name'] for c in metadata['classes'][:5]]
            parts.append(f"Classes: {', '.join(class_names)}")
        
        return '\n'.join(parts)
