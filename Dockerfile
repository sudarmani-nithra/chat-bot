FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8003

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application codebase
COPY . .

# Ensure runtime directories exist
RUN mkdir -p /app/audio_cache /app/static

# Expose default port from environment
EXPOSE ${PORT}

# Load environment variables from .env if present and start server dynamically
CMD ["sh", "-c", "set -a; [ -f .env ] && . ./.env; set +a; exec uvicorn app:app --host ${HOST:-0.0.0.0} --port ${PORT:-8003}"]

