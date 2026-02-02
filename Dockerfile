# Use Python slim image for lightweight build + runtime
FROM python:3.11-slim

# Install system dependencies
# git: for cloning repos
# nginx: for serving the static site
RUN apt-get update && apt-get install -y \
    git \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Configure Nginx
# Remove default site
RUN rm -rf /usr/share/nginx/html/*
# Copy custom config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY generate_docs.py .
COPY config.yaml .
COPY mkdocs.yml .
COPY entrypoint.sh .

# Copy existing docs/assets if any (optional, can be ignored if generating fresh)
COPY viewer_assets ./viewer_assets
COPY docs ./docs

# Make entrypoint executable and fix Windows line endings
RUN apt-get update && apt-get install -y dos2unix && rm -rf /var/lib/apt/lists/*
RUN dos2unix entrypoint.sh && chmod +x entrypoint.sh

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV GENERATE_ON_START=true

# Expose HTTP port
EXPOSE 80

# Start via entrypoint
CMD ["./entrypoint.sh"]
