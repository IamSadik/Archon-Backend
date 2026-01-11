"""
Base Tool - Abstract base class for all agent tools.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Type
from enum import Enum


class ToolCategory(Enum):
    """Categories of tools."""
    CODE = "code"
    MEMORY = "memory"
    PLANNING = "planning"
    EXECUTION = "execution"
    COMMUNICATION = "communication"


@dataclass
class ToolResult:
    """Result returned by a tool execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'success': self.success,
            'data': self.data,
            'error': self.error,
            'metadata': self.metadata
        }


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str  # 'string', 'integer', 'boolean', 'array', 'object'
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None


class BaseTool(ABC):
    """
    Abstract base class for all agent tools.
    
    Tools are the primary way agents interact with:
    - The codebase (read/write files)
    - Memory systems (store/retrieve)
    - Planning systems (features/tasks)
    - External systems (run commands, tests)
    """
    
    # Tool metadata - override in subclasses
    name: str = "base_tool"
    description: str = "Base tool"
    category: ToolCategory = ToolCategory.CODE
    parameters: List[ToolParameter] = []
    requires_confirmation: bool = False
    
    def __init__(self, context: Dict[str, Any] = None):
        """
        Initialize the tool with context.
        
        Args:
            context: Execution context containing user, project, services
        """
        self.context = context or {}
        self.user = context.get('user')
        self.project = context.get('project')
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with given parameters.
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            ToolResult with execution outcome
        """
        pass
    
    def validate_params(self, **kwargs) -> Optional[str]:
        """
        Validate input parameters.
        
        Args:
            **kwargs: Parameters to validate
            
        Returns:
            Error message if validation fails, None otherwise
        """
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return f"Missing required parameter: {param.name}"
            
            if param.name in kwargs:
                value = kwargs[param.name]
                
                # Type validation
                if param.type == 'string' and not isinstance(value, str):
                    return f"Parameter {param.name} must be a string"
                elif param.type == 'integer' and not isinstance(value, int):
                    return f"Parameter {param.name} must be an integer"
                elif param.type == 'boolean' and not isinstance(value, bool):
                    return f"Parameter {param.name} must be a boolean"
                elif param.type == 'array' and not isinstance(value, list):
                    return f"Parameter {param.name} must be an array"
                elif param.type == 'object' and not isinstance(value, dict):
                    return f"Parameter {param.name} must be an object"
                
                # Enum validation
                if param.enum and value not in param.enum:
                    return f"Parameter {param.name} must be one of: {param.enum}"
        
        return None
    
    def to_openai_function(self) -> Dict[str, Any]:
        """
        Convert tool to OpenAI function calling format.
        
        Returns:
            OpenAI function definition
        """
        properties = {}
        required = []
        
        for param in self.parameters:
            prop = {
                'type': param.type,
                'description': param.description
            }
            if param.enum:
                prop['enum'] = param.enum
            if param.default is not None:
                prop['default'] = param.default
            
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            'name': self.name,
            'description': self.description,
            'parameters': {
                'type': 'object',
                'properties': properties,
                'required': required
            }
        }
    
    def to_langchain_tool(self):
        """
        Convert to LangChain tool format.
        
        Returns:
            LangChain Tool instance
        """
        from langchain.tools import StructuredTool
        from pydantic import create_model, Field
        
        # Build pydantic model for parameters
        fields = {}
        for param in self.parameters:
            python_type = {
                'string': str,
                'integer': int,
                'boolean': bool,
                'array': list,
                'object': dict
            }.get(param.type, str)
            
            if param.required:
                fields[param.name] = (python_type, Field(description=param.description))
            else:
                fields[param.name] = (Optional[python_type], Field(default=param.default, description=param.description))
        
        ArgsModel = create_model(f'{self.name}_args', **fields)
        
        def tool_func(**kwargs):
            result = self.execute(**kwargs)
            return result.to_dict()
        
        return StructuredTool(
            name=self.name,
            description=self.description,
            func=tool_func,
            args_schema=ArgsModel
        )


class ToolRegistry:
    """
    Registry for managing available tools.
    """
    
    _tools: Dict[str, Type[BaseTool]] = {}
    
    @classmethod
    def register(cls, tool_class: Type[BaseTool]):
        """Register a tool class."""
        cls._tools[tool_class.name] = tool_class
        return tool_class
    
    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseTool]]:
        """Get a tool class by name."""
        return cls._tools.get(name)
    
    @classmethod
    def get_all(cls) -> Dict[str, Type[BaseTool]]:
        """Get all registered tools."""
        return cls._tools.copy()
    
    @classmethod
    def get_by_category(cls, category: ToolCategory) -> List[Type[BaseTool]]:
        """Get tools by category."""
        return [t for t in cls._tools.values() if t.category == category]
    
    @classmethod
    def create_instance(cls, name: str, context: Dict[str, Any] = None) -> Optional[BaseTool]:
        """Create a tool instance by name."""
        tool_class = cls.get(name)
        if tool_class:
            return tool_class(context)
        return None
    
    @classmethod
    def get_openai_functions(cls, categories: List[ToolCategory] = None) -> List[Dict]:
        """Get all tools as OpenAI function definitions."""
        tools = cls._tools.values()
        if categories:
            tools = [t for t in tools if t.category in categories]
        
        return [t({}).to_openai_function() for t in tools]
    
    @classmethod
    def get_langchain_tools(cls, context: Dict[str, Any] = None, categories: List[ToolCategory] = None) -> List:
        """Get all tools as LangChain tools."""
        tools = cls._tools.values()
        if categories:
            tools = [t for t in tools if t.category in categories]
        
        return [t(context).to_langchain_tool() for t in tools]
