from .base import BaseLLMProvider
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from typing import List


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider."""
    
    def __init__(self, api_key: str, model: str = "gemini-pro"):
        super().__init__(api_key, model)
        self.llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key
        )
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=api_key
        )
    
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
