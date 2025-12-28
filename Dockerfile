FROM python:3.11-slim

# Install system dependencies
# ffmpeg is required for yt-dlp to merge formats
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt Flask

# Copy application code
COPY . .

# Expose port
EXPOSE 5000

# Run the web server
CMD ["python", "web/app.py"]
