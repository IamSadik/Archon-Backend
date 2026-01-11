"""
Planner Agent Graph - Specialized for planning and task breakdown.
This is the LangGraph implementation of the planning brain.
"""
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage
from apps.agents.graphs.base_graph import BaseAgentGraph, AgentState
from apps.agents.nodes import PlannerNode, ReasonerNode, MemoryNode


class PlannerAgentGraph(BaseAgentGraph):
    """
    A planning-focused agent that:
    - Analyzes user intent
    - Manages the feature tree
    - Tracks progress and state
    - Coordinates with memory
    - Delegates code tasks to executor
    
    This agent does NOT write code - it only plans and coordinates.
    """
    
    def __init__(self, llm=None, checkpoint=True, planning_service=None, memory_service=None):
        """
        Initialize the planner graph.
        
        Args:
            llm: Language model
            checkpoint: Enable checkpointing
            planning_service: Optional PlanningService instance
            memory_service: Optional MemoryService instance
        """
        super().__init__(llm=llm, checkpoint=checkpoint)
        self.planning_service = planning_service
        self.memory_service = memory_service
    
    def build_graph(self) -> StateGraph:
        """Build the planner agent workflow graph."""
        # Initialize nodes
        planner = PlannerNode(llm=self.llm)
        reasoner = ReasonerNode(llm=self.llm)
        memory = MemoryNode(llm=self.llm)
        
        # Create the graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("initialize", self._initialize_node)
        workflow.add_node("retrieve_context", self._retrieve_context_node)
        workflow.add_node("analyze_intent", self._analyze_intent_node)
        workflow.add_node("plan", planner)
        workflow.add_node("update_state", self._update_state_node)
        workflow.add_node("reason", reasoner)
        workflow.add_node("memory_sync", memory)
        workflow.add_node("decide_next", self._decide_next_node)
        workflow.add_node("complete", self._complete_node)
        
        # Set entry point
        workflow.set_entry_point("initialize")
        
        # Define edges
        workflow.add_edge("initialize", "retrieve_context")
        workflow.add_edge("retrieve_context", "analyze_intent")
        workflow.add_edge("analyze_intent", "plan")
        workflow.add_edge("plan", "update_state")
        workflow.add_edge("update_state", "reason")
        workflow.add_edge("reason", "memory_sync")
        workflow.add_edge("memory_sync", "decide_next")
        
        # Conditional edge from decide_next
        workflow.add_conditional_edges(
            "decide_next",
            self._route_decision,
            {
                "continue": "retrieve_context",
                "delegate": "complete",
                "end": "complete"
            }
        )
        
        workflow.add_edge("complete", END)
        
        return workflow
    
    def _initialize_node(self, state: AgentState) -> Dict[str, Any]:
        """Initialize the planning session."""
        return {
            'messages': state['messages'],
            'iteration_count': 0,
            'current_task': {
                'phase': 'initialization',
                'planning_context': {}
            }
        }
    
    def _retrieve_context_node(self, state: AgentState) -> Dict[str, Any]:
        """Retrieve relevant context from memory and planning state."""
        context = {
            'retrieved_memories': [],
            'active_feature': None,
            'plan_summary': None
        }
        
        # If we have planning service, get context
        if self.planning_service:
            try:
                active = self.planning_service.get_active_feature()
                if active:
                    context['active_feature'] = {
                        'id': str(active.id),
                        'name': active.name,
                        'status': active.status,
                        'description': active.description
                    }
                
                context['plan_summary'] = self.planning_service.get_plan_summary()
            except Exception:
                pass
        
        # If we have memory service, search for relevant context
        if self.memory_service:
            try:
                goal = state.get('goal', '')
                context['retrieved_memories'] = self.memory_service.search_memory(goal, top_k=5)
            except Exception:
                pass
        
        current_task = state.get('current_task', {})
        current_task['planning_context'] = context
        current_task['phase'] = 'context_retrieved'
        
        return {
            'current_task': current_task,
            'short_term_memory': context.get('retrieved_memories', [])
        }
    
    def _analyze_intent_node(self, state: AgentState) -> Dict[str, Any]:
        """Analyze user intent from the goal."""
        goal = state.get('goal', '')
        current_task = state.get('current_task', {})
        
        # Simple intent classification (can be enhanced with LLM)
        intent_signals = {
            'create': ['create', 'add', 'new', 'implement', 'build'],
            'modify': ['update', 'change', 'fix', 'modify', 'edit'],
            'query': ['what', 'show', 'list', 'status', 'how'],
            'complete': ['done', 'finish', 'complete', 'mark'],
            'switch': ['switch', 'move to', 'go to', 'change to']
        }
        
        detected_intent = 'general'
        for intent, keywords in intent_signals.items():
            if any(kw in goal.lower() for kw in keywords):
                detected_intent = intent
                break
        
        current_task['detected_intent'] = detected_intent
        current_task['phase'] = 'intent_analyzed'
        
        return {
            'current_task': current_task,
            'messages': state['messages'] + [
                AIMessage(content=f"[Intent Analysis] Detected intent: {detected_intent}")
            ]
        }
    
    def _update_state_node(self, state: AgentState) -> Dict[str, Any]:
        """Update planning state based on decisions."""
        current_task = state.get('current_task', {})
        
        # Track what actions were taken
        actions_taken = current_task.get('actions_taken', [])
        
        if self.planning_service:
            try:
                # Update feature activity if there's an active feature
                active = self.planning_service.get_active_feature()
                if active:
                    active.last_activity_at = __import__('django.utils.timezone', fromlist=['timezone']).timezone.now()
                    active.save(update_fields=['last_activity_at'])
                    actions_taken.append(f"Updated activity for feature: {active.name}")
            except Exception:
                pass
        
        current_task['actions_taken'] = actions_taken
        current_task['phase'] = 'state_updated'
        
        return {
            'current_task': current_task,
            'iteration_count': state.get('iteration_count', 0) + 1
        }
    
    def _decide_next_node(self, state: AgentState) -> Dict[str, Any]:
        """Decide what to do next."""
        current_task = state.get('current_task', {})
        iteration_count = state.get('iteration_count', 0)
        max_iterations = state.get('max_iterations', 50)
        
        # Check termination conditions
        if iteration_count >= max_iterations:
            current_task['next_decision'] = 'end'
            current_task['reason'] = 'Max iterations reached'
        elif current_task.get('detected_intent') in ['create', 'modify']:
            # Code-related tasks should be delegated
            current_task['next_decision'] = 'delegate'
            current_task['reason'] = 'Code task - delegating to executor'
        elif current_task.get('plan', {}).get('complete', False):
            current_task['next_decision'] = 'end'
            current_task['reason'] = 'Planning complete'
        else:
            # Default to end for queries
            current_task['next_decision'] = 'end'
            current_task['reason'] = 'Query processed'
        
        current_task['phase'] = 'decision_made'
        
        return {'current_task': current_task}
    
    def _route_decision(self, state: AgentState) -> str:
        """Route based on the decision made."""
        current_task = state.get('current_task', {})
        return current_task.get('next_decision', 'end')
    
    def _complete_node(self, state: AgentState) -> Dict[str, Any]:
        """Finalize the planning session."""
        current_task = state.get('current_task', {})
        
        final_result = {
            'status': 'completed',
            'goal': state['goal'],
            'detected_intent': current_task.get('detected_intent', 'unknown'),
            'plan': current_task.get('plan', {}),
            'reasoning': current_task.get('reasoning', 'No reasoning provided'),
            'actions_taken': current_task.get('actions_taken', []),
            'next_decision': current_task.get('next_decision', 'end'),
            'delegation_needed': current_task.get('next_decision') == 'delegate',
            'planning_context': current_task.get('planning_context', {}),
            'total_iterations': state['iteration_count']
        }
        
        # Sync to memory if available
        if self.memory_service:
            try:
                self.memory_service.store_short_term(
                    session_id=state.get('session_id', 'unknown'),
                    key=f"planning_result_{state.get('session_id', '')}",
                    content=final_result,
                    memory_type='context',
                    ttl_seconds=3600
                )
            except Exception:
                pass
        
        return {
            'final_result': final_result,
            'next_action': 'end',
            'messages': state['messages'] + [
                AIMessage(content=f"[Planning Complete] {current_task.get('reason', 'Done')}")
            ]
        }
