# Use explicit Python version (matches .python-version)
FROM python:3.11.9-slim AS base

# Avoid .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Workdir inside the container
WORKDIR /app

# System dependencies (needed for psycopg2, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------
# Install Python dependencies
# ----------------------------

# Copy only requirements first for better Docker caching
COPY backend/requirements.txt ./backend/requirements.txt

RUN pip install --upgrade pip && \
    pip install -r backend/requirements.txt

# ----------------------------
# Copy application code
# ----------------------------
COPY backend ./backend

# Default workdir for running commands
WORKDIR /app

# Expose a default port for future API (change if needed)
EXPOSE 8000

# ----------------------------
# Default command
# ----------------------------
# For now, just open a Python REPL.
# Once you add an API (e.g., FastAPI in backend/app/main.py),
# change this to a suitable command, e.g.:
# CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["python"]
