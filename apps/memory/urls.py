from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.memory.views import (
    ShortTermMemoryViewSet,
    LongTermMemoryViewSet,
    MemoryManagementViewSet,
    MemorySnapshotViewSet
)

router = DefaultRouter()
router.register(r'short-term', ShortTermMemoryViewSet, basename='short-term-memory')
router.register(r'long-term', LongTermMemoryViewSet, basename='long-term-memory')
router.register(r'management', MemoryManagementViewSet, basename='memory-management')
router.register(r'snapshots', MemorySnapshotViewSet, basename='memory-snapshot')

urlpatterns = [
    path('', include(router.urls)),
]
