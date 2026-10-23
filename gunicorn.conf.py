# Gunicorn Production Configuration for Render Free-Tier Optimization
# Memory leak prevention & strict resource bounds

import os

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "2"))
worker_class = "gthread"

# Memory recycling: restart worker after 1000 requests to prevent memory bloat
max_requests = 1000
max_requests_jitter = 50

# Timeouts
timeout = 60
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s µs'

# Security: do not leak server banner
server_tokens = "None"
