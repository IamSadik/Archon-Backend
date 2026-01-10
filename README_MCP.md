# MCP Server for Archon AI Agent

## Overview

This MCP (Model Context Protocol) server provides database access tools for AI agents. It allows agents to query the Supabase PostgreSQL database safely and efficiently.

## Features

- **Query Database**: Execute SELECT queries on the database
- **Table Schema**: Get schema information for any table
- **List Tables**: List all available tables
- **User Management**: Get, search, and manage users
- **Database Stats**: Get statistics about tables and data

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure your `.env` file has the correct database credentials:
```env
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=db.rfndgfifbvqhkhoyqtbc.supabase.co
DB_PORT=5432
```

## Running the MCP Server

### Standalone Mode

Run the server directly:
```bash
python mcp_server.py
```

### With Claude Desktop or Other MCP Clients

Add this configuration to your MCP client config file:

**For Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json` on Mac):
```json
{
  "mcpServers": {
    "archon-database": {
      "command": "python",
      "args": ["I:\\Archon\\backend\\mcp_server.py"],
      "env": {
        "DB_NAME": "postgres",
        "DB_USER": "postgres",
        "DB_PASSWORD": "SADIK!@#3838",
        "DB_HOST": "db.rfndgfifbvqhkhoyqtbc.supabase.co",
        "DB_PORT": "5432"
      }
    }
  }
}
```

## Available Tools

### 1. query_database
Execute SELECT queries on the database.

**Arguments:**
- `query` (string, required): The SQL SELECT query
- `params` (array, optional): Query parameters for parameterized queries

**Example:**
```json
{
  "query": "SELECT * FROM users WHERE is_active = true LIMIT 5"
}
```

### 2. get_table_schema
Get schema information for a table.

**Arguments:**
- `table_name` (string, required): Name of the table

**Example:**
```json
{
  "table_name": "users"
}
```

### 3. list_tables
List all tables in the database.

**Arguments:** None

### 4. get_users
Get users with their profiles.

**Arguments:**
- `limit` (integer, optional): Maximum number of users (default: 10)

**Example:**
```json
{
  "limit": 20
}
```

### 5. get_user_by_email
Get a specific user by email.

**Arguments:**
- `email` (string, required): User's email address

**Example:**
```json
{
  "email": "user@example.com"
}
```

### 6. search_users
Search users by email, username, or full name.

**Arguments:**
- `search_term` (string, required): Search term

**Example:**
```json
{
  "search_term": "john"
}
```

### 7. get_database_stats
Get database statistics including table sizes and row counts.

**Arguments:** None

## Security

- Only SELECT queries are allowed through `query_database` tool
- All queries use parameterized statements to prevent SQL injection
- Service key authentication with Supabase
- Connection pooling and proper error handling

## Using MCP Client in Django

You can use the MCP client directly in your Django code:

```python
from integrations.mcp_client import mcp_client, get_users, get_user_by_email

# Get users
users = get_users(limit=10)
print(users)

# Get specific user
user = get_user_by_email("test@example.com")
print(user)

# Custom query
result = mcp_client.call_tool_sync("query_database", {
    "query": "SELECT COUNT(*) FROM users WHERE is_active = true"
})
print(result)
```

## Troubleshooting

### Connection Issues
- Verify database credentials in `.env` file
- Check network connectivity to Supabase
- Ensure PostgreSQL port (5432) is accessible

### Tool Not Found
- Make sure you're using the correct tool name
- Check the available tools with `list_tools`

### Query Failures
- Verify the SQL syntax is correct
- Check that table/column names exist
- Ensure you're only using SELECT statements

## Integration with AI Agents

The MCP server is designed to work seamlessly with:
- **Claude Desktop**: Direct integration via config file
- **LangChain**: Use as a tool in agent workflows
- **Custom AI Agents**: Via the Python client library

## Future Enhancements

- [ ] Write operations (INSERT, UPDATE, DELETE) with proper permissions
- [ ] Query result caching
- [ ] Query execution history and analytics
- [ ] Advanced search and filtering
- [ ] Real-time database change notifications
- [ ] GraphQL-style query interface
