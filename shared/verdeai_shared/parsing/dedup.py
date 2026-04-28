"""Deduplication helpers: SHA-256, pHash, FastCDC.

Full implementation in Phase 1.
"""

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file's raw bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()
