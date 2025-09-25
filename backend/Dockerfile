# Use a base image with conda and Linux tools
FROM continuumio/minianaconda3:latest

# Install rdkit via conda-forge
RUN conda install -c conda-forge rdkit -y && \
    conda clean -a -y

# Install system tool: wkhtmltopdf (needed for pdfkit)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wkhtmltopdf \
        libxrender1 \
        libfontconfig1 \
        libx11-dev \
        libxext6 \
        libxft2 \
        libfreetype6 \
        libpng16-16 \
        zlib1g \
        fonts-liberation \
        xvfb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# 🚨 CRITICAL: UPGRADE pip, setuptools, wheel BEFORE installing anything else
# This fixes the "AttributeError: module 'pkgutil' has no attribute 'ImpImporter'" error
RUN pip install --upgrade pip setuptools wheel

# Now install your Python dependencies safely
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code
COPY . .

# Ensure wkhtmltopdf is accessible to pdfkit
RUN ln -sf /usr/bin/wkhtmltopdf /usr/local/bin/wkhtmltopdf || true

# Expose port (Render uses PORT environment variable automatically)
EXPOSE 5000

# Run the app with gunicorn
# CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:$PORT", "--timeout", "120"]
CMD exec gunicorn "main:app" "--bind=0.0.0.0:${PORT:-5000}" "--workers=2" "--timeout" "120" "--threads=4"

