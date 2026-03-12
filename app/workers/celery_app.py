"""Celery application configuration."""

import os
# Fix for macOS SIGABRT during multiprocessing fork with Objective-C frameworks (PyTorch, PyMuPDF)
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
# Force CPU for PyTorch — MPS (Metal) crashes in forked Celery workers on macOS
os.environ["PYTORCH_MPS_DISABLE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "personal_ai_assistant",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Auto-discover tasks in the workers package
celery_app.autodiscover_tasks(["app.workers"])
