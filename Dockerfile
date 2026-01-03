# ============================================
# AutoGLM-GUI Docker Image
# Multi-stage build: Node (frontend) + Python (backend)
# ============================================

# Stage 1: Build Frontend
FROM node:20-slim AS frontend

WORKDIR /app

# Enable corepack for pnpm
RUN corepack enable

# Copy frontend source
COPY frontend ./frontend

# Install dependencies and build
WORKDIR /app/frontend
RUN pnpm install --frozen-lockfile && pnpm build

# ============================================
# Stage 2: Build Backend
FROM python:3.11-slim AS backend

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
# - adb: Android Debug Bridge for device control
# - curl: For healthcheck
# - ca-certificates: For HTTPS connections
RUN apt-get update && apt-get install -y --no-install-recommends \
    adb \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Python project files
COPY pyproject.toml README.md ./
COPY AutoGLM_GUI ./AutoGLM_GUI
COPY phone_agent ./phone_agent
COPY mai_agent ./mai_agent
COPY scrcpy-server-v3.3.3 ./scrcpy-server-v3.3.3

# Install Python dependencies
RUN pip install --no-cache-dir .

# Copy frontend build output from Stage 1
COPY --from=frontend /app/frontend/dist ./AutoGLM_GUI/static

# Create directories for persistent data
RUN mkdir -p /root/.config/autoglm /app/logs

# Environment variables (can be overridden at runtime)
ENV AUTOGLM_BASE_URL=""
ENV AUTOGLM_MODEL_NAME="autoglm-phone"
ENV AUTOGLM_API_KEY=""
ENV AUTOGLM_CORS_ORIGINS="*"

# Expose the default port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Default command
CMD ["autoglm-gui", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
