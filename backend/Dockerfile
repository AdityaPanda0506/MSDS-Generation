# Use Python 3.9 slim image
FROM python:3.9-slim

# Install minimal system dependencies
RUN apt-get update && \
    apt-get install -y \
        gcc \
        g++ \
        wget \
        curl \
        ca-certificates \
        libxml2-dev \
        libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install miniconda
RUN wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh && \
    bash /tmp/miniconda.sh -b -p /opt/conda && \
    rm /tmp/miniconda.sh && \
    /opt/conda/bin/conda clean -a -y

# Add conda to PATH
ENV PATH="/opt/conda/bin:$PATH"

# Install RDKit via conda (this is the critical part)
RUN conda install -c conda-forge rdkit -y && \
    conda clean -a -y

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
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

# Simple health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:$PORT/api/health || exit 1

# Run with gunicorn
CMD gunicorn main:app \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --timeout 300 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile -
