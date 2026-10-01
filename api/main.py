import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from celery import Celery
from celery.result import AsyncResult
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from logging_config import configure_logging


logger = configure_logging("llmapp.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_async_engine(
        os.getenv(
            "POSTGRES_DSN",
            "postgresql+asyncpg://postgres:postgres@postgres:5432/dev",
        )
    )
    redis = Redis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True,
    )
    vector_db = httpx.AsyncClient(
        base_url=os.getenv("VECTOR_DB_URL", "http://vector_db:6333"),
        timeout=3.0,
    )
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = redis
    app.state.vector_db = vector_db
    try:
        yield
    finally:
        await vector_db.aclose()
        await redis.aclose()
        await engine.dispose()


app = FastAPI(title="LLM App", version="0.0.1", lifespan=lifespan)
celery_app = Celery(
    "llmapp_api",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "LLM App"}


@app.get("/version")
async def version() -> dict[str, str]:
    return {"version": app.version}


@app.post("/uploads/pdf", status_code=202)
async def upload_pdf(file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        logger.warning("pdf_upload_rejected", filename=file.filename)
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    upload_dir = Path(os.getenv("UPLOAD_DIR", "/uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{uuid4()}.pdf"

    try:
        with file_path.open("wb") as destination:
            first_chunk = await file.read(1024)
            if b"%PDF-" not in first_chunk:
                logger.warning("pdf_upload_invalid", filename=file.filename, path=str(file_path))
                raise HTTPException(status_code=400, detail="Uploaded file is not a PDF")
            destination.write(first_chunk)
            while chunk := await file.read(1024 * 1024):
                destination.write(chunk)
    except Exception:
        file_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    try:
        task = await asyncio.to_thread(
            celery_app.send_task,
            "tasks.extract_pdf_text",
            args=[str(file_path)],
        )
    except Exception:
        logger.exception("pdf_upload_enqueue_failed", path=str(file_path))
        file_path.unlink(missing_ok=True)
        raise

    logger.info("pdf_upload_queued", task_id=task.id, path=str(file_path), filename=file.filename)
    return {"task_id": task.id, "status": "queued"}


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str) -> dict[str, object]:
    def read_result() -> dict[str, object]:
        result = AsyncResult(task_id, app=celery_app)
        if result.state == "SUCCESS":
            logger.info("task_completed", task_id=task_id)
            return {"task_id": task_id, "status": "completed", "result": result.result}
        if result.state == "FAILURE":
            logger.warning("task_failed", task_id=task_id, error=str(result.result))
            return {"task_id": task_id, "status": "failed", "error": str(result.result)}
        logger.info("task_status_checked", task_id=task_id, state=result.state)
        return {
            "task_id": task_id,
            "status": "processing" if result.state == "STARTED" else "queued",
        }

    return await asyncio.to_thread(read_result)


@app.get("/healthz")
async def healthz(request: Request) -> JSONResponse:
    checks = {"postgres": "ok", "redis": "ok", "vectordb": "ok"}
    try:
        async with request.app.state.session_factory() as session:
            await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        checks["postgres"] = "unavailable"

    try:
        await request.app.state.redis.ping()
    except RedisError:
        checks["redis"] = "unavailable"

    try:
        response = await request.app.state.vector_db.get("/healthz")
        response.raise_for_status()
    except httpx.HTTPError:
        checks["vectordb"] = "unavailable"

    healthy = all(status == "ok" for status in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "unhealthy", **checks},
    )