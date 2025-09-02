# Multi-stage Docker build for SDS Generator
FROM continuumio/miniconda3:latest

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONDA_AUTO_UPDATE_CONDA=false

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Create conda environment and install RDKit
RUN conda create -n sds-env python=3.9 -y && \
    conda install -n sds-env -c conda-forge rdkit -y && \
    conda clean -a -y

# Activate conda environment for subsequent commands
SHELL ["conda", "run", "-n", "sds-env", "/bin/bash", "-c"]

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies in conda environment
RUN conda run -n sds-env pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Run the application
CMD ["conda", "run", "--no-capture-output", "-n", "sds-env", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "main:app"]
