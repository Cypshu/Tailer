# TAILER Backend API

FastAPI-based REST API for the TAILER LLM API Gateway platform.

## Quick Start

### Prerequisites
- Python 3.11+
- Virtual environment (recommended)

### Installation

1. Create and activate virtual environment:
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows PowerShell
# or
source venv/bin/activate      # Linux/Mac
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the server:
```bash
python main.py
```

The API will be available at **http://localhost:8000**

## API Documentation

### Interactive Docs
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Health Check
```bash
curl http://localhost:8000/health
```

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app setup
│   ├── config.py            # Configuration
│   ├── models.py            # Pydantic data models
│   ├── mock_data.py         # Mock data (MVP only)
│   └── api/
│       ├── admin.py         # Admin endpoints
│       ├── user.py          # User endpoints
│       └── runtime.py       # Runtime API (/v1/chat/completions)
├── main.py                  # Entry point
├── requirements.txt         # Python dependencies
└── venv/                    # Virtual environment
```

## API Endpoints

### Admin API (`/admin`)

#### Dashboard Stats
- **GET** `/admin/dashboard/stats` - Get dashboard statistics

#### User Management
- **GET** `/admin/users` - List all users
- **POST** `/admin/users` - Create a new user
- **GET** `/admin/users/{user_id}` - Get specific user

#### API Key Management
- **GET** `/admin/keys` - List all Sub-API Keys
- **POST** `/admin/keys` - Create new Sub-API Key
- **GET** `/admin/keys/{key_id}` - Get specific key
- **DELETE** `/admin/keys/{key_id}` - Revoke a key

#### Usage Tracking
- **GET** `/admin/usage` - Get usage events (with optional filtering)
  - Query params: `user_id`, `key_id`, `limit`, `offset`

### User API (`/user`)

#### Profile
- **GET** `/user/me` - Get current user profile

#### Keys
- **GET** `/user/keys` - Get user's Sub-API Keys
- **GET** `/user/keys/{key_id}` - Get specific key

#### Usage
- **GET** `/user/usage` - Get user's usage events
- **GET** `/user/stats` - Get user statistics

### Runtime API

#### Chat Completions (OpenAI-compatible)
- **POST** `/v1/chat/completions` - Send chat request
  - **Header**: `Authorization: Bearer tailer_sub_xxx`
  - **Body**: Standard OpenAI format

Example:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer tailer_sub_xxxxxxxxxxxxx1" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "max_tokens": 500
  }'
```

#### Health Check
- **GET** `/health` - Server status

## Mock Data

The MVP uses mock data in `app/mock_data.py`:

- **Users**: Team Alpha, Team Beta, Organizer
- **Sub-API Keys**: 3 demo keys with different permissions
- **Usage Events**: Sample API requests with token counts and costs
- **Projects**: Hackathon 2026

All data is held in-memory. It resets when the server restarts.

## Current User Context

For MVP development, the User API uses a hardcoded `CURRENT_USER_ID = "user_1"` (Team Alpha).

In production, this would be:
1. Extracted from JWT token in Authorization header
2. Validated against database
3. Used to scope all user-specific queries

## Configuration

Settings are loaded from `app/config.py` using the `TAILER_` prefix to avoid collisions with generic machine-wide variables:
- `TAILER_APP_NAME`: Application name (default: TAILER)
- `TAILER_DEBUG`: Debug mode (default: true)
- `TAILER_BACKEND_URL`: Backend URL (default: http://localhost:8000)
- `TAILER_FRONTEND_URL`: Frontend URL for CORS (default: http://localhost:3000)

## CORS Configuration

The API allows requests from:
- http://localhost:3000
- http://localhost:3001
- http://127.0.0.1:3000

This enables frontend integration during development.

## Features

✅ **MVP Features**
- Admin dashboard API
- User management endpoints
- Sub-API Key management
- Usage tracking API
- OpenAI-compatible chat endpoint
- Mock data storage
- CORS support
- Interactive API docs

🚀 **Future Features**
- PostgreSQL/SQLAlchemy integration
- JWT authentication
- Real provider API routing
- Rate limiting with Redis
- Database migrations (Alembic)
- Production deployment
- Full test suite
- Provider credential encryption

## Development Notes

### Reload on Changes
The server automatically reloads when files change (thanks to `watchfiles`).

### Add New Endpoints
1. Create or edit route file in `app/api/`
2. Add route function with FastAPI decorator
3. Include router in `app/main.py`

### Running Tests
Tests will be added in Phase 2. For now, use the Swagger UI to test endpoints manually.

## Connecting Frontend to Backend

The frontend dashboard (at http://localhost:3000) is already configured to call this API.

When you create users/keys in the admin dashboard, they're added to `MOCK_USERS` and `MOCK_KEYS`.

Example frontend API calls:
```typescript
// Fetch dashboard stats
const response = await fetch('http://localhost:8000/admin/dashboard/stats')
const stats = await response.json()

// Get user's keys
const response = await fetch('http://localhost:8000/user/keys')
const keys = await response.json()

// Send chat completion
const response = await fetch('http://localhost:8000/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer tailer_sub_xxxxxxxxxxxxx1',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    model: 'gpt-4o-mini',
    messages: [{role: 'user', content: 'Hello'}],
    max_tokens: 500
  })
})
```

## Environment Setup

Copy `.env.example` to `.env` and customize as needed:
```bash
cp .env.example .env
```

## Troubleshooting

### Port 8000 already in use
Change the port in `main.py`:
```python
uvicorn.run(..., port=8001)
```

### Import errors
Make sure you're in the virtual environment:
```bash
.\venv\Scripts\Activate.ps1
```

### CORS errors
Check that Frontend URL is correctly configured in `app/config.py`.

## Next Steps

1. **Database Integration**: Replace mock data with PostgreSQL
2. **Authentication**: Implement JWT token validation
3. **Provider Routing**: Connect to real OpenAI/Anthropic APIs
4. **Rate Limiting**: Implement Redis-based rate limiting
5. **Testing**: Add unit and integration tests
6. **Deployment**: Containerize with Docker, deploy to cloud

---

**API Base URL**: http://localhost:8000
**Frontend**: http://localhost:3000
**Docs**: http://localhost:8000/docs
