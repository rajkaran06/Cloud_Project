# ==============================================================================
# Dockerfile: Optimized Multi-Layer Container for Flask Visitor Counter
# Base Image: Python 3.11 Slim (Debian-based, ~130MB vs standard ~1000MB)
# ==============================================================================

FROM python:3.11-slim AS runtime

# Set environment variables:
# - PYTHONDONTWRITEBYTECODE: Prevents Python from writing .pyc files to disk
# - PYTHONUNBUFFERED: Ensures standard output/err are flushed immediately to container logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

# Set working directory inside container
WORKDIR /app

# Copy dependency definition first to take advantage of Docker build layer caching
COPY requirements.txt .

# Install dependencies without saving pip cache (reduces image size significantly)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ ./src/

# Security Best Practice: Create non-root system user and switch to it
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser && \
    chown -R appuser:appgroup /app

USER appuser

# Document exposed network port
EXPOSE 5000

# Health check to allow Docker engine to monitor container responsiveness
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/healthz')" || exit 1

# Start production WSGI server (Gunicorn) with 2 workers and 2 threads
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "30", "src.app:app"]
