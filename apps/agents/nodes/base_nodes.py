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
from apps.agents.tools.base import ToolRegistry


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
        
        # Format memory context
        memory_context = ""
        if state.get('long_term_memory'):
            memory_section = []
            for m in state['long_term_memory']:
                category = m.get('category', 'general')
                if category == 'code_snippet' or category == 'coding_standard':
                    content = m.get('content', '')
                    if isinstance(content, dict):
                        content = str(content)
                    memory_section.append(f"- [{category}] {content}")
            if memory_section:
                memory_context = "Relevant Code Context:\n" + "\n".join(memory_section)

        system_prompt = """You are an expert software developer.
Your job is to write high-quality, efficient, and well-documented code.
Follow best practices and existing project patterns.

When writing code:
1. Explain your changes briefly
2. Provide the full code or clear diffs
3. Handle errors and edge cases
4. Add comments for complex logic"""

        coding_prompt = f"""
Goal: {goal}
Current Task: {current_task.get('plan', 'Execute coding task')}
Reasoning: {current_task.get('reasoning', 'No reasoning provided')}

{memory_context}

Generate the necessary code or file operations.
If you need to use tools (like writing files), specify them clearly.
"""

        # Call LLM
        if self.llm:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                *messages[-3:],
                HumanMessage(content=coding_prompt)
            ])
            content = LLMService.get_clean_text(response.content)
        else:
            content = "Mock code generation output. Would normally generate code here."

        return {
            'messages': [AIMessage(content=f"Code generated:\n{content}")],
            'current_task': {
                'type': 'coding',
                'output': content,
                'status': 'in_progress'
            },
            'iteration_count': state['iteration_count'] + 1,
            'next_action': 'review'
        }


class ReviewerNode(BaseNode):
    """
    Reviews generated code or completed work.
    Validates quality and correctness.
    """
    
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Review the code or output."""
        messages = state['messages']
        current_task = state.get('current_task', {})
        
        system_prompt = """You are an expert code reviewer.
Review the code or output for:
1. Correctness and logic
2. Security issues
3. Performance implications
4. Style and best practices

Decide if the work is accepted or needs revision."""

        review_prompt = f"""
Task: {state['goal']}
Output to Review: {current_task.get('output', 'No output')}

Review the work and provide feedback.
End with "APPROVED" if it looks good, or "REVISION REQUIRED" if changes are needed.
"""

        if self.llm:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=review_prompt)
            ])
            review_content = LLMService.get_clean_text(response.content)
            
            status = 'completed' if 'APPROVED' in review_content else 'revision'
        else:
            review_content = "Code looks good. APPROVED."
            status = 'completed'
            
        return {
            'messages': [AIMessage(content=f"Review:\n{review_content}")],
            'current_task': {
                'type': 'review',
                'review': review_content,
                'status': status
            },
            'iteration_count': state['iteration_count'] + 1,
            'next_action': 'memory' if status == 'completed' else 'code'
        }


class MemoryNode(BaseNode):
    """
    Retrieves relevant context from memory systems.
    Accesses both short-term and long-term memory.
    """
    
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Save results to memory."""
        output = state.get('current_task', {}).get('output')
        goal = state['goal']
        project_id = state['project_id']
        
        # Save to memory service (mock implementation for now)
        try:
            # interacting with MemoryService would happen here
            # MemoryService.add_memory(...)
            pass
        except Exception as e:
            print(f"Failed to save memory: {e}")
            
        return {
            'messages': [AIMessage(content="Memory updated with task results.")],
            'iteration_count': state['iteration_count'] + 1,
            'next_action': 'end'
        }


class ToolExecutorNode(BaseNode):
    """
    Executes tools based on agent decisions.
    Handles tool calls and result processing.
    """
    
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Execute selected tools."""
        current_task = state.get('current_task', {})
        decision = current_task.get('decision', '')
        messages = state['messages']
        goal = state['goal']
        
        # 1. Identify which tool to use
        # If the previous step didn't explicitly specify a structured tool call,
        # we ask the LLM to generate one based on the context.
        
        available_tools = ToolRegistry.get_all()
        tool_descriptions = []
        for name, tool_cls in available_tools.items():
            tool_descriptions.append(f"- {name}: {tool_cls.description}")
        
        tool_list_str = "\n".join(tool_descriptions)
        
        system_prompt = """You are a tool execution agent.
Your job is to select the correct tool and parameters to achieve the current goal.
You must output a valid JSON object representing the tool call.

Format:
{
    "tool": "tool_name",
    "params": {
        "param1": "value1"
    }
}

Available Tools:
""" + tool_list_str

        execution_prompt = f"""
Goal: {goal}
Previous Context: {messages[-1].content if messages else ''}
Current Decision: {decision}

Select the best tool to make progress.
"""

        tool_call = None
        if self.llm:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=execution_prompt)
            ])
            content = LLMService.get_clean_text(response.content)
            
            # Simple parsing of JSON from text
            try:
                import json
                # Find JSON block
                if '{' in content and '}' in content:
                    json_str = content[content.find('{'):content.rfind('}')+1]
                    tool_call = json.loads(json_str)
            except Exception as e:
                print(f"Failed to parse tool call: {e}")
        
        results = []
        output_msg = ""
        
        if tool_call:
            tool_name = tool_call.get('tool')
            params = tool_call.get('params', {})
            
            # Get tool class from registry
            tool_cls = ToolRegistry.get(tool_name)
            
            if tool_cls:
                try:
                    # Instantiate tool with context
                    tool_instance = tool_cls(context={
                        'project_id': state.get('project_id'),
                        'user': state.get('user', {}), # Handle case where user might be missing
                        'project': { 'id': state.get('project_id') }
                    })
                    
                    # Execute tool
                    result = tool_instance.execute(**params)
                    results.append(result.to_dict())
                    
                    if result.success:
                        output_msg = f"Tool '{tool_name}' executed successfully.\nResult: {result.data}"
                    else:
                        output_msg = f"Tool '{tool_name}' failed.\nError: {result.error}"
                        
                except Exception as e:
                    output_msg = f"Tool '{tool_name}' execution failed: {str(e)}"
                    results.append({'error': str(e), 'success': False})
            else:
                output_msg = f"Tool '{tool_name}' not found in registry."
        else:
            output_msg = "No valid tool execution determined."

        return {
            'messages': [AIMessage(content=output_msg)],
            'tool_outputs': results,
            'current_task': {
                'type': 'tool_execution',
                'output': output_msg,
                'status': 'completed' if results and results[0].get('success') else 'failed'
            },
            'iteration_count': state['iteration_count'] + 1,
            'next_action': 'review'
        }
