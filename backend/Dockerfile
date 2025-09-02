# Use base image
FROM continuumio/anaconda3

# Pin to Python 3.11 (critical!)
RUN conda install python=3.11 -y && \
    conda install -c conda-forge rdkit -y && \
    conda clean -a -y

# Install system tool: wkhtmltopdf (needed for pdfkit)
RUN apt-get update && \
    apt-get install -y wkhtmltopdf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your code
COPY . .

# Expose port
EXPOSE 10000

# Run the app with gunicorn – use shell form to expand $PORT
CMD exec gunicorn "main:app" "--bind=0.0.0.0:${PORT:-10000}" "--workers=2"
