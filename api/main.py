import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


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