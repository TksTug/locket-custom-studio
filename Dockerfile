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

# Run with python or gunicorn
CMD ["python", "web_studio/server.py"]
