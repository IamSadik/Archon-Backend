"""
Vector Store URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.vector_store.views import (
    EmbeddingViewSet,
    SemanticSearchViewSet,
    SearchLogViewSet
)

router = DefaultRouter()
router.register(r'embeddings', EmbeddingViewSet, basename='embedding')
router.register(r'search-logs', SearchLogViewSet, basename='search-log')

urlpatterns = [
    path('', include(router.urls)),
    path('search/', SemanticSearchViewSet.as_view({'post': 'search'}), name='semantic-search'),
    path('hybrid-search/', SemanticSearchViewSet.as_view({'post': 'hybrid_search'}), name='hybrid-search'),
    path('get-context/', SemanticSearchViewSet.as_view({'post': 'get_context'}), name='get-context'),
]
