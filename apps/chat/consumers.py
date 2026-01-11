import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from apps.agents.services.master_orchestrator import MasterOrchestrator
from apps.projects.models import Project

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for user chat interactions.
    Routes messages to the MasterOrchestrator.
    """
    
    async def connect(self):
        self.user = self.scope["user"]
        
        if isinstance(self.user, AnonymousUser):
            await self.close()
            return
            
        self.session_id = self.scope['url_route']['kwargs'].get('session_id')
        self.project_id = self.scope['url_route']['kwargs'].get('project_id')
        
        # Verify project access
        if self.project_id:
            try:
                self.project = await Project.objects.aget(
                    id=self.project_id, 
                    user=self.user
                )
            except Project.DoesNotExist:
                await self.close()
                return
        else:
            # Try to get default/latest project for user
            try:
                self.project = await Project.objects.filter(
                    user=self.user
                ).latest('updated_at').aget()
            except Project.DoesNotExist:
                await self.close()  # No project found
                return

        # Initialize MasterOrchestrator
        self.orchestrator = MasterOrchestrator(
            user=self.user,
            project=self.project,
            on_status_update=self.send_status_update,
            on_planner_update=self.send_planner_update,
            on_executor_update=self.send_executor_update,
            on_user_input_needed=self.send_input_request
        )
        
        # Join group
        self.room_group_name = f"chat_{self.user.id}"
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Restore session if ID provided
        if self.session_id:
            restoration = await self.orchestrator.restore_session(self.session_id)
            await self.send_json(restoration)

    async def disconnect(self, close_code):
        # Leave group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message = data.get('message')
            context = data.get('context', {})
            
            if not message:
                return

            # Process via Orchestrator
            response = await self.orchestrator.process_message(message, context)
            
            # Send back response
            await self.send_json({
                'type': 'response',
                'data': response
            })
            
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await self.send_json({
                'type': 'error',
                'message': str(e)
            })

    # Callback methods for Orchestrator
    async def send_status_update(self, data):
        await self.send_json({
            'type': 'status_update',
            'data': data
        })

    async def send_planner_update(self, data):
        await self.send_json({
            'type': 'planner_update',
            'data': data
        })

    async def send_executor_update(self, data):
        await self.send_json({
            'type': 'executor_update',
            'data': data
        })

    async def send_input_request(self, data):
        await self.send_json({
            'type': 'input_needed',
            'data': data
        })

    async def send_json(self, content):
        """Helper to send JSON data"""
        await self.send(text_data=json.dumps(content))


class AgentConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for streaming agent updates.
    Used for the "Agent View" in the frontend.
    """
    
    async def connect(self):
        self.user = self.scope["user"]
        
        if isinstance(self.user, AnonymousUser):
            await self.close()
            return
            
        self.session_id = self.scope['url_route']['kwargs'].get('session_id')
        
        if not self.session_id:
            await self.close()
            return
            
        self.room_group_name = f"agent_session_{self.session_id}"
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
    async def receive(self, text_data):
        # Mostly read-only for now, but could handle intervention commands
        pass

    # Method to receive group messages
    async def agent_update(self, event):
        await self.send(text_data=json.dumps(event['data']))