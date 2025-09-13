# Use base image with conda
FROM continuumio/anaconda3

# Set working directory
WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install rdkit via conda-forge (critical!)
RUN conda install -c conda-forge rdkit -y && \
    conda clean -a -y

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your code
COPY . .

# Expose port
EXPOSE 10000

# Run the app
CMD exec gunicorn "main:app" "--bind=0.0.0.0:${PORT:-10000}" "--workers=2" "--timeout", "120"
