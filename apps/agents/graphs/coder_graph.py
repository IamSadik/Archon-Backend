"""
Coder Agent Graph - A complete LangGraph workflow for code generation.
This agent can plan, reason, generate code, and review its work.
"""
from langgraph.graph import StateGraph, END
from apps.agents.graphs.base_graph import BaseAgentGraph, AgentState
from apps.agents.nodes import (
    PlannerNode,
    ReasonerNode,
    CoderNode,
    ReviewerNode,
    MemoryNode
)


class CoderAgentGraph(BaseAgentGraph):
    """
    A coding-focused agent that follows this workflow:
    1. Plan the implementation approach
    2. Reason about next steps
    3. Generate code
    4. Review the code
    5. Iterate or complete
    """
    
    def build_graph(self) -> StateGraph:
        """Build the coder agent workflow graph."""
        # Initialize nodes
        planner = PlannerNode(llm=self.llm)
        reasoner = ReasonerNode(llm=self.llm)
        coder = CoderNode(llm=self.llm)
        reviewer = ReviewerNode(llm=self.llm)
        memory = MemoryNode(llm=self.llm)
        
        # Create the graph
        workflow = StateGraph(AgentState)
        
        # Add nodes to the graph
        workflow.add_node("start", self._start_node)
        workflow.add_node("memory", memory)
        workflow.add_node("plan", planner)
        workflow.add_node("reason", reasoner)
        workflow.add_node("code", coder)
        workflow.add_node("review", reviewer)
        workflow.add_node("complete", self._complete_node)
        
        # Set entry point
        workflow.set_entry_point("start")
        
        # Define edges and routing
        workflow.add_edge("start", "memory")
        workflow.add_edge("memory", "plan")
        workflow.add_edge("plan", "reason")
        
        # Conditional routing from reasoner
        workflow.add_conditional_edges(
            "reason",
            self._route_from_reasoner,
            {
                "code": "code",
                "review": "review",
                "complete": "complete",
                "end": "complete"
            }
        )
        
        workflow.add_edge("code", "review")
        
        # Conditional routing from reviewer
        workflow.add_conditional_edges(
            "review",
            self._route_from_reviewer,
            {
                "complete": "complete",
                "code": "reason",  # Go back to reasoning if changes needed
                "continue": "reason"
            }
        )
        
        # Conditional routing to check if we should continue or end
        workflow.add_conditional_edges(
            "complete",
            self.should_continue,
            {
                "continue": "reason",
                "end": END
            }
        )
        
        return workflow
    
    def _start_node(self, state: AgentState) -> dict:
        """Initialize the agent session."""
        return {
            'messages': state['messages'],
            'iteration_count': 0
        }
    
    def _complete_node(self, state: AgentState) -> dict:
        """Finalize the agent session."""
        task_results = state.get('task_results', [])
        
        # Compile final result
        final_result = {
            'status': 'completed',
            'goal': state['goal'],
            'total_iterations': state['iteration_count'],
            'tasks_completed': len(task_results),
            'results': task_results,
            'messages': [msg.content if hasattr(msg, 'content') else str(msg) for msg in state['messages']]
        }
        
        return {
            'final_result': final_result,
            'next_action': 'end'
        }
    
    def _route_from_reasoner(self, state: AgentState) -> str:
        """Route based on reasoner's decision."""
        current_task = state.get('current_task', {})
        decision = current_task.get('decision', 'code')
        
        # Map decisions to next nodes
        decision_map = {
            'code': 'code',
            'review': 'review',
            'complete': 'complete',
            'tool': 'code',  # For now, tools go through code node
        }
        
        return decision_map.get(decision, 'code')
    
    def _route_from_reviewer(self, state: AgentState) -> str:
        """Route based on reviewer's feedback."""
        next_action = state.get('next_action', 'complete')
        
        if next_action == 'code':
            return 'code'
        elif next_action == 'complete':
            return 'complete'
        else:
            return 'continue'
