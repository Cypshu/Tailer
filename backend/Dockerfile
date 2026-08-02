FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD curl -f http://localhost:8000/ready || exit 1

# Apply migrations, seed deterministic development fixtures, then run the API.
CMD ["sh", "-c", "alembic upgrade head && python -m app.bootstrap && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
