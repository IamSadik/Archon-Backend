"""
LLM Service - Manages language model initialization and configuration.
"""
from django.conf import settings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic


class LLMService:
    """
    Service for initializing and managing LLM instances.
    Supports multiple providers: Gemini, OpenAI, Anthropic.
    """
    
    @staticmethod
    def get_clean_text(content):
        """Safely extracts text from Gemini list-based content."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # Extract all text blocks and join them
            return " ".join([
                block.get("text", "") 
                for block in content 
                if isinstance(block, dict) and block.get("type") == "text"
            ])
        return str(content)
        
    @staticmethod
    def get_llm(provider: str = 'gemini', model: str = None, **kwargs):
        """
        Get an LLM instance based on provider.
        
        Args:
            provider: LLM provider ('gemini', 'openai', 'anthropic')
            model: Specific model name (optional)
            **kwargs: Additional configuration for the LLM
            
        Returns:
            Configured LLM instance
        """
        provider = provider.lower()
        
        if provider == 'gemini':
            return LLMService._get_gemini_llm(model, **kwargs)
        elif provider == 'openai':
            return LLMService._get_openai_llm(model, **kwargs)
        elif provider == 'anthropic':
            return LLMService._get_anthropic_llm(model, **kwargs)
        else:
            # Default to Gemini
            return LLMService._get_gemini_llm(model, **kwargs)
    
    @staticmethod
    def _get_gemini_llm(model: str = None, **kwargs):
        """Get Google Gemini LLM instance."""
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        # Use default model if none provided
        # Valid models: gemini-3-flash-preview, gemini-2.0-flash
        model_name = 'gemini-2.5-flash-lite'
        
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.GEMINI_API_KEY,
            convert_system_message_to_human=True,
            temperature=kwargs.get('temperature', 0.1),
            **kwargs
        )
    
    @staticmethod
    def _get_openai_llm(model: str = None, **kwargs):
        """Get OpenAI LLM instance."""
        default_model = 'gpt-4-turbo-preview'
        model_name = model or default_model
        
        return ChatOpenAI(
            model=model_name,
            openai_api_key=settings.OPENAI_API_KEY,
            temperature=kwargs.get('temperature', 0.7),
            max_tokens=kwargs.get('max_tokens', 4096),
            **kwargs
        )
    
    @staticmethod
    def _get_anthropic_llm(model: str = None, **kwargs):
        """Get Anthropic Claude LLM instance."""
        default_model = 'claude-3-opus-20240229'
        model_name = model or default_model
        
        return ChatAnthropic(
            model=model_name,
            anthropic_api_key=settings.ANTHROPIC_API_KEY,
            temperature=kwargs.get('temperature', 0.7),
            max_tokens=kwargs.get('max_tokens', 4096),
            **kwargs
        )
    
    @staticmethod
    def get_user_preferred_llm(user):
        """
        Get LLM based on user's preferences.
        
        Args:
            user: User instance with profile
            
        Returns:
            Configured LLM instance
        """
        preferred_provider = getattr(user, 'preferred_llm', 'gemini')
        return LLMService.get_llm(provider=preferred_provider)
