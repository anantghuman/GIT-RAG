"""Deterministic IDs and hashes shared by ingestion and retrieval."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def stable_hash(value: str, length: int = 32) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def normalize_repo_id(repo_url: str) -> str:
    cleaned = repo_url.rstrip("/").removesuffix(".git")
    name = cleaned.split("/")[-1] or "repo"
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name).strip("-").lower() or "repo"
    return f"{slug}-{stable_hash(cleaned, 10)}"


def chunk_id(
    *,
    repo_id: str,
    sha: str,
    path: str,
    symbol: str | None,
    line_start: int,
    line_end: int,
    chunk_type: str,
    hash_value: str,
    embedding_model: str,
) -> str:
    raw = "|".join(
        [
            repo_id,
            sha,
            path,
            symbol or "",
            str(line_start),
            str(line_end),
            chunk_type,
            hash_value,
            embedding_model,
        ]
    )
    return f"chk_{stable_hash(raw, 40)}"


def file_id(repo_id: str, path: str) -> str:
    return f"file_{stable_hash(repo_id + '|' + path, 32)}"


def file_version_id(repo_id: str, sha: str, path: str) -> str:
    return f"fv_{stable_hash(repo_id + '|' + sha + '|' + path, 32)}"


def symbol_id(repo_id: str, path: str, symbol_name: str, symbol_kind: str) -> str:
    return f"sym_{stable_hash(repo_id + '|' + path + '|' + symbol_kind + '|' + symbol_name, 32)}"


def embedding_cache_id(hash_value: str, model: str) -> str:
    return f"emb_{stable_hash(hash_value + '|' + model, 32)}"


def query_cache_key(
    *,
    model: str,
    repo_id: str,
    question: str,
    branch: str | None,
    sha: str | None,
    path_prefix: str | None,
    top_k: int,
    index_generation: int,
    include_answer: bool,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "repo_id": repo_id,
        "question": " ".join(question.split()).lower(),
        "branch": branch,
        "sha": sha,
        "path_prefix": path_prefix,
        "top_k": top_k,
        "index_generation": index_generation,
        "include_answer": include_answer,
    }
    return "query:" + stable_hash(json.dumps(payload, sort_keys=True), 48)
