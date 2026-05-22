"""
Original-file storage via Mongo GridFS. Used to keep the raw PDF or image
bytes alongside the structured extraction so the UI can offer a download
or preview instead of rendering garbled OCR text.
"""
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from .db import get_db


def _bucket() -> AsyncIOMotorGridFSBucket:
    return AsyncIOMotorGridFSBucket(get_db(), bucket_name="attachments")


async def save_attachment(content: bytes, filename: str, mime: str) -> str:
    """Returns the GridFS file id (stringified ObjectId)."""
    file_id = await _bucket().upload_from_stream(
        filename, content, metadata={"content_type": mime}
    )
    return str(file_id)


async def open_attachment(file_id: str):
    """Returns (mime, filename, async_iterator_of_bytes)."""
    from bson import ObjectId
    bucket = _bucket()
    grid_out = await bucket.open_download_stream(ObjectId(file_id))
    mime = (grid_out.metadata or {}).get("content_type", "application/octet-stream")
    filename = grid_out.filename or "attachment"
    async def _iter():
        while True:
            chunk = await grid_out.readchunk()
            if not chunk:
                break
            yield chunk
    return mime, filename, _iter()
