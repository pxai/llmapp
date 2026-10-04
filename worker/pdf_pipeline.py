import json
import math
import os
import re
from pathlib import Path
from urllib import error, request
from uuid import uuid4

from pypdf import PdfReader

from logging_config import configure_logging


logger = configure_logging("llmapp.worker.pipeline")


def extract_pdf_text(file_path: str) -> str:
    pdf_path = Path(file_path).resolve()
    if not pdf_path.exists():
        logger.error("pdf_missing", path=str(pdf_path))
        raise FileNotFoundError(f"PDF not found: {file_path}")

    reader = PdfReader(str(pdf_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    logger.info("pdf_text_extracted", path=str(pdf_path), pages=len(pages))
    return "\n\n".join(pages)


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    if not text.strip():
        logger.warning("empty_text_for_chunking")
        return []

    words = text.split()
    if len(words) <= chunk_size:
        return [text.strip()]

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end == len(words):
            break
        start += max(1, chunk_size - overlap)

    return chunks


def generate_embedding(text: str, dimensions: int = 128) -> list[float]:
    vector = [0.0] * dimensions
    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return vector

    for index, token in enumerate(tokens):
        seed = sum(ord(char) for char in token)
        vector[seed % dimensions] += 1.0 + (index % 10) * 0.01

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def ensure_qdrant_collection(collection_name: str, vector_size: int, base_url: str) -> None:
    collection_url = f"{base_url.rstrip('/')}/collections/{collection_name}"
    try:
        request.urlopen(request.Request(collection_url, method="GET"))
        return
    except error.HTTPError as exc:
        if exc.code != 404:
            raise

    payload = json.dumps({"vectors": {"size": vector_size, "distance": "Cosine"}}).encode()
    create_req = request.Request(
        collection_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    request.urlopen(create_req)


def upsert_document_to_qdrant(file_path: str, text: str) -> dict[str, object]:
    base_url = os.getenv("VECTOR_DB_URL", "http://vector_db:6333")
    collection_name = os.getenv("VECTOR_DB_COLLECTION", "documents")
    vector_size = 128

    chunks = chunk_text(text)
    if not chunks:
        return {"collection": collection_name, "chunks": 0, "status": "empty"}

    ensure_qdrant_collection(collection_name, vector_size, base_url)
    logger.info("upserting_vectors", collection=collection_name, chunks=len(chunks), source=Path(file_path).name)

    points = []
    for index, chunk in enumerate(chunks):
        vector = generate_embedding(chunk, vector_size)
        points.append(
            {
                "id": str(uuid4()),
                "vector": vector,
                "payload": {
                    "source_pdf": str(Path(file_path).name),
                    "chunk_index": index,
                    "text": chunk,
                },
            }
        )

    payload = json.dumps({"points": points}).encode()
    upsert_req = request.Request(
        f"{base_url.rstrip('/')}/collections/{collection_name}/points?wait=true",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    request.urlopen(upsert_req)
    logger.info("vectors_indexed", collection=collection_name, chunks=len(chunks))

    return {"collection": collection_name, "chunks": len(chunks), "status": "indexed"}


def process_pdf_file(file_path: str) -> dict[str, object]:
    extracted_text = extract_pdf_text(file_path)
    qdrant_result = upsert_document_to_qdrant(file_path, extracted_text)
    return {
        "text": extracted_text,
        "pages": len(PdfReader(str(Path(file_path).resolve())).pages),
        "vector_db": qdrant_result,
    }
