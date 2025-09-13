# Use a pre-built image that includes RDKit
FROM continuumio/miniconda3:latest

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
        gcc \
        g++ \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install RDKit via conda (should work better in conda base image)
RUN conda install -c conda-forge rdkit -y && \
    conda clean --all -y

# Set working directory
WORKDIR /app

# Copy requirements (without RDKit since we installed it via conda)
COPY requirements.txt .

# Install remaining Python dependencies via pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories
RUN mkdir -p temp logs

# Set environment variables
ENV PYTHONPATH=/app
ENV FLASK_ENV=production

# Expose port
EXPOSE $PORT

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:$PORT/api/health || exit 1

# Run with gunicorn
CMD gunicorn main:app \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --timeout 300 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile -
