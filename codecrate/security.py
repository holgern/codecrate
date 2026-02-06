from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

DEFAULT_SENSITIVE_PATH_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.kdbx",
    "*.crt",
    "*.cer",
    "*.der",
    "*.asc",
    "*.gpg",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_rsa*",
    "id_dsa",
    "id_dsa*",
    "id_ed25519",
    "id_ed25519*",
    "credentials.json",
    "*secrets*",
)

_SNIFF_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key",
        re.compile(r"-----BEGIN\s+[A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
    ),
    (
        "aws-access-key-id",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    (
        "aws-secret-access-key",
        re.compile(r"aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{20,}"),
    ),
    (
        "generic-api-key",
        re.compile(
            r"\b(?:api[_-]?key|x-api-key)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
            re.IGNORECASE,
        ),
    ),
)

_SNIFF_BYTES_LIMIT = 200_000


@dataclass(frozen=True)
class SkippedForSafety:
    path: Path
    reason: str


def _matches_sensitive_path(rel_path: str, filename: str) -> str | None:
    rel_lower = rel_path.lower()
    name_lower = filename.lower()
    for pattern in DEFAULT_SENSITIVE_PATH_PATTERNS:
        pat = pattern.lower()
        if fnmatch(rel_lower, pat) or fnmatch(name_lower, pat):
            return f"path:{pattern}"
    return None


def _read_prefix_text(path: Path) -> str:
    with path.open("rb") as f:
        data = f.read(_SNIFF_BYTES_LIMIT)
    return data.decode("utf-8", errors="replace")


def _matches_sensitive_content(path: Path) -> str | None:
    text = _read_prefix_text(path)
    for name, pat in _SNIFF_PATTERNS:
        if pat.search(text):
            return f"content:{name}"
    return None


def filter_sensitive_files(
    root: Path,
    files: list[Path],
    *,
    content_sniff: bool,
) -> tuple[list[Path], list[SkippedForSafety]]:
    safe_files: list[Path] = []
    skipped: list[SkippedForSafety] = []

    for path in files:
        rel = path.relative_to(root).as_posix()
        reason = _matches_sensitive_path(rel, path.name)
        if reason is None and content_sniff:
            try:
                reason = _matches_sensitive_content(path)
            except OSError:
                reason = None

        if reason is not None:
            skipped.append(SkippedForSafety(path=path, reason=reason))
        else:
            safe_files.append(path)

    return safe_files, skipped
