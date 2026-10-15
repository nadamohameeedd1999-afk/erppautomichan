# ============================================================
# ERP Automation - Dockerfile for Railway
# Web-only deployment (بدون Chrome/Selenium — الاختبارات محليًا)
# ============================================================

FROM python:3.11-slim

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Working directory
WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements & install
COPY requirements.txt .

# نثبّت المتطلبات الأساسية بس (بدون selenium/webdriver-manager)
# عشان Railway مش محتاج chrome
RUN pip install --upgrade pip && \
    pip install \
        Flask==3.0.0 \
        python-dotenv==1.0.1 \
        loguru==0.7.2 \
        reportlab==5.0.1 \
        openpyxl==3.1.5 \
        slack-sdk==3.45.0 \
        requests==2.34.2 \
        gunicorn

# Copy project
COPY . .

# Create directories
RUN mkdir -p reports/results reports/screenshots reports/logs reports/allure-results \
    && mkdir -p logs

# Environment variables
ENV PORT=5000
ENV FLASK_ENV=production
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUTF8=1

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run
CMD ["python", "web/app.py"]