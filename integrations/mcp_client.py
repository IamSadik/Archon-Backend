"""
MCP Client Integration for Django
Provides easy access to MCP server tools from Django views and services
"""

import json
import subprocess
import asyncio
from typing import Any, Dict, List, Optional
from django.conf import settings


class MCPClient:
    """Client for interacting with the MCP server."""
    
    def __init__(self, server_path: str = "mcp_server.py"):
        self.server_path = server_path
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool asynchronously.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Dictionary of arguments for the tool
        
        Returns:
            Dictionary containing the tool response
        """
        # This is a simplified implementation
        # In production, you'd maintain a persistent connection to the MCP server
        try:
            # For now, we'll use direct database access
            # In a full implementation, this would communicate with the MCP server
            from integrations.supabase_client import get_supabase_admin_client
            
            client = get_supabase_admin_client()
            
            if tool_name == "get_users":
                limit = arguments.get("limit", 10)
                response = client.table("users").select("*").limit(limit).execute()
                return {
                    "success": True,
                    "user_count": len(response.data),
                    "users": response.data
                }
            
            elif tool_name == "get_user_by_email":
                email = arguments.get("email")
                response = client.table("users").select("*").eq("email", email).execute()
                return {
                    "success": True,
                    "found": len(response.data) > 0,
                    "user": response.data[0] if response.data else None
                }
            
            else:
                return {
                    "success": False,
                    "error": f"Tool {tool_name} not implemented in simplified client"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def call_tool_sync(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper for call_tool."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.call_tool(tool_name, arguments))
        finally:
            loop.close()


# Global MCP client instance
mcp_client = MCPClient()


# Convenience functions
def query_database(query: str, params: Optional[List] = None) -> Dict[str, Any]:
    """Execute a database query via MCP."""
    return mcp_client.call_tool_sync("query_database", {
        "query": query,
        "params": params or []
    })


def get_users(limit: int = 10) -> Dict[str, Any]:
    """Get users via MCP."""
    return mcp_client.call_tool_sync("get_users", {"limit": limit})


def get_user_by_email(email: str) -> Dict[str, Any]:
    """Get a user by email via MCP."""
    return mcp_client.call_tool_sync("get_user_by_email", {"email": email})


def search_users(search_term: str) -> Dict[str, Any]:
    """Search users via MCP."""
    return mcp_client.call_tool_sync("search_users", {"search_term": search_term})


def list_tables() -> Dict[str, Any]:
    """List all database tables via MCP."""
    return mcp_client.call_tool_sync("list_tables", {})


def get_table_schema(table_name: str) -> Dict[str, Any]:
    """Get table schema via MCP."""
    return mcp_client.call_tool_sync("get_table_schema", {"table_name": table_name})
