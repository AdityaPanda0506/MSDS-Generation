# Use base image
FROM continuumio/anaconda3

# Explicitly downgrade/ensure Python 3.11
RUN conda install python=3.11 -y && \
    conda install -c conda-forge rdkit -y && \
    conda clean -a -y

# Install system tools
RUN apt-get update && \
    apt-get install -y wkhtmltopdf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD exec gunicorn "main:app" "--bind=0.0.0.0:${PORT:-10000}" "--workers=2"
