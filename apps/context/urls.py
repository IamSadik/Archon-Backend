from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.context.views import ContextFileViewSet, CodeAnalysisViewSet

router = DefaultRouter()
router.register(r'files', ContextFileViewSet, basename='context-file')
router.register(r'analysis', CodeAnalysisViewSet, basename='code-analysis')

urlpatterns = [
    path('', include(router.urls)),
]
