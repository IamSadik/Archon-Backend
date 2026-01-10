from .base import BaseLLMProvider
from langchain_anthropic import ChatAnthropic
from typing import List


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude LLM provider."""
    
    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229"):
        super().__init__(api_key, model)
        self.llm = ChatAnthropic(model=model, anthropic_api_key=api_key)
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        response = self.llm.invoke(prompt)
        return response.content
    
    def generate_stream(self, prompt: str, **kwargs):
        """Generate text with streaming."""
        for chunk in self.llm.stream(prompt):
            yield chunk.content
    
    def embed(self, text: str) -> List[float]:
        """Anthropic doesn't provide embeddings, use OpenAI or other provider."""
        raise NotImplementedError("Anthropic doesn't provide embeddings")
