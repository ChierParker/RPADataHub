# ============================================================
# CompetitorWatch Docker Image
# ============================================================
FROM python:3.12-slim

LABEL maintainer="CompetitorWatch Team"
LABEL description="Competitor price monitoring & AI analysis system"

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    curl wget gnupg ca-certificates \
    fonts-liberation libasound2 libatk-bridge2.0-0 \
    libatk1.0-0 libcups2 libdbus-1-3 libdrm2 \
    libgbm1 libgtk-3-0 libnspr4 libnss3 \
    libu2f-udev libxcomposite1 libxdamage1 \
    libxfixes3 libxkbcommon0 libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -s /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

# Default command (override via docker-compose)
CMD ["python", "app.py"]
