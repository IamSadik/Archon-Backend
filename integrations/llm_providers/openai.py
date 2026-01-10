from .base import BaseLLMProvider
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from typing import List


class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM provider."""
    
    def __init__(self, api_key: str, model: str = "gpt-4"):
        super().__init__(api_key, model)
        self.llm = ChatOpenAI(model=model, openai_api_key=api_key)
        self.embeddings = OpenAIEmbeddings(openai_api_key=api_key)
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        response = self.llm.invoke(prompt)
        return response.content
    
    def generate_stream(self, prompt: str, **kwargs):
        """Generate text with streaming."""
        for chunk in self.llm.stream(prompt):
            yield chunk.content
    
    def embed(self, text: str) -> List[float]:
        """Generate embeddings for text."""
        return self.embeddings.embed_query(text)
