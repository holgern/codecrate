from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Literal

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

DEFAULT_SENSITIVE_CONTENT_PATTERNS: tuple[str, ...] = (
    r"private-key=(?i)-----BEGIN\s+[A-Z ]*PRIVATE KEY-----",
    r"aws-access-key-id=\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    r"aws-secret-access-key=aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{20,}",
    r"generic-api-key=(?i)\b(?:api[_-]?key|x-api-key)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
)

DEFAULT_SNIFF_BYTES_LIMIT = 200_000


@dataclass(frozen=True)
class SafetyFinding:
    path: Path
    reason: str
    action: Literal["skipped", "redacted"]


SkippedForSafety = SafetyFinding


@dataclass(frozen=True)
class SafetyRuleSet:
    path_patterns: tuple[str, ...]
    content_patterns: tuple[tuple[str, re.Pattern[str]], ...]
    sniff_bytes_limit: int = DEFAULT_SNIFF_BYTES_LIMIT


@dataclass(frozen=True)
class SafetyScanResult:
    safe_files: list[Path]
    skipped: list[SafetyFinding]
    redacted_files: dict[Path, str]
    findings: list[SafetyFinding]


def _parse_named_pattern(raw: str, index: int) -> tuple[str, str]:
    text = raw.strip()
    if not text:
        raise ValueError("Empty content pattern")
    if "=" in text:
        name, pattern = text.split("=", 1)
        name = name.strip() or f"custom-{index + 1}"
        pattern = pattern.strip()
    else:
        name = f"custom-{index + 1}"
        pattern = text
    if not pattern:
        raise ValueError(f"Empty regex in content pattern: {raw}")
    return name, pattern


def compile_content_patterns(
    raw_patterns: list[str],
) -> tuple[tuple[str, re.Pattern[str]], ...]:
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for idx, raw in enumerate(raw_patterns):
        name, regex = _parse_named_pattern(raw, idx)
        try:
            compiled.append((name, re.compile(regex)))
        except re.error as e:  # pragma: no cover - compile error path
            raise ValueError(f"Invalid content regex '{name}': {e}") from e
    return tuple(compiled)


def default_ruleset() -> SafetyRuleSet:
    return SafetyRuleSet(
        path_patterns=DEFAULT_SENSITIVE_PATH_PATTERNS,
        content_patterns=compile_content_patterns(
            list(DEFAULT_SENSITIVE_CONTENT_PATTERNS)
        ),
        sniff_bytes_limit=DEFAULT_SNIFF_BYTES_LIMIT,
    )


def build_ruleset(
    *,
    path_patterns: list[str] | None = None,
    content_patterns: list[str] | None = None,
    sniff_bytes_limit: int = DEFAULT_SNIFF_BYTES_LIMIT,
) -> SafetyRuleSet:
    raw_paths = (
        list(DEFAULT_SENSITIVE_PATH_PATTERNS)
        if path_patterns is None
        else [p for p in path_patterns if str(p).strip()]
    )
    raw_content = (
        list(DEFAULT_SENSITIVE_CONTENT_PATTERNS)
        if content_patterns is None
        else [p for p in content_patterns if str(p).strip()]
    )
    return SafetyRuleSet(
        path_patterns=tuple(raw_paths),
        content_patterns=compile_content_patterns(raw_content),
        sniff_bytes_limit=max(0, int(sniff_bytes_limit)),
    )


def _matches_sensitive_path(
    rel_path: str,
    filename: str,
    path_patterns: tuple[str, ...],
) -> str | None:
    rel_lower = rel_path.lower()
    name_lower = filename.lower()
    for pattern in path_patterns:
        pat = pattern.lower()
        if fnmatch(rel_lower, pat) or fnmatch(name_lower, pat):
            return f"path:{pattern}"
    return None


def _read_prefix_text(path: Path, *, limit: int) -> str:
    with path.open("rb") as f:
        data = f.read(limit)
    return data.decode("utf-8", errors="replace")


def _matches_sensitive_content(
    path: Path,
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
    *,
    sniff_bytes_limit: int,
) -> str | None:
    text = _read_prefix_text(path, limit=sniff_bytes_limit)
    for name, pat in patterns:
        if pat.search(text):
            return f"content:{name}"
    return None


def _mask_text_preserving_structure(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch in {"\n", "\r", "\t", " "}:
            out.append(ch)
        else:
            out.append("x")
    return "".join(out)


def _mask_content_matches(
    text: str,
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
) -> str:
    chars = list(text)
    for _name, pat in patterns:
        for m in pat.finditer(text):
            start, end = m.span()
            for i in range(start, end):
                ch = chars[i]
                if ch not in {"\n", "\r", "\t", " "}:
                    chars[i] = "x"
    return "".join(chars)


def apply_safety_filters(
    root: Path,
    files: list[Path],
    *,
    ruleset: SafetyRuleSet,
    content_sniff: bool,
    redaction: bool,
) -> SafetyScanResult:
    safe_files: list[Path] = []
    skipped: list[SafetyFinding] = []
    redacted_files: dict[Path, str] = {}
    findings: list[SafetyFinding] = []

    for path in files:
        rel = path.relative_to(root).as_posix()
        reason = _matches_sensitive_path(rel, path.name, ruleset.path_patterns)
        if reason is None and content_sniff and ruleset.content_patterns:
            try:
                reason = _matches_sensitive_content(
                    path,
                    ruleset.content_patterns,
                    sniff_bytes_limit=ruleset.sniff_bytes_limit,
                )
            except OSError:
                reason = None

        if reason is None:
            safe_files.append(path)
            continue

        if redaction:
            try:
                original = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                skipped_item = SafetyFinding(path=path, reason=reason, action="skipped")
                skipped.append(skipped_item)
                findings.append(skipped_item)
                continue

            if reason.startswith("path:"):
                redacted_text = _mask_text_preserving_structure(original)
            else:
                redacted_text = _mask_content_matches(
                    original, ruleset.content_patterns
                )
            redacted_files[path] = redacted_text
            safe_files.append(path)
            findings.append(SafetyFinding(path=path, reason=reason, action="redacted"))
            continue

        skipped_item = SafetyFinding(path=path, reason=reason, action="skipped")
        skipped.append(skipped_item)
        findings.append(skipped_item)

    return SafetyScanResult(
        safe_files=safe_files,
        skipped=skipped,
        redacted_files=redacted_files,
        findings=findings,
    )


def filter_sensitive_files(
    root: Path,
    files: list[Path],
    *,
    content_sniff: bool,
) -> tuple[list[Path], list[SkippedForSafety]]:
    result = apply_safety_filters(
        root,
        files,
        ruleset=default_ruleset(),
        content_sniff=content_sniff,
        redaction=False,
    )
    return result.safe_files, result.skipped
