FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better caching
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy everything else
COPY . .

# Explicitly set permissions for entrypoint
RUN chmod +x /app/entrypoint.sh && \
    dos2unix /app/entrypoint.sh || true  # Convert line endings if dos2unix exists

ENTRYPOINT ["/app/entrypoint.sh"]