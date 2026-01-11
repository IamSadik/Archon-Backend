"""
Base node implementations for agent graphs.
Each node represents a specific capability in the agent workflow.
"""
from typing import Dict, Any
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from apps.agents.graphs.base_graph import AgentState
from apps.projects.models import Project
from apps.memory.services.memory_service import MemoryService
from apps.vector_store.services.semantic_search_service import SemanticSearchService
from apps.agents.services.llm_service import LLMService


class BaseNode:
    """Base class for all agent nodes."""
    
    def __init__(self, llm=None):
        self.llm = llm
    
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Execute the node logic."""
        raise NotImplementedError("Subclasses must implement __call__")


class PlannerNode(BaseNode):
    """
    Plans the high-level approach to accomplish the goal.
    Breaks down complex tasks into manageable steps.
    """
    
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Create a plan based on the goal."""
        goal = state['goal']
        messages = state['messages']
        
        # Format memory context
        memory_context = ""
        if state.get('long_term_memory'):
            memory_section = []
            for m in state['long_term_memory']:
                category = m.get('category', 'General')
                content = m.get('content', '')
                if isinstance(content, dict):
                    content = str(content)
                memory_section.append(f"- [{category}] {content}")
            if memory_section:
                memory_context = "Relevant Memory Context:\n" + "\n".join(memory_section)

        # Build planning prompt
        system_prompt = """You are an expert software development planner.
Your job is to break down complex development goals into clear, actionable steps.
Consider the project context and create a detailed plan.

For each step, specify:
1. What needs to be done
2. Which tools or resources are needed
3. Expected outcome
4. Dependencies on other steps

Be specific and practical."""

        planning_prompt = f"""
Goal: {goal}

Project Context:
- Project ID: {state['project_id']}
- Previous results: {len(state['task_results'])} tasks completed

{memory_context}

Create a detailed execution plan with numbered steps.
"""

        # Call LLM to generate plan
        if self.llm:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=planning_prompt)
            ])
            plan_content = LLMService.get_clean_text(response.content)
        else:
            # Fallback if no LLM
            plan_content = f"Plan for: {goal}\n1. Analyze requirements\n2. Implement solution\n3. Test and validate"
        
        # Update state
        return {
            'messages': [AIMessage(content=f"Plan created:\n{plan_content}")],
            'current_task': {
                'type': 'planning',
                'plan': plan_content,
                'status': 'completed'
            },
            'iteration_count': state['iteration_count'] + 1,
            'next_action': 'reason'
        }


class ReasonerNode(BaseNode):
    """
    Analyzes the current situation and decides next steps.
    Uses chain-of-thought reasoning to make decisions.
    """
    
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Reason about the current state and determine next action."""
        messages = state['messages']
        current_task = state.get('current_task', {})
        task_results = state.get('task_results', [])
        
        # Format memory context for reasoning (focus on lessons and decisions)
        memory_context = ""
        if state.get('long_term_memory'):
            memory_section = []
            for m in state['long_term_memory']:
                category = m.get('category', 'general')
                # Prioritize relevant categories for reasoning
                if category in ['lesson_learned', 'architectural_decision', 'mistake']:
                    content = m.get('content', '')
                    if isinstance(content, dict):
                        content = str(content)
                    memory_section.append(f"- [{category}] {content}")
            if memory_section:
                memory_context = "Lessons & Decisions from Memory:\n" + "\n".join(memory_section)

        system_prompt = """You are an expert reasoning agent.
Analyze the current situation and determine the best next action.
Think step-by-step and be explicit about your reasoning.

Available actions:
- code: Generate or modify code
- tool: Use a specific tool
- review: Review and validate work
- complete: Mark the goal as complete
- continue: Continue with current approach

Consider:
1. What has been accomplished so far?
2. What is the current goal?
3. What is the best next step?
4. Are there any blockers or issues?"""

        reasoning_prompt = f"""
Current Goal: {state['goal']}
Completed Tasks: {len(task_results)}
Current Plan: {current_task.get('plan', 'No plan yet')}

{memory_context}

Analyze the situation and decide the next action.
Format your response as:
REASONING: <your step-by-step thinking>
DECISION: <next action>
DETAILS: <specific details about what to do>
"""

        # Call LLM for reasoning
        if self.llm:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                *messages[-5:],  # Last 5 messages for context
                HumanMessage(content=reasoning_prompt)
            ])
            reasoning_content = LLMService.get_clean_text(response.content)
            
            # Parse decision
            decision = 'continue'
            if 'DECISION: code' in reasoning_content.lower():
                decision = 'code'
            elif 'DECISION: tool' in reasoning_content.lower():
                decision = 'tool'
            elif 'DECISION: review' in reasoning_content.lower():
                decision = 'review'
            elif 'DECISION: complete' in reasoning_content.lower():
                decision = 'complete'
        else:
            reasoning_content = "Continuing with task execution"
            decision = 'code'
        
        return {
            'messages': [AIMessage(content=f"Reasoning:\n{reasoning_content}")],
            'current_task': {
                'type': 'reasoning',
                'reasoning': reasoning_content,
                'decision': decision
            },
            'iteration_count': state['iteration_count'] + 1,
            'next_action': decision
        }


class CoderNode(BaseNode):
    """
    Generates, modifies, or analyzes code.
    The core code generation capability.
    """
    
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Generate or modify code based on the task."""
        goal = state['goal']
        messages = state['messages']
        current_task = state.get('current_task', {})
        project_id = state.get('project_id')
        
        # 1. Retrieve relevant code context (RAG)
        context_files = ""
        try:
            if project_id:
                project = Project.objects.get(id=project_id)
                search_service = SemanticSearchService()
                results = search_service.search(
                    query=goal,
                    project=project,
                    top_k=3,
                    document_type='code_file'
                )
                
                if results:
                    context_parts = []
                    for result in results:
                        # Format: FilePath -> Content
                        content = result.get('content', '')
                        file_path = result.get('metadata', {}).get('file_path', 'unknown')
                        context_parts.append(f"File: {file_path}\n---\n{content}\n---")
                    
                    context_files = "\n".join(context_parts)
        except Exception as e:
            print(f"Error retrieving context in CoderNode: {e}")
            # Fallback to no context
        
        # 2. Get Memory Context (Patterns, Standards)
        memory_context = ""
        if state.get('long_term_memory'):
            memory_section = []
            for m in state.get('long_term_memory'):
                category = m.get('category', 'General')
                # Prioritize coding standard relevant memories
                if category in ['pattern', 'best_practice', 'user_preference']:
                    content = m.get('content', '')
                    if isinstance(content, dict):
                        content = str(content)
                    memory_section.append(f"- [{category}] {content}")
            if memory_section:
                memory_context = "Coding Standards & Patterns:\n" + "\n".join(memory_section)

        system_prompt = """You are an expert software developer.
Write clean, efficient, and well-documented code.
Follow best practices and coding standards.

When generating code:
1. Include proper error handling
2. Add clear comments
3. Follow the language's style guide
4. Consider edge cases
5. Make code maintainable

Output format:
FILE: <filename>
```<language>
<code>
```
EXPLANATION: <what the code does>
"""

        coding_prompt = f"""
Task: {goal}

Context from reasoning: {current_task.get('reasoning', 'N/A')}

{memory_context}

Existing Code Context (Reference these files/patterns):
{context_files if context_files else "No specific existing code found."}

Generate the necessary code to accomplish this task.
"""

        # Call LLM for code generation
        if self.llm:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                *messages[-3:],  # Recent context
                HumanMessage(content=coding_prompt)
            ])
            code_content = LLMService.get_clean_text(response.content)
        else:
            code_content = f"# Code for: {goal}\n# TODO: Implement this functionality"
        
        return {
            'messages': [AIMessage(content=f"Generated code:\n{code_content}")],
            'current_task': {
                'type': 'coding',
                'code': code_content,
                'status': 'completed'
            },
            'task_results': state['task_results'] + [{
                'type': 'code_generation',
                'content': code_content,
                'timestamp': 'now'
            }],
            'iteration_count': state['iteration_count'] + 1,
            'next_action': 'review'
        }


class ReviewerNode(BaseNode):
    """
    Reviews generated code or completed work.
    Validates quality and correctness.
    """
    
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Review the completed work."""
        task_results = state.get('task_results', [])
        current_task = state.get('current_task', {})
        
        if not task_results:
            return {
                'messages': [AIMessage(content="No work to review yet.")],
                'iteration_count': state['iteration_count'] + 1,
                'next_action': 'reason'
            }
        
        last_result = task_results[-1]
        
        system_prompt = """You are an expert code reviewer.
Review code for:
1. Correctness
2. Best practices
3. Security issues
4. Performance concerns
5. Code quality

Provide constructive feedback and rate the code:
- APPROVED: Ready to use
- NEEDS_CHANGES: Issues that must be fixed
- ACCEPTABLE: Minor improvements suggested but acceptable"""

        review_prompt = f"""
Review this work:
Type: {last_result.get('type')}
Content: {last_result.get('content', '')[:500]}...

Provide your review with rating and feedback.
"""

        # Call LLM for review
        if self.llm:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=review_prompt)
            ])
            review_content = LLMService.get_clean_text(response.content)
            
            # Determine if approved
            if 'APPROVED' in review_content.upper():
                next_action = 'complete'
            elif 'NEEDS_CHANGES' in review_content.upper():
                next_action = 'code'
            else:
                next_action = 'complete'
        else:
            review_content = "Review: Code looks acceptable."
            next_action = 'complete'
        
        return {
            'messages': [AIMessage(content=f"Review:\n{review_content}")],
            'current_task': {
                'type': 'review',
                'review': review_content,
                'status': 'completed'
            },
            'iteration_count': state['iteration_count'] + 1,
            'next_action': next_action
        }


class MemoryNode(BaseNode):
    """
    Retrieves relevant context from memory systems.
    Accesses both short-term and long-term memory.
    """
    
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Retrieve relevant memory context."""
        goal = state['goal']
        project_id = state['project_id']
        session_id = state['session_id']
        
        try:
            project = Project.objects.get(id=project_id)
            memory_service = MemoryService(user=project.user, project=project)
            
            # Retrieve context for the current goal
            unified_context = memory_service.get_context_for_query(goal)
            
            # Get structured memory for passing to other nodes
            short_term = memory_service.get_session_memory(session_id)
            # Get top relevant long-term memories
            long_term_results = memory_service.search_memory(goal, top_k=5)
            
            memory_log = f"Memory Context Retrieved:\n{unified_context[:500]}..."
            
        except Exception as e:
            print(f"Error in MemoryNode: {e}")
            short_term = []
            long_term_results = []
            memory_log = "Failed to retrieve memory context."
            # Fallback
        
        return {
            'messages': [AIMessage(content=memory_log)],
            'short_term_memory': short_term,
            'long_term_memory': long_term_results,
            'iteration_count': state['iteration_count'] + 1,
            'next_action': 'continue'
        }


class ToolExecutorNode(BaseNode):
    """
    Executes tools based on agent decisions.
    Handles tool calls and result processing.
    """
    
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Execute a tool based on the current task."""
        current_task = state.get('current_task', {})
        tool_name = current_task.get('tool_name', 'unknown')
        tool_params = current_task.get('tool_params', {})
        
        # TODO: Integrate with actual tool service
        # For now, return placeholder
        tool_result = {
            'tool': tool_name,
            'success': True,
            'result': f"Executed {tool_name} with params {tool_params}"
        }
        
        return {
            'messages': [AIMessage(content=f"Executed tool: {tool_name}")],
            'tool_calls': state['tool_calls'] + [tool_result],
            'task_results': state['task_results'] + [tool_result],
            'iteration_count': state['iteration_count'] + 1,
            'next_action': 'reason'
        }
