# Use official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
# PYTHONUNBUFFERED: Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1
# APP_ENV: Defaults to production in Docker
ENV APP_ENV=production
# Playwright browser path (shared location)
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

# Set work directory
WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install dependencies defined in pyproject.toml
RUN pip install --no-cache-dir .

# Install Playwright browsers to shared location (before user switch)
RUN mkdir -p $PLAYWRIGHT_BROWSERS_PATH && \
    playwright install chromium && \
    chmod -R 755 $PLAYWRIGHT_BROWSERS_PATH

# Create a non-root user and switch to it (Security Best Practice)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Run the application
CMD ["python", "main.py"]
