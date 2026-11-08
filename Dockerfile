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

# Expose standard HTTP ports (both 5050 and Render default 10000)
ENV PORT=5050
EXPOSE 5050 10000

# Run Gunicorn binding to both 0.0.0.0:${PORT:-5050} and 0.0.0.0:10000 so Render routes traffic regardless of port config!
# Workers set to 2 with 4 threads for optimal memory usage (< 400MB) within Render 512MB free tier limit.
CMD ["sh", "-c", "gunicorn --workers 2 --threads 4 --timeout 180 --bind 0.0.0.0:${PORT:-5050} --bind 0.0.0.0:10000 web_studio.server:app"]
