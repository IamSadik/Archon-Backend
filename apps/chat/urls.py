"""
Chat URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.chat.views import ChatSessionViewSet, ChatMessageViewSet

router = DefaultRouter()
router.register(r'sessions', ChatSessionViewSet, basename='chat-session')
router.register(r'messages', ChatMessageViewSet, basename='chat-message')

urlpatterns = [
    path('', include(router.urls)),
    path('send/', ChatSessionViewSet.as_view({'post': 'send_message'}), name='chat-send'),
]
