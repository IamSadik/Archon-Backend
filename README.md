# Archon AI Agent Backend

A sophisticated autonomous AI agent system built with Django, LangGraph, and LangChain. Archon is designed to understand codebases, plan features, and execute code generation tasks with memory persistence and intelligent orchestration.

## 🌟 Features

- **Autonomous Agent System**: Multi-agent architecture with a Master Orchestrator coordinating planning and execution
- **LangGraph Integration**: State-machine based agent workflows using LangGraph
- **Multi-LLM Support**: Pluggable LLM providers (OpenAI, Anthropic Claude, Google Gemini)
- **Memory System**: Short-term and long-term memory with importance scoring
- **Planning & Task Management**: Hierarchical feature planning with task breakdown
- **Context Management**: Code file indexing, analysis, and semantic search
- **Vector Store**: Pinecone integration for semantic code search and embeddings
- **Real-time Updates**: WebSocket support via Django Channels for live agent updates
- **MCP Server**: Model Context Protocol server for tool integration
- **RESTful API**: Comprehensive API with Swagger/OpenAPI documentation

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Master Orchestrator                       │
│  (Central coordination for planning, execution, and memory) │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌───────────┐  ┌───────────┐  ┌───────────┐
│  Planner  │  │ Executor  │  │  Memory   │
│ Service   │  │ Service   │  │  Service  │
└───────────┘  └───────────┘  └───────────┘
        │             │             │
        ▼             ▼             ▼
┌───────────┐  ┌───────────┐  ┌───────────┐
│ Features  │  │   Agent   │  │  Short &  │
│  & Tasks  │  │ Sessions  │  │ Long-term │
└───────────┘  └───────────┘  └───────────┘
```

## 📁 Project Structure

```
backend/
├── apps/
│   ├── agents/          # AI agent sessions, executions, and tool calls
│   │   ├── services/    # Master orchestrator, autonomous executor
│   │   ├── graphs/      # LangGraph agent definitions
│   │   ├── nodes/       # Graph node implementations
│   │   └── tools/       # Agent tools (code generation, file ops, etc.)
│   ├── authentication/  # Custom user model, JWT authentication
│   ├── chat/            # WebSocket consumers for real-time chat
│   ├── context/         # Code file management and analysis
│   ├── core/            # Shared models, middleware, utilities
│   ├── memory/          # Short-term and long-term memory management
│   ├── planning/        # Feature planning, task breakdown
│   ├── projects/        # Project management
│   └── vector_store/    # Embeddings and semantic search
├── config/
│   ├── settings/        # Django settings (base, dev, prod, test)
│   ├── urls.py          # URL routing
│   └── asgi.py          # ASGI configuration for WebSockets
├── integrations/
│   ├── llm_providers/   # OpenAI, Anthropic, Gemini integrations
│   ├── cache/           # Redis and local caching
│   ├── mcp_client.py    # MCP client integration
│   ├── pinecone_config.py
│   └── supabase_client.py
├── tests/
│   ├── unit/
│   └── integration/
├── celery_app.py        # Celery configuration for async tasks
├── manage.py            # Django management script
├── requirements.txt     # Python dependencies
└── Dockerfile           # Container configuration
```

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Pinecone (for vector storage)
- API keys for LLM providers (OpenAI, Anthropic, or Google Gemini)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd backend
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/macOS
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   
   Create a `.env` file in the project root:
   ```env
   # Django
   DJANGO_SECRET_KEY=your-secret-key
   DJANGO_DEBUG=True
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
   
   # Database
   DB_NAME=your-database-name
   DB_USER=postgres
   DB_PASSWORD=your-password
   DB_HOST=localhost
   DB_PORT=5432
   
   # Redis
   REDIS_URL=redis://localhost:6379/0
   CELERY_BROKER_URL=redis://localhost:6379/0
   CELERY_RESULT_BACKEND=redis://localhost:6379/0
   
   # Supabase (optional)
   SUPABASE_URL=your-supabase-url
   SUPABASE_KEY=your-supabase-anon-key
   SUPABASE_SERVICE_KEY=your-supabase-service-key
   
   # Pinecone
   PINECONE_API_KEY=your-pinecone-api-key
   PINECONE_ENVIRONMENT=your-environment
   PINECONE_INDEX_NAME=archon-index
   
   # LLM Providers (configure at least one)
   GEMINI_API_KEY=your-gemini-api-key
   OPENAI_API_KEY=your-openai-api-key
   ANTHROPIC_API_KEY=your-anthropic-api-key
   
   # LangChain (optional, for tracing)
   LANGCHAIN_API_KEY=your-langchain-api-key
   LANGCHAIN_TRACING_V2=false
   LANGCHAIN_PROJECT=archon
   
   # JWT
   JWT_SECRET_KEY=your-jwt-secret
   JWT_ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   REFRESH_TOKEN_EXPIRE_DAYS=7
   
   # CORS
   CORS_ALLOWED_ORIGINS=http://localhost:3000
   ```

5. **Run database migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create a superuser (optional)**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run the development server**
   ```bash
   # Using Daphne (ASGI - supports WebSockets)
   daphne -b 0.0.0.0 -p 8000 config.asgi:application
   
   # Or using Django's runserver (HTTP only)
   python manage.py runserver
   ```

### Running with Celery (Background Tasks)

```bash
# Start Celery worker
celery -A celery_app worker --loglevel=info

# Start Celery beat (for scheduled tasks)
celery -A celery_app beat --loglevel=info
```

## 🔌 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register/` | Register new user |
| POST | `/api/auth/login/` | Login and get JWT tokens |
| POST | `/api/auth/refresh/` | Refresh access token |
| GET | `/api/auth/me/` | Get current user info |

### Projects
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects/` | List user's projects |
| POST | `/api/projects/` | Create new project |
| GET | `/api/projects/{id}/` | Get project details |
| PUT | `/api/projects/{id}/` | Update project |
| DELETE | `/api/projects/{id}/` | Delete project |

### Agent Sessions
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/agents/sessions/` | List agent sessions |
| POST | `/api/agents/sessions/` | Create new session |
| POST | `/api/agents/sessions/{id}/execute/` | Execute session |
| POST | `/api/agents/sessions/{id}/pause/` | Pause session |
| POST | `/api/agents/sessions/{id}/resume/` | Resume session |
| GET | `/api/agents/sessions/{id}/progress/` | Get progress |
| POST | `/api/agents/sessions/run/` | Quick-run agent |

### Planning
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/planning/plans/` | List project plans |
| GET | `/api/planning/features/` | List features |
| POST | `/api/planning/features/` | Create feature |
| GET | `/api/planning/tasks/` | List tasks |

### Memory
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memory/short-term/` | List short-term memories |
| GET | `/api/memory/long-term/` | List long-term memories |
| POST | `/api/memory/search/` | Search memories |

### Context
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/context/files/` | List indexed files |
| POST | `/api/context/files/` | Add file to context |
| POST | `/api/context/index/` | Index project files |

### Vector Store
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/vector-store/search/` | Semantic search |
| POST | `/api/vector-store/embed/` | Create embeddings |

### API Documentation
- **Swagger UI**: `/api/docs/`
- **ReDoc**: `/api/redoc/`
- **OpenAPI Schema**: `/api/schema/`

## 🔄 WebSocket Endpoints

### Chat Consumer
```
ws://localhost:8000/ws/chat/{project_id}/
```
Real-time chat with the AI agent, supporting:
- Message processing
- Status updates
- Planner updates
- Executor updates
- Input requests

### Agent Consumer
```
ws://localhost:8000/ws/agent/{session_id}/
```
Stream agent execution updates for a specific session.

## 🧠 Memory System

### Short-Term Memory
- Temporary storage for conversation context
- Auto-expires based on TTL (default: 1 hour)
- Types: conversation, code_snippet, decision, context, state

### Long-Term Memory
- Persistent knowledge storage
- Importance scoring (0.0 - 1.0)
- Categories: architectural_decision, user_preference, constraint, pattern, mistake, best_practice, lesson_learned
- Vector embeddings for semantic retrieval

## 🤖 Agent Types

- **Coder**: Code generation and modification
- **Planner**: Feature planning and task breakdown
- **Reviewer**: Code review and quality checks
- **Researcher**: Documentation and context gathering
- **Executor**: Autonomous task execution

## 🐳 Docker Deployment

```bash
# Build the image
docker build -t archon-backend .

# Run the container
docker run -p 8000:8000 --env-file .env archon-backend
```

### Docker Compose (recommended)
```yaml
version: '3.8'
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - redis
      - postgres

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: ai_agent_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  celery:
    build: .
    command: celery -A celery_app worker --loglevel=info
    env_file:
      - .env
    depends_on:
      - redis
      - postgres

volumes:
  postgres_data:
```



## 📊 Code Quality

```bash
# Format code
black .

# Sort imports
isort .

# Lint code
flake8
```



## 🔐 Security

- JWT-based authentication with access/refresh tokens
- Custom user model with email-based authentication
- CORS configuration for frontend integration
- Environment-based secrets management
- Request logging middleware



## 🙏 Acknowledgments

- [Django](https://www.djangoproject.com/)
- [LangChain](https://langchain.com/)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [Django Channels](https://channels.readthedocs.io/)
- [Pinecone](https://www.pinecone.io/)
- [Supabase](https://supabase.com/)
