import os
from pathlib import Path

from celery import Celery
from pypdf import PdfReader


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
        raise ValueError("PDF path is outside the upload directory")

    try:
        reader = PdfReader(pdf_path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return {"text": "\n\n".join(pages), "pages": len(pages)}
    finally:
        pdf_path.unlink(missing_ok=True)