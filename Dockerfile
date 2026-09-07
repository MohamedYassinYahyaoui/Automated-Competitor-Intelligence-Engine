FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 1. Update apt repositories first
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Let Playwright automatically install Chromium AND its required OS dependencies
RUN playwright install --with-deps chromium

# 4. Copy rest of codebase
COPY . .

CMD ["python", "main.py"]