from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api import admin, user, runtime, auth
from app.repositories.base import UnitOfWorkFactory
from app.repositories.dependencies import get_uow_factory

app = FastAPI(
    title=settings.app_name,
    description="Secure LLM API Gateway for managed access and usage monitoring",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration - allow frontend to communicate
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(user.router)
app.include_router(runtime.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to TAILER API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    """Process liveness check; it deliberately avoids downstream I/O."""
    return {"status": "healthy"}


@app.get("/ready")
def readiness(factory: UnitOfWorkFactory = Depends(get_uow_factory)):
    """Report ready only when the configured repository can answer a query."""
    try:
        with factory() as uow:
            uow.projects.get_by_id(settings.default_project_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistence backend is unavailable",
        ) from exc
    return {"status": "ready"}
