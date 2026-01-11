"""
Chat Service - Orchestrates chat interactions with LLM, memory, and context.
"""
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator
from django.conf import settings
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from apps.chat.models import ChatSession, ChatMessage
from apps.projects.models import Project
from apps.memory.services.memory_service import MemoryService
from apps.vector_store.services import SemanticSearchService
from apps.agents.services.llm_service import LLMService


class ChatService:
    """
    Service for managing chat interactions.
    Integrates LLM, memory, and context retrieval.
    """
    
    SYSTEM_PROMPT = """You are Archon, an intelligent AI coding assistant.
You have access to the user's project context, memory of past conversations, and coding preferences.
Be helpful, concise, and provide accurate code when asked.

When writing code:
- Follow best practices for the language
- Include error handling
- Add helpful comments
- Consider edge cases

Remember the user's preferences and past decisions when making suggestions."""
    
    def __init__(self, user, project: Project = None):
        """
        Initialize the chat service.
        
        Args:
            user: User instance
            project: Optional project for context
        """
        self.user = user
        self.project = project
        self.llm = LLMService.get_user_preferred_llm(user)
        self.memory_service = None
        self.search_service = None
    
    def _get_memory_service(self):
        """Lazy load memory service."""
        if self.memory_service is None:
            self.memory_service = MemoryService(self.user, self.project)
        return self.memory_service
    
    def _get_search_service(self):
        """Lazy load search service."""
        if self.search_service is None:
            self.search_service = SemanticSearchService()
        return self.search_service
    
    def get_or_create_session(
        self,
        session_id: str = None,
        project: Project = None,
        title: str = None
    ) -> ChatSession:
        """
        Get existing session or create a new one.
        
        Args:
            session_id: Optional existing session ID
            project: Project for the session
            title: Optional title for new session
            
        Returns:
            ChatSession instance
        """
        if session_id:
            try:
                return ChatSession.objects.get(
                    id=session_id,
                    user=self.user
                )
            except ChatSession.DoesNotExist:
                pass
        
        # Create new session
        return ChatSession.objects.create(
            user=self.user,
            project=project or self.project,
            title=title or "New Chat",
            is_active=True
        )
    
    def get_conversation_history(
        self,
        session: ChatSession,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a session.
        
        Args:
            session: ChatSession instance
            limit: Maximum messages to retrieve
            
        Returns:
            List of message dictionaries
        """
        messages = session.messages.order_by('-created_at')[:limit]
        messages = list(reversed(messages))
        
        return [
            {
                'role': msg.role,
                'content': msg.content,
                'metadata': msg.metadata
            }
            for msg in messages
        ]
    
    def _build_context(
        self,
        query: str,
        include_memory: bool = True,
        include_code_context: bool = True
    ) -> str:
        """
        Build context string for the LLM.
        
        Args:
            query: User's query
            include_memory: Whether to include memory context
            include_code_context: Whether to include code context
            
        Returns:
            Formatted context string
        """
        context_parts = []
        
        # Add memory context
        if include_memory and self.project:
            try:
                memory_service = self._get_memory_service()
                memory_context = memory_service.get_context_for_query(query)
                if memory_context:
                    context_parts.append(f"## Relevant Memory\n{memory_context}")
            except Exception:
                pass  # Memory service might not be fully set up
        
        # Add code context
        if include_code_context and self.project:
            try:
                search_service = self._get_search_service()
                code_context = search_service.get_context_for_query(
                    query=query,
                    project=self.project,
                    max_tokens=2000,
                    document_types=['code', 'documentation']
                )
                if code_context:
                    context_parts.append(f"## Relevant Code\n{code_context}")
            except Exception:
                pass  # Search service might not be fully set up
        
        return "\n\n".join(context_parts)
    
    def _build_messages(
        self,
        query: str,
        session: ChatSession,
        context: str = None
    ) -> List:
        """
        Build message list for LLM.
        
        Args:
            query: User's query
            session: ChatSession instance
            context: Optional context string
            
        Returns:
            List of LangChain messages
        """
        messages = [SystemMessage(content=self.SYSTEM_PROMPT)]
        
        # Add context if available
        if context:
            messages.append(SystemMessage(content=f"Context:\n{context}"))
        
        # Add conversation history
        history = self.get_conversation_history(session, limit=10)
        for msg in history:
            if msg['role'] == 'user':
                messages.append(HumanMessage(content=msg['content']))
            elif msg['role'] == 'assistant':
                messages.append(AIMessage(content=msg['content']))
        
        # Add current query
        messages.append(HumanMessage(content=query))
        
        return messages
    
    def send_message(
        self,
        message: str,
        session: ChatSession = None,
        include_context: bool = True,
        include_memory: bool = True
    ) -> Dict[str, Any]:
        """
        Send a message and get a response.
        
        Args:
            message: User's message
            session: ChatSession instance (will create if None)
            include_context: Whether to include code context
            include_memory: Whether to include memory context
            
        Returns:
            Response dictionary
        """
        # Get or create session
        if session is None:
            session = self.get_or_create_session()
        
        # Save user message
        user_message = ChatMessage.objects.create(
            session=session,
            role='user',
            content=message
        )
        
        # Build context
        context = None
        if include_context or include_memory:
            context = self._build_context(
                message,
                include_memory=include_memory,
                include_code_context=include_context
            )
        
        # Build messages for LLM
        messages = self._build_messages(message, session, context)
        
        # Get LLM response
        try:
            response = self.llm.invoke(messages)
            response_content = response.content
            
            # Extract token usage if available
            tokens_used = None
            if hasattr(response, 'usage_metadata'):
                tokens_used = response.usage_metadata.get('total_tokens')
            
        except Exception as e:
            response_content = f"I apologize, but I encountered an error: {str(e)}"
            tokens_used = None
        
        # Save assistant message
        assistant_message = ChatMessage.objects.create(
            session=session,
            role='assistant',
            content=response_content,
            tokens_used=tokens_used,
            metadata={
                'context_included': include_context,
                'memory_included': include_memory
            }
        )
        
        # Update session title if it's the first message
        if session.messages.count() <= 2 and session.title == "New Chat":
            # Generate title from first message
            title = message[:50] + "..." if len(message) > 50 else message
            session.title = title
            session.save(update_fields=['title'])
        
        # Store in memory for future retrieval
        if include_memory and self.project:
            try:
                memory_service = self._get_memory_service()
                memory_service.store_conversation_turn(
                    session_id=str(session.id),
                    user_message=message,
                    assistant_response=response_content
                )
            except Exception:
                pass  # Memory storage is optional
        
        return {
            'session_id': str(session.id),
            'message_id': str(assistant_message.id),
            'role': 'assistant',
            'content': response_content,
            'tokens_used': tokens_used,
            'metadata': assistant_message.metadata
        }
    
    async def send_message_stream(
        self,
        message: str,
        session: ChatSession = None,
        include_context: bool = True,
        include_memory: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Send a message and stream the response.
        
        Args:
            message: User's message
            session: ChatSession instance
            include_context: Whether to include code context
            include_memory: Whether to include memory context
            
        Yields:
            Response chunks
        """
        # Get or create session
        if session is None:
            session = self.get_or_create_session()
        
        # Save user message
        user_message = ChatMessage.objects.create(
            session=session,
            role='user',
            content=message
        )
        
        # Build context
        context = None
        if include_context or include_memory:
            context = self._build_context(
                message,
                include_memory=include_memory,
                include_code_context=include_context
            )
        
        # Build messages for LLM
        messages = self._build_messages(message, session, context)
        
        # Stream LLM response
        full_response = ""
        try:
            async for chunk in self.llm.astream(messages):
                if hasattr(chunk, 'content') and chunk.content:
                    full_response += chunk.content
                    yield {
                        'type': 'chunk',
                        'session_id': str(session.id),
                        'content': chunk.content
                    }
        except Exception as e:
            full_response = f"I apologize, but I encountered an error: {str(e)}"
            yield {
                'type': 'error',
                'session_id': str(session.id),
                'content': full_response
            }
        
        # Save complete response
        assistant_message = ChatMessage.objects.create(
            session=session,
            role='assistant',
            content=full_response,
            metadata={
                'context_included': include_context,
                'memory_included': include_memory,
                'streamed': True
            }
        )
        
        # Yield final message
        yield {
            'type': 'complete',
            'session_id': str(session.id),
            'message_id': str(assistant_message.id),
            'content': full_response
        }
    
    def regenerate_response(self, message_id: str) -> Dict[str, Any]:
        """
        Regenerate a response for a message.
        
        Args:
            message_id: ID of the assistant message to regenerate
            
        Returns:
            New response dictionary
        """
        try:
            old_message = ChatMessage.objects.get(
                id=message_id,
                session__user=self.user,
                role='assistant'
            )
        except ChatMessage.DoesNotExist:
            raise ValueError("Message not found")
        
        session = old_message.session
        
        # Find the user message before this one
        user_message = session.messages.filter(
            role='user',
            created_at__lt=old_message.created_at
        ).order_by('-created_at').first()
        
        if not user_message:
            raise ValueError("No user message found to regenerate from")
        
        # Delete the old response
        old_message.delete()
        
        # Generate new response
        return self.send_message(
            message=user_message.content,
            session=session,
            include_context=True,
            include_memory=True
        )
    
    def clear_session(self, session: ChatSession):
        """
        Clear all messages in a session.
        
        Args:
            session: ChatSession to clear
        """
        session.messages.all().delete()
    
    def end_session(self, session: ChatSession):
        """
        End a chat session.
        
        Args:
            session: ChatSession to end
        """
        session.is_active = False
        session.save(update_fields=['is_active'])
