# TAILER - Secure LLM API Gateway

A web platform for managing, splitting, monitoring, and controlling access to Large Language Model APIs through controlled Sub-API Keys.

## Project Overview

**TAILER** is a hackathon project that solves the problem of safely sharing a single LLM provider API key among multiple participants/teams while:
- ✅ Monitoring usage per user/team
- ✅ Enforcing rate limits and budgets
- ✅ Restricting model access
- ✅ Providing transparent cost tracking
- ✅ Managing key lifecycle (create, revoke, rotate)

## Project Structure

```
Tailer/
├── frontend/               # Next.js React dashboard
│   ├── app/               # Next.js app router
│   ├── components/        # Reusable UI components
│   ├── lib/               # Mock data & utilities
│   ├── public/            # Static assets
│   ├── package.json
│   ├── tsconfig.json
│   └── README.md
│
├── backend/               # FastAPI REST API
│   ├── app/
│   │   ├── api/          # Route handlers (admin, user, runtime)
│   │   ├── main.py       # FastAPI app setup
│   │   ├── config.py     # Configuration
│   │   ├── models.py     # Data models
│   │   └── mock_data.py  # MVP mock data
│   ├── main.py           # Entry point
│   ├── requirements.txt  # Python dependencies
│   ├── venv/             # Virtual environment
│   └── README.md
│
├── IDEA.md                        # Original project idea
├── TAILER_Program_Architecture.md # Detailed architecture
├── TAILER_Project_Baseline.md     # Project requirements & roadmap
└── README.md                      # This file
```

## Quick Start

### Option 1: Docker Compose (Recommended)

**Prerequisites**: Docker and Docker Compose installed

```bash
# Copy environment template
cp .env.example .env

# Start all services (Backend + Frontend + PostgreSQL + Redis)
docker compose up -d

# Wait for services to be healthy
docker compose ps

# Access the services:
# - Frontend: http://localhost:3000
# - Backend API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
# - Database: localhost:5432
# - Redis: localhost:6379

# View logs
docker compose logs -f backend
docker compose logs -f frontend

# Stop services
docker compose down
```

### Option 2: Local Development (No Docker)

#### 1. Start the Backend (Port 8000)

```bash
cd backend

# Create and activate virtual environment (Windows)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Start the server
python main.py
```

**API Available at**: http://localhost:8000
**Docs**: http://localhost:8000/docs

#### 2. Start the Frontend (Port 3000)

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

**Dashboard Available at**: http://localhost:3000

## Technology Stack

### Frontend
- **Framework**: Next.js 16 (React 19)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Icons**: React Icons
- **UI Pattern**: App Router with dynamic routes

### Backend
- **Framework**: FastAPI 0.104
- **Server**: Uvicorn (ASGI)
- **Data Validation**: Pydantic
- **Python**: 3.11+

## Current Features (MVP)

### ✅ Admin Dashboard
- **Overview Stats**: Active keys, tokens used, cost, users, requests
- **User Management**: List, create, manage users
- **API Key Management**: Create, revoke, configure Sub-API Keys
- **Usage Dashboard**: View all API requests, token usage, costs
- **Quick Actions**: Create keys, add users, export reports

### ✅ User Dashboard
- **My Keys**: View assigned Sub-API Keys
- **Usage Stats**: Tokens used vs limit, budget vs spent
- **Request History**: View personal API calls and costs

### ✅ Backend API
- **Admin APIs**: User, key, and usage management
- **User APIs**: View personal keys and usage
- **Runtime API**: OpenAI-compatible `/v1/chat/completions` endpoint
- **Swagger/ReDoc**: Interactive API documentation

### ✅ Data
- **Mock Users**: Team Alpha, Team Beta, Organizer
- **Mock Keys**: 3 demo Sub-API Keys with different permissions
- **Mock Usage Events**: Sample API requests with tokens and costs

## Roadmap

### Phase 1: ✅ MVP Foundation
- [x] Frontend dashboard (Admin + User)
- [x] Backend API structure
- [x] Mock data layer
- [x] CORS configuration
- [x] API documentation

### Phase 2: Database & Auth (Next)
- [ ] PostgreSQL integration
- [ ] SQLAlchemy models
- [ ] Alembic migrations
- [ ] JWT authentication
- [ ] User session management

### Phase 3: Provider Integration
- [ ] OpenAI provider connection
- [ ] Anthropic provider support
- [ ] Provider credential encryption
- [ ] Real API routing

### Phase 4: Production Ready
- [ ] Redis rate limiting
- [ ] Budget enforcement
- [ ] Usage export (CSV)
- [ ] Comprehensive testing
- [ ] Error handling & logging
- [ ] Docker containerization

## API Endpoints Overview

### Admin Endpoints
```
GET    /admin/dashboard/stats       # Dashboard statistics
GET    /admin/users                 # List users
POST   /admin/users                 # Create user
GET    /admin/keys                  # List keys
POST   /admin/keys                  # Create key
DELETE /admin/keys/{key_id}         # Revoke key
GET    /admin/usage                 # Usage events
```

### User Endpoints
```
GET    /user/me                     # Current user
GET    /user/keys                   # My keys
GET    /user/usage                  # My usage
GET    /user/stats                  # My statistics
```

### Runtime Endpoint
```
POST   /v1/chat/completions        # Chat endpoint (OpenAI-compatible)
```

## Frontend Routes

### Admin Routes
- `/admin` – Admin dashboard
- `/admin/users` – User management
- `/admin/keys` – API key management

### User Routes
- `/user/dashboard` – User dashboard
- `/` – Home / Landing page

## Development Workflow

1. **Make changes** to backend code → Uvicorn auto-reloads
2. **Make changes** to frontend code → Next.js hot-reloads
3. **Test endpoints** at http://localhost:8000/docs (Swagger UI)
4. **Test UI** at http://localhost:3000

## Environment Variables

Copy `.env.example` to `.env` and customize as needed:

```bash
cp .env.example .env
```

### Key Variables
- `POSTGRES_DB` – Database name
- `POSTGRES_USER` – Database user
- `POSTGRES_PASSWORD` – Database password
- `DATABASE_URL` – Full database connection string
- `FRONTEND_URL` – Frontend URL for CORS
- `API_BASE_URL` – Backend URL used by frontend
- `OPENAI_API_KEY` – OpenAI API key (optional for MVP)

### Docker Compose
All services read from the `.env` file automatically. If using local development, frontend needs `NEXT_PUBLIC_API_URL` in `.frontend/.env.local`.

## Design Philosophy

Per **CLAUDE.md** principles:
- 🎯 **Simple over Elegant**: Working MVP before abstractions
- 📚 **Explain Decisions**: Code includes rationale for non-obvious choices
- 🔧 **Build the Gateway First**: Runtime API is prioritized
- 🌐 **Language-Independent**: HTTP/JSON APIs, not Python libraries
- 🛡️ **Security First**: API keys are hashed, provider keys are encrypted (future)
- 📊 **Usage-Centric**: Every request is tracked for monitoring

## Known Limitations (MVP)

- Mock data held in-memory (resets on server restart)
- User context hardcoded to `user_1` (Team Alpha)
- No real database
- No real LLM provider connections
- No authentication/authorization enforcement
- No rate limiting implementation
- No encryption of provider keys

These will be addressed in Phase 2+.

## Testing

### Manual Testing
Use the Swagger UI at http://localhost:8000/docs to test backend endpoints.

Use the frontend dashboard to test the full flow:
1. Go to `/admin`
2. Create users/keys
3. Go to `/user/dashboard`
4. View generated usage events

### Future Testing
- Unit tests (pytest)
- Integration tests
- API tests
- End-to-end tests

## Deployment

Currently designed for local development. For production:

1. **Backend**: Containerize with Docker, deploy to cloud (Railway, Render, AWS)
2. **Frontend**: Build → Deploy to Vercel, Netlify, or CloudFlare Pages
3. **Database**: Managed PostgreSQL (Neon, Railway, AWS RDS)
4. **Secrets**: Use environment variables and secret management

## Troubleshooting

### Backend won't start
```bash
# Check if port 8000 is in use
netstat -ano | findstr :8000

# If in use, change port in backend/main.py
```

### Frontend can't reach backend
- Ensure backend is running on http://localhost:8000
- Check CORS settings in `app/main.py`
- Check browser console for errors

### Changes not reflecting
- Backend: Restart if auto-reload fails
- Frontend: Clear `.next` folder and restart if hot-reload fails

## Team & Contribution

This is a hackathon project built by students/beginners. Goals:
- ✅ Ship a working prototype
- ✅ Learn full-stack development
- ✅ Understand API design & database concepts
- ✅ Practice collaboration

## Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Next.js Docs**: https://nextjs.org/docs
- **Tailwind CSS**: https://tailwindcss.com/
- **Pydantic**: https://docs.pydantic.dev/

## License

Hackathon Project - 2026

---

**Status**: MVP - Frontend & Backend APIs connected ✅
**Next Goal**: Add database integration
**Questions?**: Check `TAILER_Project_Baseline.md` for detailed project context
