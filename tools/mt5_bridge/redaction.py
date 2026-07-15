from __future__ import annotations

import hashlib


def hash_identifier(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def redact_server(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "***"
    return f"{text[:2]}***{text[-2:]}"

