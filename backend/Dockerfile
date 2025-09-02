# Use a smaller conda base (optional: you can keep anaconda3 if preferred)
FROM continuumio/anaconda3

# Create a non-root user (good practice)
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
WORKDIR /app

# Switch to non-root user
USER app

# Install rdkit via conda-forge
# Run as non-privileged user; ensure conda is available
SHELL ["/bin/bash", "-c"]
RUN conda install -c conda-forge rdkit -y && \
    conda clean -a -y

# System packages: update and install wkhtmltopdf (from official static binary for better compatibility)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        xz-utils \
        fontconfig \
        libxrender1 \
        libfontconfig1 \
        libx11-dev \
        libxt6 \
        libxext6 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Download and install latest wkhtmltopdf (static binary)
# Check https://github.com/wkhtmltopdf/wkhtmltopdf/releases for latest version
ENV WKHTMLTOPDF_VERSION 0.12.6-1
RUN curl -LO "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}_linux.generic-amd64.tar.xz" && \
    tar -xf "wkhtmltox_${WKHTMLTOPDF_VERSION}_linux.generic-amd64.tar.xz" && \
    cp wkhtmltox/bin/wkhtmltopdf /usr/local/bin/ && \
    chmod +x /usr/local/bin/wkhtmltopdf && \
    rm -rf "wkhtmltox_${WKHTMLTOPDF_VERSION}_linux.generic-amd64.tar.xz" wkhtmltox

# Copy Python requirements
COPY --chown=app:app requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=app:app . .

# Expose port (Render, Docker, etc.)
EXPOSE 10000

# Run gunicorn with dynamic PORT using shell form to allow variable expansion
CMD exec gunicorn "main:app" "--bind=0.0.0.0:${PORT:-10000}" "--workers=2"
