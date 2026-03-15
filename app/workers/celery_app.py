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


# ---------------------------------------------------------------------------
# Pre-load models at worker startup (avoids first-request latency)
# ---------------------------------------------------------------------------

from celery.signals import worker_process_init  # noqa: E402

import logging  # noqa: E402
_logger = logging.getLogger(__name__)


@worker_process_init.connect
def _preload_models(**kwargs):
    """Eagerly load ML models when a Celery worker process starts.

    This prevents the first task from bearing the full model-loading
    latency (which can cause API timeouts).
    """
    _logger.info("Worker starting — pre-loading ML models...")

    # 1) Sentence-transformer embedding model
    try:
        from app.workers.tasks import EmbeddingModelManager
        EmbeddingModelManager()
        _logger.info("Embedding model pre-loaded.")
    except Exception:
        _logger.exception("Failed to pre-load embedding model")

    # 2) BLIP captioning model
    try:
        from app.services.image_processing import _get_blip_model
        _get_blip_model()
        _logger.info("BLIP captioning model pre-loaded.")
    except Exception:
        _logger.exception("Failed to pre-load BLIP model")

    # 3) YOLO object detection model
    try:
        from app.services.image_processing import _get_yolo_model
        _get_yolo_model()
        _logger.info("YOLO model pre-loaded.")
    except Exception:
        _logger.exception("Failed to pre-load YOLO model")

    # 4) EasyOCR reader
    try:
        from app.services.image_processing import _get_ocr_reader
        _get_ocr_reader()
        _logger.info("OCR reader pre-loaded.")
    except Exception:
        _logger.exception("Failed to pre-load OCR reader")

    _logger.info("Worker model pre-loading complete.")
