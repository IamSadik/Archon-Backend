"""
Code Analyzer Service - Analyzes code files for structure and dependencies.
"""
import ast
import re
from typing import Dict, Any, List, Optional
from apps.context.models import ContextFile, CodeAnalysis


class CodeAnalyzerService:
    """
    Service for analyzing code files.
    Extracts functions, classes, imports, dependencies, and complexity metrics.
    """
    
    def __init__(self):
        """Initialize the code analyzer service."""
        self.supported_languages = ['python', 'javascript', 'typescript', 'java']
    
    def analyze_file(self, context_file: ContextFile) -> CodeAnalysis:
        """
        Analyze a code file and create/update analysis record.
        
        Args:
            context_file: ContextFile instance to analyze
            
        Returns:
            CodeAnalysis instance
        """
        if not context_file.content:
            raise ValueError("File has no content to analyze")
        
        language = context_file.language
        content = context_file.content
        
        # Get analysis based on language
        if language == 'python':
            analysis_data = self._analyze_python(content)
        elif language in ('javascript', 'typescript'):
            analysis_data = self._analyze_javascript(content)
        elif language == 'java':
            analysis_data = self._analyze_java(content)
        else:
            analysis_data = self._analyze_generic(content)
        
        # Calculate complexity
        complexity = self._calculate_complexity(content, language)
        analysis_data['complexity_score'] = complexity
        
        # Count lines of code
        analysis_data['lines_of_code'] = self._count_lines_of_code(content)
        
        # Create or update analysis
        analysis, created = CodeAnalysis.objects.update_or_create(
            context_file=context_file,
            defaults={
                'functions': analysis_data.get('functions', []),
                'classes': analysis_data.get('classes', []),
                'imports': analysis_data.get('imports', []),
                'exports': analysis_data.get('exports', []),
                'lines_of_code': analysis_data.get('lines_of_code', 0),
                'complexity_score': analysis_data.get('complexity_score'),
                'dependencies': analysis_data.get('dependencies', []),
                'dependent_files': [],
                'analyzer_version': '1.0.0'
            }
        )
        
        return analysis
    
    def _analyze_python(self, content: str) -> Dict[str, Any]:
        """Analyze Python code."""
        result = {
            'functions': [],
            'classes': [],
            'imports': [],
            'exports': [],
            'dependencies': []
        }
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_info = {
                        'name': node.name,
                        'line': node.lineno,
                        'end_line': getattr(node, 'end_lineno', node.lineno),
                        'args': [arg.arg for arg in node.args.args],
                        'decorators': [self._get_decorator_name(d) for d in node.decorator_list],
                        'docstring': ast.get_docstring(node) or '',
                        'is_async': False
                    }
                    result['functions'].append(func_info)
                    
                elif isinstance(node, ast.AsyncFunctionDef):
                    func_info = {
                        'name': node.name,
                        'line': node.lineno,
                        'end_line': getattr(node, 'end_lineno', node.lineno),
                        'args': [arg.arg for arg in node.args.args],
                        'decorators': [self._get_decorator_name(d) for d in node.decorator_list],
                        'docstring': ast.get_docstring(node) or '',
                        'is_async': True
                    }
                    result['functions'].append(func_info)
                    
                elif isinstance(node, ast.ClassDef):
                    methods = []
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            methods.append({
                                'name': item.name,
                                'line': item.lineno,
                                'is_async': isinstance(item, ast.AsyncFunctionDef)
                            })
                    
                    class_info = {
                        'name': node.name,
                        'line': node.lineno,
                        'end_line': getattr(node, 'end_lineno', node.lineno),
                        'bases': [self._get_name(base) for base in node.bases],
                        'methods': methods,
                        'docstring': ast.get_docstring(node) or ''
                    }
                    result['classes'].append(class_info)
                    
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        result['imports'].append({
                            'module': alias.name,
                            'alias': alias.asname,
                            'line': node.lineno
                        })
                        result['dependencies'].append(alias.name.split('.')[0])
                        
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        result['imports'].append({
                            'module': module,
                            'name': alias.name,
                            'alias': alias.asname,
                            'line': node.lineno
                        })
                    if module:
                        result['dependencies'].append(module.split('.')[0])
            
            # Remove duplicates from dependencies
            result['dependencies'] = list(set(result['dependencies']))
            
        except SyntaxError as e:
            result['parse_error'] = str(e)
        
        return result
    
    def _analyze_javascript(self, content: str) -> Dict[str, Any]:
        """Analyze JavaScript/TypeScript code."""
        result = {
            'functions': [],
            'classes': [],
            'imports': [],
            'exports': [],
            'dependencies': []
        }
        
        # Function patterns
        func_patterns = [
            (r'function\s+(\w+)\s*\(([^)]*)\)', 'function'),
            (r'const\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>', 'arrow'),
            (r'const\s+(\w+)\s*=\s*(?:async\s*)?function\s*\(([^)]*)\)', 'expression'),
            (r'(\w+)\s*\(([^)]*)\)\s*{', 'method'),
        ]
        
        for pattern, func_type in func_patterns:
            for match in re.finditer(pattern, content):
                name = match.group(1)
                args = match.group(2).split(',') if match.group(2) else []
                args = [a.strip().split(':')[0].strip() for a in args if a.strip()]
                
                result['functions'].append({
                    'name': name,
                    'line': content[:match.start()].count('\n') + 1,
                    'args': args,
                    'type': func_type
                })
        
        # Class pattern
        class_pattern = r'class\s+(\w+)\s*(?:extends\s+(\w+))?\s*{'
        for match in re.finditer(class_pattern, content):
            result['classes'].append({
                'name': match.group(1),
                'line': content[:match.start()].count('\n') + 1,
                'extends': match.group(2)
            })
        
        # Import patterns
        import_patterns = [
            r"import\s+(?:{([^}]+)}|(\w+))\s+from\s+['\"]([^'\"]+)['\"]",
            r"import\s+['\"]([^'\"]+)['\"]",
            r"require\s*\(['\"]([^'\"]+)['\"]\)",
        ]
        
        for pattern in import_patterns:
            for match in re.finditer(pattern, content):
                groups = match.groups()
                module = groups[-1] if groups[-1] else groups[0]
                result['imports'].append({
                    'module': module,
                    'line': content[:match.start()].count('\n') + 1
                })
                if not module.startswith('.'):
                    result['dependencies'].append(module.split('/')[0])
        
        # Export patterns
        export_patterns = [
            r'export\s+(?:default\s+)?(?:class|function|const|let|var)\s+(\w+)',
            r'export\s*{\s*([^}]+)\s*}',
            r'module\.exports\s*=\s*(\w+)',
        ]
        
        for pattern in export_patterns:
            for match in re.finditer(pattern, content):
                exports = match.group(1)
                if ',' in exports:
                    result['exports'].extend([e.strip() for e in exports.split(',')])
                else:
                    result['exports'].append(exports.strip())
        
        result['dependencies'] = list(set(result['dependencies']))
        
        return result
    
    def _analyze_java(self, content: str) -> Dict[str, Any]:
        """Analyze Java code."""
        result = {
            'functions': [],
            'classes': [],
            'imports': [],
            'exports': [],
            'dependencies': []
        }
        
        # Import pattern
        for match in re.finditer(r'import\s+([\w.]+);', content):
            module = match.group(1)
            result['imports'].append({
                'module': module,
                'line': content[:match.start()].count('\n') + 1
            })
            # Get package name as dependency
            parts = module.split('.')
            if len(parts) >= 2:
                result['dependencies'].append(parts[0] + '.' + parts[1])
        
        # Class pattern
        class_pattern = r'(?:public|private|protected)?\s*(?:abstract|final)?\s*class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?'
        for match in re.finditer(class_pattern, content):
            result['classes'].append({
                'name': match.group(1),
                'line': content[:match.start()].count('\n') + 1,
                'extends': match.group(2),
                'implements': [i.strip() for i in (match.group(3) or '').split(',')] if match.group(3) else []
            })
        
        # Method pattern
        method_pattern = r'(?:public|private|protected)?\s*(?:static)?\s*(?:final)?\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)'
        for match in re.finditer(method_pattern, content):
            return_type = match.group(1)
            name = match.group(2)
            args = match.group(3)
            
            if name not in ('if', 'while', 'for', 'switch', 'catch'):
                result['functions'].append({
                    'name': name,
                    'line': content[:match.start()].count('\n') + 1,
                    'return_type': return_type,
                    'args': args
                })
        
        result['dependencies'] = list(set(result['dependencies']))
        
        return result
    
    def _analyze_generic(self, content: str) -> Dict[str, Any]:
        """Generic analysis for unsupported languages."""
        return {
            'functions': [],
            'classes': [],
            'imports': [],
            'exports': [],
            'dependencies': []
        }
    
    def _get_decorator_name(self, node) -> str:
        """Get decorator name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return str(node)
    
    def _get_name(self, node) -> str:
        """Get name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        return str(node)
    
    def _calculate_complexity(self, content: str, language: str) -> float:
        """
        Calculate cyclomatic complexity approximation.
        
        Args:
            content: Code content
            language: Programming language
            
        Returns:
            Complexity score
        """
        complexity = 1  # Base complexity
        
        # Control flow keywords that increase complexity
        control_patterns = [
            r'\bif\b', r'\belif\b', r'\belse\b',
            r'\bfor\b', r'\bwhile\b',
            r'\btry\b', r'\bexcept\b', r'\bcatch\b',
            r'\bcase\b', r'\bswitch\b',
            r'\band\b', r'\bor\b', r'\b&&\b', r'\b\|\|\b',
            r'\?',  # Ternary operator
        ]
        
        for pattern in control_patterns:
            complexity += len(re.findall(pattern, content))
        
        return round(complexity, 2)
    
    def _count_lines_of_code(self, content: str) -> int:
        """
        Count lines of code (excluding comments and blank lines).
        
        Args:
            content: Code content
            
        Returns:
            Number of lines of code
        """
        lines = content.split('\n')
        code_lines = 0
        in_multiline_comment = False
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines
            if not stripped:
                continue
            
            # Handle multiline comments
            if '"""' in stripped or "'''" in stripped:
                in_multiline_comment = not in_multiline_comment
                continue
            
            if in_multiline_comment:
                continue
            
            # Skip single-line comments
            if stripped.startswith('#') or stripped.startswith('//'):
                continue
            
            code_lines += 1
        
        return code_lines
    
    def find_dependencies(self, context_file: ContextFile) -> List[str]:
        """
        Find file dependencies.
        
        Args:
            context_file: ContextFile to find dependencies for
            
        Returns:
            List of dependency file paths
        """
        try:
            analysis = context_file.analysis
            return analysis.dependencies
        except CodeAnalysis.DoesNotExist:
            return []
    
    def get_file_summary(self, context_file: ContextFile) -> str:
        """
        Generate a summary of a code file for LLM context.
        
        Args:
            context_file: ContextFile to summarize
            
        Returns:
            Summary string
        """
        try:
            analysis = context_file.analysis
        except CodeAnalysis.DoesNotExist:
            return f"File: {context_file.file_name} ({context_file.language or 'unknown'})"
        
        summary_parts = [
            f"File: {context_file.file_name}",
            f"Language: {context_file.language or 'unknown'}",
            f"Lines of code: {analysis.lines_of_code}",
        ]
        
        if analysis.classes:
            class_names = [c.get('name', 'Unknown') if isinstance(c, dict) else str(c) for c in analysis.classes]
            summary_parts.append(f"Classes: {', '.join(class_names)}")
        
        if analysis.functions:
            func_names = [f.get('name', 'Unknown') if isinstance(f, dict) else str(f) for f in analysis.functions[:10]]
            summary_parts.append(f"Functions: {', '.join(func_names)}")
            if len(analysis.functions) > 10:
                summary_parts.append(f"  ... and {len(analysis.functions) - 10} more")
        
        if analysis.imports:
            summary_parts.append(f"Imports: {len(analysis.imports)} modules")
        
        if analysis.complexity_score:
            summary_parts.append(f"Complexity: {analysis.complexity_score}")
        
        return '\n'.join(summary_parts)
