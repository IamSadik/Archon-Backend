"""
WebSocket URL routing for chat functionality.
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Chat WebSocket - with optional session ID
    re_path(r'ws/chat/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<session_id>[0-9a-f-]+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/chat/project/(?P<project_id>[0-9a-f-]+)/$', consumers.ChatConsumer.as_asgi()),
    
    # Agent WebSocket - requires session ID
    re_path(r'ws/agent/(?P<session_id>[0-9a-f-]+)/$', consumers.AgentConsumer.as_asgi()),
]
