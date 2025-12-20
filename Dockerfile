# Use official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
# PYTHONUNBUFFERED: Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1
# APP_ENV: Defaults to production in Docker
ENV APP_ENV=production

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install dependencies defined in pyproject.toml
RUN pip install --no-cache-dir .

# Create a non-root user and switch to it (Security Best Practice)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Run the application
CMD ["python", "main.py"]
