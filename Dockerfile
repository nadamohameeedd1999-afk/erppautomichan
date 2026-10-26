# ============================================================
# ERP Automation - Dockerfile with VNC
# ============================================================

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# ===== System deps =====
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg unzip curl ca-certificates \
    xvfb x11vnc novnc websockify \
    supervisor \
    fonts-liberation \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
    libcups2 libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 \
    libnspr4 libnss3 libxcomposite1 libxdamage1 libxfixes3 \
    libxkbcommon0 libxrandr2 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# ===== Chrome =====
RUN wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/*

# ===== ChromeDriver =====
RUN CHROMEDRIVER_URL=$(curl -s https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json | python -c "import sys, json; data=json.load(sys.stdin); downloads=data['channels']['Stable']['downloads']['chromedriver']; url=[d['url'] for d in downloads if d['platform']=='linux64'][0]; print(url)") \
    && echo "ChromeDriver URL: $CHROMEDRIVER_URL" \
    && wget -q "$CHROMEDRIVER_URL" -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver \
    && rm /tmp/chromedriver.zip \
    && rm -rf /tmp/chromedriver-linux64

# ===== Python deps =====
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install gunicorn

# ===== Copy project =====
COPY . .

# ===== Data folder (mount a volume here so nothing is lost on redeploy) =====
ENV DATA_DIR=/app/data \
    DEFS_DIR=/app/data/defs
RUN mkdir -p /app/data /root/.vnc

# ===== Supervisor config =====
RUN mkdir -p /etc/supervisor/conf.d

COPY <<'EOF' /etc/supervisor/conf.d/supervisord.conf
[supervisord]
nodaemon=true
logfile=/var/log/supervisord.log
pidfile=/var/run/supervisord.pid

[program:xvfb]
command=/usr/bin/Xvfb :99 -screen 0 1920x1080x24
autorestart=true
priority=10
stdout_logfile=/var/log/xvfb.log
stderr_logfile=/var/log/xvfb.log

[program:x11vnc]
; listens on localhost only â€” the dashboard proxies it behind its own login (/live)
; password comes from the VNC_PASSWORD variable (default: erp)
command=/bin/sh -c 'x11vnc -storepasswd "${VNC_PASSWORD:-erp}" /root/.vnc/passwd >/dev/null 2>&1; exec /usr/bin/x11vnc -display :99 -forever -shared -localhost -rfbauth /root/.vnc/passwd -rfbport 5900' 
autorestart=true
priority=20
stdout_logfile=/var/log/x11vnc.log
stderr_logfile=/var/log/x11vnc.log

[program:flask]
command=python web/app.py
autorestart=true
priority=40
stdout_logfile=/var/log/flask.log
stderr_logfile=/var/log/flask.log
environment=DISPLAY=":99",PORT="5000"
EOF

# ===== ENV =====
ENV PORT=5000
ENV FLASK_ENV=production
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUTF8=1
ENV DISPLAY=:99
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver

EXPOSE 5000

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
