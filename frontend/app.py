import asyncio
import os

import chainlit as cl
import requests


BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://api:8080")


def upload_pdf_to_api(file_path: str, file_name: str) -> dict:
    with open(file_path, "rb") as file_handle:
        response = requests.post(
            f"{BACKEND_API_URL}/uploads/pdf",
            files={"file": (file_name, file_handle, "application/pdf")},
            timeout=30,
        )

    if response.status_code != 202:
        raise RuntimeError(f"Upload failed: {response.text}")

    return response.json()


def get_task_status(task_id: str) -> dict:
    response = requests.get(f"{BACKEND_API_URL}/tasks/{task_id}", timeout=15)
    if response.status_code != 200:
        raise RuntimeError(f"Task status failed: {response.text}")
    return response.json()


async def process_uploaded_file(file: cl.File) -> None:
    try:
        await cl.Message(content=f"Uploading {file.name}...", author="system").send()
        upload_result = await asyncio.to_thread(upload_pdf_to_api, file.path, file.name)
        task_id = upload_result["task_id"]

        await cl.Message(content=f"Queued task {task_id}. Processing PDF...", author="system").send()

        deadline = asyncio.get_running_loop().time() + 180
        while True:
            if asyncio.get_running_loop().time() > deadline:
                await cl.Message(content="PDF processing timed out.", author="system").send()
                return

            status = await asyncio.to_thread(get_task_status, task_id)
            status_name = status.get("status")

            if status_name == "completed":
                result = status.get("result", {})
                text = result.get("text", "")
                preview = text[:1200].replace("\n", "\n\n")
                await cl.Message(content=f"Processing complete.\n\n{preview or 'No text found in the PDF.'}", author="system").send()
                return

            if status_name == "failed":
                await cl.Message(content=f"Processing failed: {status.get('error', 'unknown error')}", author="system").send()
                return

            await asyncio.sleep(2)

    except Exception as exc:  # pragma: no cover - user-facing UI error path
        await cl.Message(content=f"Something went wrong: {exc}", author="system").send()


@cl.on_chat_start
async def on_chat_start() -> None:
    await cl.Message(content="Upload a PDF and I will process it for indexing.", author="system").send()
    files = await cl.AskFileMessage(
        content="Upload a PDF document",
        accept=["application/pdf"],
        max_files=1,
        timeout=600,
    ).send()

    if not files:
        await cl.Message(content="No file uploaded.", author="system").send()
        return

    await process_uploaded_file(files[0])


@cl.on_message
async def on_message(message: cl.Message) -> None:
    await cl.Message(content=f"You said: {message.content}").send()