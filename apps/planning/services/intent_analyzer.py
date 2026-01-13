"""
Intent Analyzer Service - Analyzes user messages to determine intent and extract entities.
This is a critical component for understanding what the user wants to do.
"""
import re
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from django.utils import timezone
from apps.agents.services.llm_service import LLMService
from apps.projects.models import Project
from langchain_core.messages import HumanMessage, SystemMessage


class IntentType(Enum):
    """Types of user intents the system can recognize."""
    # Planning intents
    CREATE_FEATURE = "create_feature"
    CREATE_SUB_FEATURE = "create_sub_feature"
    UPDATE_FEATURE = "update_feature"
    DELETE_FEATURE = "delete_feature"
    START_FEATURE = "start_feature"
    COMPLETE_FEATURE = "complete_feature"
    PAUSE_FEATURE = "pause_feature"
    RESUME_FEATURE = "resume_feature"
    SWITCH_FEATURE = "switch_feature"
    
    # Task intents
    CREATE_TASK = "create_task"
    COMPLETE_TASK = "complete_task"
    
    # Query intents
    QUERY_STATUS = "query_status"
    QUERY_PROGRESS = "query_progress"
    QUERY_FEATURE = "query_feature"
    QUERY_PLAN = "query_plan"
    LIST_FEATURES = "list_features"
    
    # Execution intents (delegate to executor)
    IMPLEMENT_CODE = "implement_code"
    GENERATE_CODE = "generate_code"
    REFACTOR_CODE = "refactor_code"
    DEBUG_CODE = "debug_code"
    TEST_CODE = "test_code"
    REVIEW_CODE = "review_code"
    
    # Memory intents
    REMEMBER = "remember"
    RECALL = "recall"
    
    # Control intents
    CONTINUE = "continue"
    STOP = "stop"
    HELP = "help"
    
    # Unknown
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """Result of intent analysis."""
    intent_type: IntentType
    confidence: float  # 0.0 to 1.0
    entities: Dict[str, Any] = field(default_factory=dict)
    context_needed: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    suggested_action: str = ""
    raw_analysis: Optional[Dict] = None


class IntentAnalyzerService:
    """
    Service for analyzing user intent from messages.
    Uses a combination of pattern matching and LLM for complex cases.
    """
    
    def __init__(self, user, project: Project):
        """
        Initialize the intent analyzer.
        
        Args:
            user: User instance
            project: Current project context
        """
        self.user = user
        self.project = project
        
        # Intent patterns for quick matching
        self._intent_patterns = {
            IntentType.CREATE_FEATURE: [
                r"create\s+(a\s+)?(new\s+)?feature",
                r"add\s+(a\s+)?(new\s+)?feature",
                r"new\s+feature",
                r"let'?s?\s+build",
                r"i\s+want\s+to\s+build",
                r"implement\s+(a\s+)?feature",
            ],
            IntentType.CREATE_SUB_FEATURE: [
                r"add\s+(a\s+)?sub-?feature",
                r"create\s+(a\s+)?sub-?feature",
                r"break\s+(it\s+)?down",
                r"split\s+(this\s+)?into",
            ],
            IntentType.START_FEATURE: [
                r"start\s+(working\s+on|feature)",
                r"begin\s+(working\s+on|feature)",
                r"work\s+on",
                r"let'?s?\s+start",
            ],
            IntentType.COMPLETE_FEATURE: [
                r"(mark\s+)?(as\s+)?complete",
                r"(mark\s+)?(as\s+)?done",
                r"finish(ed)?",
                r"completed?",
            ],
            IntentType.PAUSE_FEATURE: [
                r"pause",
                r"hold\s+on",
                r"put\s+on\s+hold",
                r"stop\s+for\s+now",
            ],
            IntentType.RESUME_FEATURE: [
                r"resume",
                r"continue\s+(with|working)",
                r"pick\s+up\s+where",
                r"get\s+back\s+to",
            ],
            IntentType.SWITCH_FEATURE: [
                r"switch\s+to",
                r"move\s+to",
                r"change\s+to",
                r"work\s+on\s+.+\s+instead",
            ],
            IntentType.QUERY_STATUS: [
                r"what'?s?\s+the\s+status",
                r"how'?s?\s+(it\s+)?going",
                r"where\s+are\s+we",
                r"current\s+status",
                r"show\s+status",
            ],
            IntentType.QUERY_PROGRESS: [
                r"(show\s+)?progress",
                r"how\s+much\s+(is\s+)?done",
                r"completion\s+percentage",
                r"what'?s?\s+left",
            ],
            IntentType.LIST_FEATURES: [
                r"list\s+(all\s+)?features",
                r"show\s+(all\s+)?features",
                r"what\s+features",
            ],
            IntentType.IMPLEMENT_CODE: [
                r"implement",
                r"code\s+(this|it|the)",
                r"write\s+(the\s+)?code",
                r"build\s+(this|it)",
            ],
            IntentType.GENERATE_CODE: [
                r"generate\s+(code|function|class)",
                r"create\s+(a\s+)?(function|class|module)",
            ],
            IntentType.REFACTOR_CODE: [
                r"refactor",
                r"improve\s+(the\s+)?code",
                r"clean\s+up",
                r"optimize",
            ],
            IntentType.DEBUG_CODE: [
                r"debug",
                r"fix\s+(the\s+)?(bug|error|issue)",
                r"troubleshoot",
                r"why\s+is\s+(it|this)\s+(not\s+working|failing|broken)",
            ],
            IntentType.TEST_CODE: [
                r"test",
                r"write\s+tests?",
                r"add\s+tests?",
                r"run\s+tests?",
            ],
            IntentType.REVIEW_CODE: [
                r"review\s+(the\s+)?code",
                r"code\s+review",
                r"check\s+(the\s+)?code",
            ],
            IntentType.CONTINUE: [
                r"^continue$",
                r"^next$",
                r"^go(\s+on)?$",
                r"^proceed$",
                r"keep\s+going",
            ],
            IntentType.HELP: [
                r"^help$",
                r"what\s+can\s+you\s+do",
                r"how\s+do\s+i",
            ],
            IntentType.REMEMBER: [
                r"remember\s+(that|this)",
                r"note\s+(that|this)",
                r"keep\s+in\s+mind",
                r"don'?t\s+forget",
            ],
            IntentType.RECALL: [
                r"what\s+did\s+(i|we)\s+decide",
                r"remind\s+me",
                r"what\s+was\s+the",
            ],
        }
        
        # Execution-related intents that should delegate to executor
        self._executor_intents = {
            IntentType.IMPLEMENT_CODE,
            IntentType.GENERATE_CODE,
            IntentType.REFACTOR_CODE,
            IntentType.DEBUG_CODE,
            IntentType.TEST_CODE,
            IntentType.REVIEW_CODE,
        }
    
    def analyze(self, message: str, context: Dict = None) -> IntentResult:
        """
        Analyze a user message to determine intent.
        
        Args:
            message: User's message
            context: Current context (active feature, history, etc.)
            
        Returns:
            IntentResult with classified intent and extracted entities
        """
        context = context or {}
        message_lower = message.lower().strip()
        
        # Step 1: Try pattern matching first (fast)
        pattern_result = self._match_patterns(message_lower)
        
        if pattern_result and pattern_result.confidence >= 0.8:
            # High confidence pattern match - extract entities
            pattern_result.entities = self._extract_entities(message, pattern_result.intent_type)
            pattern_result.suggested_action = self._get_suggested_action(pattern_result, context)
            pattern_result.context_needed = self._determine_context_needed(pattern_result, context)
            pattern_result.requires_confirmation = len(pattern_result.context_needed) > 0
            return pattern_result
        
        # Step 2: Use LLM for complex/ambiguous cases
        llm_result = self._analyze_with_llm(message, context)
        
        # Step 3: Merge results if pattern had partial match
        if pattern_result and pattern_result.confidence >= 0.5:
            # Use pattern result but enhance with LLM
            final_result = pattern_result
            if llm_result.entities:
                final_result.entities.update(llm_result.entities)
            if llm_result.confidence > final_result.confidence:
                final_result = llm_result
        else:
            final_result = llm_result
        
        # Extract entities and determine requirements
        final_result.suggested_action = self._get_suggested_action(final_result, context)
        final_result.context_needed = self._determine_context_needed(final_result, context)
        final_result.requires_confirmation = len(final_result.context_needed) > 0
        
        return final_result
    
    def _match_patterns(self, message: str) -> Optional[IntentResult]:
        """Match message against known patterns."""
        best_match = None
        best_score = 0.0
        
        for intent_type, patterns in self._intent_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    # Calculate confidence based on match quality
                    match_length = match.end() - match.start()
                    message_length = len(message)
                    coverage = match_length / message_length if message_length > 0 else 0
                    
                    # Higher score for more specific matches
                    score = 0.6 + (coverage * 0.4)
                    
                    if score > best_score:
                        best_score = score
                        best_match = IntentResult(
                            intent_type=intent_type,
                            confidence=score,
                            entities={},
                            raw_analysis={'matched_pattern': pattern}
                        )
        
        return best_match
    
    def _analyze_with_llm(self, message: str, context: Dict) -> IntentResult:
        """Use LLM for intent analysis when patterns don't match."""
        system_prompt = """You are an intent classifier for a software development assistant.
Analyze the user message and determine their intent.

Available intents:
- create_feature: User wants to create a new feature/functionality
- create_sub_feature: User wants to break down a feature into sub-features
- update_feature: User wants to modify an existing feature
- start_feature: User wants to start working on a feature
- complete_feature: User wants to mark something as complete
- pause_feature: User wants to pause current work
- resume_feature: User wants to resume previous work
- switch_feature: User wants to switch to a different feature
- query_status: User asking about current status
- query_progress: User asking about progress
- list_features: User wants to see all features
- implement_code: User wants to implement/code something
- generate_code: User wants code generated
- refactor_code: User wants to improve existing code
- debug_code: User wants to fix a bug
- test_code: User wants to write or run tests
- review_code: User wants code reviewed
- continue: User wants to continue previous action
- remember: User wants to save information
- recall: User wants to retrieve saved information
- unknown: Cannot determine intent

Return JSON with:
{
    "intent": "intent_name",
    "confidence": 0.0-1.0,
    "entities": {
        "feature_name": "extracted name if mentioned",
        "description": "extracted description if mentioned",
        "target": "what they're referring to"
    },
    "reasoning": "brief explanation"
}"""

        # Fix: Handle None values safely when extracting active_feature
        planning_context = context.get('planning', {})
        active_feature_data = planning_context.get('active_feature') or {}
        active_feature_name = active_feature_data.get('name', 'None')

        user_prompt = f"""Message: "{message}"

Context:
- Project: {self.project.name}
- Active feature: {active_feature_name}

Classify the intent and extract any entities."""

        try:
            llm = LLMService.get_user_preferred_llm(self.user)
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            # Parse JSON response
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            import json
            result = json.loads(content)
            
            # Map to IntentType
            intent_str = result.get('intent', 'unknown')
            try:
                intent_type = IntentType(intent_str)
            except ValueError:
                intent_type = IntentType.UNKNOWN
            
            return IntentResult(
                intent_type=intent_type,
                confidence=result.get('confidence', 0.5),
                entities=result.get('entities', {}),
                raw_analysis=result
            )
            
        except Exception as e:
            # Fallback to unknown intent on error
            return IntentResult(
                intent_type=IntentType.UNKNOWN,
                confidence=0.3,
                entities={},
                raw_analysis={'error': str(e)}
            )
    
    def _extract_entities(self, message: str, intent_type: IntentType) -> Dict[str, Any]:
        """Extract entities from message based on intent type."""
        entities = {}
        
        # Extract quoted strings (often feature names)
        quoted = re.findall(r'"([^"]+)"', message)
        if quoted:
            entities['quoted_strings'] = quoted
            if intent_type in [IntentType.CREATE_FEATURE, IntentType.START_FEATURE]:
                entities['feature_name'] = quoted[0]
        
        # Extract "called X" or "named X" patterns
        called_match = re.search(r'(?:called|named)\s+["\']?([^"\',.]+)["\']?', message, re.IGNORECASE)
        if called_match:
            entities['feature_name'] = called_match.group(1).strip()
        
        # Extract "for X" patterns (often targets)
        for_match = re.search(r'for\s+(?:the\s+)?([^,.]+?)(?:\s+feature)?(?:[,.]|$)', message, re.IGNORECASE)
        if for_match:
            entities['target'] = for_match.group(1).strip()
        
        # Extract file paths
        file_pattern = r'(?:file|path)?\s*["\']?([a-zA-Z0-9_/\\.-]+\.[a-zA-Z0-9]+)["\']?'
        files = re.findall(file_pattern, message)
        if files:
            entities['files'] = files
        
        return entities
    
    def _determine_context_needed(self, result: IntentResult, context: Dict) -> List[str]:
        """Determine what additional context is needed."""
        needed = []
        
        # Feature creation needs a name
        if result.intent_type == IntentType.CREATE_FEATURE:
            if 'feature_name' not in result.entities:
                needed.append('feature_name')
        
        # Starting/completing a feature needs to know which one
        if result.intent_type in [IntentType.START_FEATURE, IntentType.COMPLETE_FEATURE]:
            active = context.get('planning', {}).get('active_feature')
            if 'feature_name' not in result.entities and 'target' not in result.entities:
                if not active:
                    needed.append('target_feature')
        
        # Switching needs target feature
        if result.intent_type == IntentType.SWITCH_FEATURE:
            if 'feature_name' not in result.entities and 'target' not in result.entities:
                needed.append('target_feature')
        
        # Code operations might need specification
        if result.intent_type in self._executor_intents:
            if not result.entities.get('target') and not result.entities.get('description'):
                active = context.get('planning', {}).get('active_feature')
                if not active:
                    needed.append('description')
        
        return needed
    
    def _get_suggested_action(self, result: IntentResult, context: Dict) -> str:
        """Generate a suggested action based on intent."""
        intent = result.intent_type
        entities = result.entities
        active = context.get('planning', {}).get('active_feature', {}) or {}
        
        action_templates = {
            IntentType.CREATE_FEATURE: "Create feature: {name}",
            IntentType.CREATE_SUB_FEATURE: "Add sub-feature to: {parent}",
            IntentType.START_FEATURE: "Start working on: {name}",
            IntentType.COMPLETE_FEATURE: "Mark as complete: {name}",
            IntentType.PAUSE_FEATURE: "Pause: {name}",
            IntentType.RESUME_FEATURE: "Resume: {name}",
            IntentType.SWITCH_FEATURE: "Switch to: {name}",
            IntentType.IMPLEMENT_CODE: "Implement: {description}",
            IntentType.GENERATE_CODE: "Generate code for: {description}",
            IntentType.REFACTOR_CODE: "Refactor: {target}",
            IntentType.DEBUG_CODE: "Debug: {target}",
            IntentType.TEST_CODE: "Write tests for: {target}",
            IntentType.REVIEW_CODE: "Review: {target}",
            IntentType.QUERY_STATUS: "Show current status",
            IntentType.QUERY_PROGRESS: "Show progress report",
            IntentType.LIST_FEATURES: "List all features",
            IntentType.CONTINUE: "Continue with current task",
        }
        
        template = action_templates.get(intent, "Process request")
        
        # Fill in template
        name = entities.get('feature_name') or entities.get('target') or active.get('name', 'current')
        description = entities.get('description', entities.get('target', 'the task'))
        
        return template.format(
            name=name,
            parent=active.get('name', 'current feature'),
            description=description,
            target=entities.get('target', 'current code')
        )
    
    def map_intent_to_planning_action(self, result: IntentResult) -> Dict[str, Any]:
        """
        Map an intent result to a planning service action.
        
        Args:
            result: Intent analysis result
            
        Returns:
            Action mapping with service method and parameters
        """
        intent = result.intent_type
        entities = result.entities
        
        # Executor intents - delegate
        if intent in self._executor_intents:
            return {
                'delegate_to': 'executor',
                'intent': intent.value,
                'entities': entities
            }
        
        # Planning actions mapping
        action_map = {
            IntentType.CREATE_FEATURE: {
                'service_method': 'create_feature',
                'params': {
                    'name': entities.get('feature_name', ''),
                    'description': entities.get('description', '')
                }
            },
            IntentType.CREATE_SUB_FEATURE: {
                'service_method': 'create_feature',
                'params': {
                    'name': entities.get('feature_name', ''),
                    'description': entities.get('description', ''),
                    'parent_id': entities.get('parent_id')
                }
            },
            IntentType.START_FEATURE: {
                'service_method': 'start_feature',
                'params': {'feature_id': entities.get('feature_id')},
                'find_by_name': entities.get('feature_name') or entities.get('target')
            },
            IntentType.COMPLETE_FEATURE: {
                'service_method': 'complete_feature',
                'params': {'feature_id': entities.get('feature_id')},
                'find_by_name': entities.get('feature_name') or entities.get('target')
            },
            IntentType.PAUSE_FEATURE: {
                'service_method': 'pause_feature',
                'params': {
                    'feature_id': entities.get('feature_id'),
                    'reason': entities.get('reason', 'User requested')
                },
                'find_by_name': entities.get('feature_name') or entities.get('target')
            },
            IntentType.RESUME_FEATURE: {
                'service_method': 'resume_feature',
                'params': {'feature_id': entities.get('feature_id')},
                'find_by_name': entities.get('feature_name') or entities.get('target')
            },
            IntentType.SWITCH_FEATURE: {
                'service_method': 'switch_feature',
                'params': {
                    'from_feature_id': entities.get('from_feature_id'),
                    'to_feature_id': entities.get('to_feature_id')
                },
                'find_by_name': entities.get('feature_name') or entities.get('target')
            },
            IntentType.QUERY_STATUS: {
                'service_method': 'get_plan_summary',
                'params': {}
            },
            IntentType.QUERY_PROGRESS: {
                'service_method': 'get_plan_summary',
                'params': {}
            },
            IntentType.LIST_FEATURES: {
                'service_method': 'get_feature_tree',
                'params': {}
            },
            IntentType.CREATE_TASK: {
                'service_method': 'create_task',
                'params': {
                    'feature_id': entities.get('feature_id'),
                    'title': entities.get('title', ''),
                    'description': entities.get('description', '')
                }
            },
            IntentType.COMPLETE_TASK: {
                'service_method': 'complete_task',
                'params': {'task_id': entities.get('task_id')}
            },
        }
        
        return action_map.get(intent, {'service_method': None})
