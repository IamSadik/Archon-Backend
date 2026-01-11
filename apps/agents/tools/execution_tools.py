"""
Execution Tools - Tools for running commands and tests.
"""
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from .base import BaseTool, ToolResult, ToolParameter, ToolCategory, ToolRegistry


@ToolRegistry.register
class RunCommandTool(BaseTool):
    """Run a shell command."""
    
    name = "run_command"
    description = "Run a shell command in the project directory"
    category = ToolCategory.EXECUTION
    requires_confirmation = True
    parameters = [
        ToolParameter(
            name="command",
            type="string",
            description="Command to execute"
        ),
        ToolParameter(
            name="working_dir",
            type="string",
            description="Working directory (relative to project root)",
            required=False,
            default="."
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Timeout in seconds",
            required=False,
            default=60
        ),
    ]
    
    # Commands that are safe to run without confirmation
    SAFE_COMMANDS = [
        'ls', 'dir', 'cat', 'head', 'tail', 'grep', 'find',
        'pwd', 'echo', 'which', 'type', 'python --version',
        'pip list', 'pip show', 'npm list', 'git status',
        'git log', 'git branch', 'git diff'
    ]
    
    def execute(
        self,
        command: str,
        working_dir: str = ".",
        timeout: int = 60
    ) -> ToolResult:
        """Run command."""
        try:
            project_root = self.context.get('project_root', '.')
            cwd = Path(project_root) / working_dir
            
            if not cwd.exists():
                return ToolResult(success=False, error=f"Directory not found: {working_dir}")
            
            # Check for dangerous commands
            dangerous_patterns = ['rm -rf', 'del /s', 'format', 'mkfs', ':(){', 'fork bomb']
            for pattern in dangerous_patterns:
                if pattern in command.lower():
                    return ToolResult(
                        success=False,
                        error=f"Potentially dangerous command blocked: {pattern}"
                    )
            
            # Run command
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return ToolResult(
                success=result.returncode == 0,
                data={
                    'stdout': result.stdout[:10000],  # Limit output size
                    'stderr': result.stderr[:5000],
                    'return_code': result.returncode,
                    'command': command
                },
                error=result.stderr if result.returncode != 0 else None
            )
            
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"Command timed out after {timeout} seconds")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@ToolRegistry.register
class RunTestsTool(BaseTool):
    """Run tests for the project."""
    
    name = "run_tests"
    description = "Run tests for the project using the appropriate test framework"
    category = ToolCategory.EXECUTION
    parameters = [
        ToolParameter(
            name="test_path",
            type="string",
            description="Path to test file or directory",
            required=False,
            default=""
        ),
        ToolParameter(
            name="framework",
            type="string",
            description="Test framework to use",
            required=False,
            default="auto",
            enum=["auto", "pytest", "unittest", "jest", "mocha"]
        ),
        ToolParameter(
            name="verbose",
            type="boolean",
            description="Enable verbose output",
            required=False,
            default=True
        ),
        ToolParameter(
            name="pattern",
            type="string",
            description="Pattern to filter tests",
            required=False,
            default=""
        ),
    ]
    
    def execute(
        self,
        test_path: str = "",
        framework: str = "auto",
        verbose: bool = True,
        pattern: str = ""
    ) -> ToolResult:
        """Run tests."""
        try:
            project_root = self.context.get('project_root', '.')
            
            # Auto-detect framework if needed
            if framework == "auto":
                framework = self._detect_framework(project_root)
            
            # Build command
            if framework == "pytest":
                cmd = ["pytest"]
                if verbose:
                    cmd.append("-v")
                if pattern:
                    cmd.extend(["-k", pattern])
                if test_path:
                    cmd.append(test_path)
                    
            elif framework == "unittest":
                cmd = ["python", "-m", "unittest"]
                if verbose:
                    cmd.append("-v")
                if test_path:
                    cmd.append(test_path)
                    
            elif framework == "jest":
                cmd = ["npx", "jest"]
                if verbose:
                    cmd.append("--verbose")
                if pattern:
                    cmd.extend(["--testNamePattern", pattern])
                if test_path:
                    cmd.append(test_path)
                    
            elif framework == "mocha":
                cmd = ["npx", "mocha"]
                if pattern:
                    cmd.extend(["--grep", pattern])
                if test_path:
                    cmd.append(test_path)
            else:
                return ToolResult(success=False, error=f"Unknown framework: {framework}")
            
            # Run tests
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for tests
            )
            
            # Parse results
            test_output = result.stdout + result.stderr
            passed = result.returncode == 0
            
            return ToolResult(
                success=passed,
                data={
                    'framework': framework,
                    'output': test_output[:20000],  # Limit output
                    'return_code': result.returncode,
                    'passed': passed,
                    'test_path': test_path or 'all'
                },
                error=None if passed else "Some tests failed"
            )
            
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="Tests timed out after 5 minutes")
        except FileNotFoundError as e:
            return ToolResult(success=False, error=f"Test framework not found: {e}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    def _detect_framework(self, project_root: str) -> str:
        """Detect the test framework used in the project."""
        root = Path(project_root)
        
        # Check for Python test frameworks
        if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists():
            return "pytest"
        if (root / "setup.py").exists():
            return "pytest"  # Default for Python projects
        
        # Check for JavaScript test frameworks
        package_json = root / "package.json"
        if package_json.exists():
            try:
                import json
                with open(package_json) as f:
                    pkg = json.load(f)
                    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
                    if 'jest' in deps:
                        return "jest"
                    if 'mocha' in deps:
                        return "mocha"
            except Exception:
                pass
        
        # Default to pytest for Python projects
        if any(root.glob("**/*.py")):
            return "pytest"
        
        return "pytest"  # Default fallback
