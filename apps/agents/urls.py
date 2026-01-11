from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.agents.views import AgentSessionViewSet, AgentExecutionViewSet, ToolCallViewSet

router = DefaultRouter()
router.register(r'sessions', AgentSessionViewSet, basename='agent-session')
router.register(r'executions', AgentExecutionViewSet, basename='agent-execution')
router.register(r'tool-calls', ToolCallViewSet, basename='tool-call')

urlpatterns = [
    path('', include(router.urls)),
]
