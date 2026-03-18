from __future__ import annotations

import json
import zlib
from typing import Any


StorageState = dict[str, Any]
SessionStorageMap = dict[str, dict[str, str]]


def compress_storage_state(storage_state: StorageState) -> bytes:
    """序列化并压缩 Playwright storage state。"""
    payload = json.dumps(storage_state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return zlib.compress(payload, level=9)


def decompress_storage_state(payload: bytes | None) -> StorageState:
    """解压数据库中的 Playwright storage state。"""
    if not payload:
        return {"cookies": [], "origins": []}
    data = zlib.decompress(payload)
    parsed = json.loads(data.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("storage_state payload must be an object")
    parsed.setdefault("cookies", [])
    parsed.setdefault("origins", [])
    return parsed


def compress_session_storage(session_storage: SessionStorageMap) -> bytes:
    """序列化并压缩 sessionStorage 快照。"""
    payload = json.dumps(session_storage, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return zlib.compress(payload, level=9)


def decompress_session_storage(payload: bytes | None) -> SessionStorageMap:
    """解压数据库中的 sessionStorage。"""
    if not payload:
        return {}
    data = zlib.decompress(payload)
    parsed = json.loads(data.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("session_storage payload must be an object")
    return {
        str(origin): {str(key): str(value) for key, value in values.items()}
        for origin, values in parsed.items()
        if isinstance(values, dict)
    }
