from pinecone import Pinecone, ServerlessSpec
from django.conf import settings


def get_pinecone_client():
    """Initialize and return Pinecone client."""
    return Pinecone(api_key=settings.PINECONE_API_KEY)


def get_pinecone_index():
    """Get or create Pinecone index."""
    pc = get_pinecone_client()
    
    if settings.PINECONE_INDEX_NAME not in pc.list_indexes().names():
        pc.create_index(
            name=settings.PINECONE_INDEX_NAME,
            dimension=1536,  # OpenAI embedding dimension
            metric='cosine',
            spec=ServerlessSpec(
                cloud='aws',
                region=settings.PINECONE_ENVIRONMENT
            )
        )
    
    return pc.Index(settings.PINECONE_INDEX_NAME)
