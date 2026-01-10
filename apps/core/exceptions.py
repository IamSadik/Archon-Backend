class AgentException(Exception):
    """Base exception for agent-related errors."""
    pass


class LLMException(AgentException):
    """Exception for LLM provider errors."""
    pass


class MemoryException(AgentException):
    """Exception for memory system errors."""
    pass


class VectorStoreException(AgentException):
    """Exception for vector store errors."""
    pass


class ContextException(AgentException):
    """Exception for context processing errors."""
    pass


class PlanningException(AgentException):
    """Exception for planning system errors."""
    pass
