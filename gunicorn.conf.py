"""Gunicorn config for the container image. Everything tunable via the env."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
# gthread keeps memory flat under the mostly-IO-bound request load here.
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))

# Logs to stdout/stderr so the platform (Compose, k8s) collects them.
accesslog = "-"
errorlog = "-"
