"""
Code Tools - Tools for interacting with the codebase.
"""
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from .base import BaseTool, ToolResult, ToolParameter, ToolCategory, ToolRegistry


@ToolRegistry.register
class ReadFileTool(BaseTool):
    """Read contents of a file."""
    
    name = "read_file"
    description = "Read the contents of a file from the project"
    category = ToolCategory.CODE
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file relative to project root"
        ),
        ToolParameter(
            name="start_line",
            type="integer",
            description="Starting line number (1-based)",
            required=False,
            default=1
        ),
        ToolParameter(
            name="end_line",
            type="integer",
            description="Ending line number (1-based, -1 for end of file)",
            required=False,
            default=-1
        ),
    ]
    
    def execute(self, file_path: str, start_line: int = 1, end_line: int = -1) -> ToolResult:
        """Read file contents."""
        try:
            # Get project root from context
            project_root = self.context.get('project_root', '.')
            full_path = Path(project_root) / file_path
            
            if not full_path.exists():
                return ToolResult(success=False, error=f"File not found: {file_path}")
            
            if not full_path.is_file():
                return ToolResult(success=False, error=f"Not a file: {file_path}")
            
            # Read file
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            
            # Apply line range
            if end_line == -1:
                end_line = total_lines
            
            start_idx = max(0, start_line - 1)
            end_idx = min(total_lines, end_line)
            
            content = ''.join(lines[start_idx:end_idx])
            
            return ToolResult(
                success=True,
                data={
                    'content': content,
                    'file_path': file_path,
                    'total_lines': total_lines,
                    'lines_read': f"{start_line}-{end_idx}"
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@ToolRegistry.register
class WriteFileTool(BaseTool):
    """Write or modify a file."""
    
    name = "write_file"
    description = "Write content to a file, creating it if necessary"
    category = ToolCategory.CODE
    requires_confirmation = True
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file relative to project root"
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Content to write to the file"
        ),
        ToolParameter(
            name="mode",
            type="string",
            description="Write mode: 'overwrite' or 'append'",
            required=False,
            default="overwrite",
            enum=["overwrite", "append"]
        ),
    ]
    
    def execute(self, file_path: str, content: str, mode: str = "overwrite") -> ToolResult:
        """Write to file."""
        try:
            project_root = self.context.get('project_root', '.')
            full_path = Path(project_root) / file_path
            
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            write_mode = 'w' if mode == 'overwrite' else 'a'
            with open(full_path, write_mode, encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult(
                success=True,
                data={
                    'file_path': file_path,
                    'mode': mode,
                    'bytes_written': len(content.encode('utf-8'))
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@ToolRegistry.register
class CreateFileTool(BaseTool):
    """Create a new file with content."""
    
    name = "create_file"
    description = "Create a new file with the given content"
    category = ToolCategory.CODE
    requires_confirmation = True
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path for the new file relative to project root"
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Initial content for the file"
        ),
    ]
    
    def execute(self, file_path: str, content: str) -> ToolResult:
        """Create a new file."""
        try:
            project_root = self.context.get('project_root', '.')
            full_path = Path(project_root) / file_path
            
            if full_path.exists():
                return ToolResult(success=False, error=f"File already exists: {file_path}")
            
            # Create parent directories
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create file
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult(
                success=True,
                data={
                    'file_path': file_path,
                    'created': True,
                    'bytes_written': len(content.encode('utf-8'))
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@ToolRegistry.register
class SearchCodeTool(BaseTool):
    """Search for patterns in code files."""
    
    name = "search_code"
    description = "Search for a pattern in project files"
    category = ToolCategory.CODE
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description="Search pattern (regex supported)"
        ),
        ToolParameter(
            name="file_pattern",
            type="string",
            description="Glob pattern for files to search (e.g., '*.py')",
            required=False,
            default="*"
        ),
        ToolParameter(
            name="directory",
            type="string",
            description="Directory to search in (relative to project root)",
            required=False,
            default="."
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum number of results to return",
            required=False,
            default=20
        ),
    ]
    
    def execute(
        self,
        pattern: str,
        file_pattern: str = "*",
        directory: str = ".",
        max_results: int = 20
    ) -> ToolResult:
        """Search for pattern in files."""
        try:
            project_root = self.context.get('project_root', '.')
            search_dir = Path(project_root) / directory
            
            if not search_dir.exists():
                return ToolResult(success=False, error=f"Directory not found: {directory}")
            
            # Compile regex
            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                return ToolResult(success=False, error=f"Invalid regex pattern: {e}")
            
            results = []
            files_searched = 0
            
            # Search files
            for file_path in search_dir.rglob(file_pattern):
                if not file_path.is_file():
                    continue
                
                # Skip binary files and common non-code directories
                if any(part in file_path.parts for part in ['.git', '__pycache__', 'node_modules', '.venv', 'venv']):
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = file_path.relative_to(project_root)
                                results.append({
                                    'file': str(rel_path),
                                    'line': line_num,
                                    'content': line.strip()[:200]  # Truncate long lines
                                })
                                
                                if len(results) >= max_results:
                                    break
                    
                    files_searched += 1
                    
                except Exception:
                    continue  # Skip files that can't be read
                
                if len(results) >= max_results:
                    break
            
            return ToolResult(
                success=True,
                data={
                    'results': results,
                    'count': len(results),
                    'files_searched': files_searched,
                    'truncated': len(results) >= max_results
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@ToolRegistry.register
class ListDirectoryTool(BaseTool):
    """List contents of a directory."""
    
    name = "list_directory"
    description = "List files and directories in a path"
    category = ToolCategory.CODE
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Directory path relative to project root",
            required=False,
            default="."
        ),
        ToolParameter(
            name="recursive",
            type="boolean",
            description="Whether to list recursively",
            required=False,
            default=False
        ),
        ToolParameter(
            name="max_depth",
            type="integer",
            description="Maximum depth for recursive listing",
            required=False,
            default=3
        ),
    ]
    
    def execute(
        self,
        path: str = ".",
        recursive: bool = False,
        max_depth: int = 3
    ) -> ToolResult:
        """List directory contents."""
        try:
            project_root = self.context.get('project_root', '.')
            target_dir = Path(project_root) / path
            
            if not target_dir.exists():
                return ToolResult(success=False, error=f"Directory not found: {path}")
            
            if not target_dir.is_dir():
                return ToolResult(success=False, error=f"Not a directory: {path}")
            
            entries = []
            
            def list_dir(dir_path: Path, depth: int = 0):
                if depth > max_depth:
                    return
                
                try:
                    for entry in sorted(dir_path.iterdir()):
                        # Skip hidden and common non-relevant directories
                        if entry.name.startswith('.') or entry.name in ['__pycache__', 'node_modules', '.venv', 'venv']:
                            continue
                        
                        rel_path = entry.relative_to(project_root)
                        
                        entry_info = {
                            'name': entry.name,
                            'path': str(rel_path),
                            'type': 'directory' if entry.is_dir() else 'file'
                        }
                        
                        if entry.is_file():
                            entry_info['size'] = entry.stat().st_size
                        
                        entries.append(entry_info)
                        
                        if recursive and entry.is_dir():
                            list_dir(entry, depth + 1)
                            
                except PermissionError:
                    pass
            
            list_dir(target_dir)
            
            return ToolResult(
                success=True,
                data={
                    'path': path,
                    'entries': entries,
                    'count': len(entries)
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
