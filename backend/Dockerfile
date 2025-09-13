# Use a base image with conda and Linux tools
FROM continuumio/anaconda3

# Install rdkit via conda-forge
RUN conda install -c conda-forge rdkit -y && \
    conda clean -a -y

# Install system dependencies: wkhtmltopdf + dependencies
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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code
COPY . .

# Ensure wkhtmltopdf is executable and accessible
# (Sometimes it's installed as /usr/bin/wkhtmltopdf, sometimes /usr/local/bin/)
RUN ln -sf /usr/bin/wkhtmltopdf /usr/local/bin/wkhtmltopdf || true

# Expose port (Render uses PORT environment variable automatically)
EXPOSE 10000

# Run the app with gunicorn
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:$PORT", "--timeout", "120"]
