import os
from pathlib import Path

from celery import Celery

from logging_config import configure_logging
from pdf_pipeline import process_pdf_file


logger = configure_logging("llmapp.worker")

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
upload_dir = Path(os.getenv("UPLOAD_DIR", "/uploads")).resolve()

celery_app = Celery(
    "llmapp_worker",
    broker=redis_url,
    backend=redis_url,
)
celery_app.conf.update(task_track_started=True)


@celery_app.task(name="tasks.extract_pdf_text")
def extract_pdf_text(file_path: str) -> dict[str, object]:
    pdf_path = Path(file_path).resolve()
    if pdf_path.parent != upload_dir:
        logger.error("pdf_outside_upload_dir", path=str(pdf_path), upload_dir=str(upload_dir))
        raise ValueError("PDF path is outside the upload directory")

    logger.info("processing_pdf", path=str(pdf_path))
    try:
        result = process_pdf_file(str(pdf_path))
        logger.info("pdf_processing_complete", path=str(pdf_path), chunks=result.get("vector_db", {}).get("chunks"))
        return result
    except Exception:
        logger.exception("pdf_processing_failed", path=str(pdf_path))
        raise
    finally:
        pdf_path.unlink(missing_ok=True)
