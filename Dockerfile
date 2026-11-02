FROM python:3.11-slim

# Install system dependencies: ffmpeg for video encoding and fonts for PIL image overlays
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency specifications and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose standard HTTP port
ENV PORT=5050
EXPOSE 5050

# Run with production high-concurrency Gunicorn server for multiple users
CMD ["sh", "-c", "gunicorn --workers 3 --threads 4 --timeout 180 --bind 0.0.0.0:${PORT:-5050} web_studio.server:app"]
