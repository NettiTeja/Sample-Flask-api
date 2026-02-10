FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y espeak-ng ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Start server
CMD ["gunicorn", "app:app"]
