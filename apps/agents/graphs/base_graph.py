"""
Base LangGraph implementation for Archon agents.
"""
from typing import TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
import operator


class AgentState(TypedDict):
    """
    Base state for all agent graphs.
    This is the shared state that flows through the graph nodes.
    """
    # Conversation history
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # Session context
    session_id: str
    project_id: str
    goal: str
    
    # Current task information
    current_task: dict
    task_results: list[dict]
    
    # Agent decision tracking
    next_action: str
    iteration_count: int
    max_iterations: int
    
    # Tool call tracking
    tool_calls: list[dict]
    
    # Memory context
    short_term_memory: list[dict]
    long_term_memory: list[dict]
    
    # Error handling
    errors: list[str]
    retry_count: int
    
    # Final output
    final_result: dict | None


class BaseAgentGraph:
    """
    Base class for creating LangGraph-based agents.
    Provides common functionality for all agent types.
    """
    
    def __init__(self, llm=None, checkpoint=True):
        """
        Initialize the base agent graph.
        
        Args:
            llm: Language model to use (will be injected from service)
            checkpoint: Whether to enable checkpointing for resume capability
        """
        self.llm = llm
        self.checkpoint = checkpoint
        self.checkpointer = MemorySaver() if checkpoint else None
        self.graph = None
    
    def create_initial_state(self, session_id: str, project_id: str, goal: str, **kwargs) -> AgentState:
        """Create initial state for the agent."""
        return AgentState(
            messages=[HumanMessage(content=goal)],
            session_id=session_id,
            project_id=project_id,
            goal=goal,
            current_task={},
            task_results=[],
            next_action="start",
            iteration_count=0,
            max_iterations=kwargs.get('max_iterations', 50),
            tool_calls=[],
            short_term_memory=[],
            long_term_memory=[],
            errors=[],
            retry_count=0,
            final_result=None
        )
    
    def build_graph(self) -> StateGraph:
        """
        Build the LangGraph workflow.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement build_graph()")
    
    def compile_graph(self):
        """Compile the graph for execution."""
        if self.graph is None:
            self.graph = self.build_graph()
        
        return self.graph.compile(checkpointer=self.checkpointer)
    
    def should_continue(self, state: AgentState) -> str:
        """
        Determine if the agent should continue processing.
        This is a common routing function used by most agents.
        """
        # Check if we've hit max iterations
        if state['iteration_count'] >= state['max_iterations']:
            return 'end'
        
        # Check if we have a final result
        if state.get('final_result') is not None:
            return 'end'
        
        # Check error conditions
        if len(state.get('errors', [])) > 3:
            return 'end'
        
        # Check next action
        next_action = state.get('next_action', 'continue')
        if next_action in ['end', 'complete', 'finish']:
            return 'end'
        
        return 'continue'
    
    async def arun(self, initial_state: AgentState, config: dict = None):
        """
        Run the agent asynchronously.
        
        Args:
            initial_state: Initial state for the agent
            config: Configuration for the graph execution
            
        Returns:
            Final state after execution
        """
        compiled_graph = self.compile_graph()
        
        # Default config with checkpoint support
        if config is None:
            config = {
                "configurable": {
                    "thread_id": initial_state['session_id']
                }
            }
        
        # Run the graph
        final_state = None
        async for state in compiled_graph.astream(initial_state, config):
            final_state = state
        
        return final_state
    
    def run(self, initial_state: AgentState, config: dict = None):
        """
        Run the agent synchronously.
        
        Args:
            initial_state: Initial state for the agent
            config: Configuration for the graph execution
            
        Returns:
            Final state after execution
        """
        compiled_graph = self.compile_graph()
        
        # Default config with checkpoint support
        if config is None:
            config = {
                "configurable": {
                    "thread_id": initial_state['session_id']
                }
            }
        
        # Run the graph
        final_state = None
        for state in compiled_graph.stream(initial_state, config):
            final_state = state
        
        return final_state
