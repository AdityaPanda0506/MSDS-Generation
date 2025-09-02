# Use a base image with conda and Linux tools
FROM continuumio/anaconda3

# Install rdkit via conda-forge
RUN conda install -c conda-forge rdkit -y && \
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

# Expose port (Render uses PORT environment variable automatically)
EXPOSE 10000

# Run the app with gunicorn
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:$PORT"]
