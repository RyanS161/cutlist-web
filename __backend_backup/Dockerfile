# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for headless rendering with PyVista/VTK
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglu1-mesa \
    libxrender1 \
    libsm6 \
    libice6 \
    libxt6 \
    libx11-6 \
    libxext6 \
    xvfb \
    curl \
    && rm -rf /var/lib/apt/lists/*

# PyVista/VTK offscreen rendering configuration
ENV PYVISTA_OFF_SCREEN=true
ENV DISPLAY=:99

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies with uv
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy application code
COPY app/ ./app/
COPY config/ ./config/

# Create directories for generated files
RUN mkdir -p stl_files model_images

# Expose port (Cloud Run uses PORT env variable)
ENV PORT=8080
EXPOSE 8080

# Run with Xvfb for VTK rendering
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 & sleep 1 && uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
