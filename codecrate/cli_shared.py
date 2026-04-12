from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from .fences import is_fence_close, parse_fence_open
from .formats import FENCE_PATCH_META, MISSING_MANIFEST_ERROR
from .udiff import normalize_newlines


def _prefix_repo_header(text: str, label: str) -> str:
    header = f"# Repository: {label}\n\n"
    if text.startswith(header):
        return text
    return header + text


def _extract_diff_blocks(md_text: str) -> str:
    """
    Extract only diff fences from markdown and concatenate to a unified diff string.
    """
    lines = md_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        opened = parse_fence_open(lines[i])
        if opened is not None and opened[1] == "diff":
            fence = opened[0]
            i += 1
            while i < len(lines) and not is_fence_close(lines[i], fence):
                out.append(lines[i])
                i += 1
        i += 1
    return "\n".join(out) + "\n"


def _extract_patch_metadata(md_text: str) -> dict[str, object] | None:
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        opened = parse_fence_open(lines[i])
        if opened is not None and opened[1] == FENCE_PATCH_META:
            fence = opened[0]
            i += 1
            body: list[str] = []
            while i < len(lines) and not is_fence_close(lines[i], fence):
                body.append(lines[i])
                i += 1
            try:
                parsed = json.loads("\n".join(body))
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
        i += 1
    return None


def _read_text_with_policy(path: Path, *, encoding_errors: str) -> str:
    try:
        return path.read_text(encoding="utf-8", errors=encoding_errors)
    except UnicodeDecodeError as e:
        raise ValueError(
            f"Failed to decode UTF-8 for {path} (encoding_errors={encoding_errors})"
        ) from e


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _verify_patch_baseline(
    *,
    root: Path,
    diffs: Sequence[object],
    patch_meta: dict[str, object] | None,
    encoding_errors: str,
    policy: Literal["auto", "require", "ignore"] = "auto",
) -> None:
    if policy == "ignore":
        return

    if not patch_meta:
        if policy == "require":
            raise SystemExit(
                "apply: --check-baseline requires patch metadata "
                f"fence `{FENCE_PATCH_META}` with baseline hashes."
            )
        return

    baseline = patch_meta.get("baseline_files_sha256")
    if not isinstance(baseline, dict):
        if policy == "require":
            raise SystemExit(
                "apply: --check-baseline requires 'baseline_files_sha256' "
                "in patch metadata."
            )
        return

    mismatches: list[str] = []
    root_resolved = root.resolve()
    for fd in diffs:
        rel = getattr(fd, "path", "")
        op = getattr(fd, "op", "")
        if not isinstance(rel, str) or not rel:
            continue
        expected_sha = baseline.get(rel)
        path = root_resolved / rel

        if op == "add":
            if path.exists():
                mismatches.append(f"{rel} (expected absent before add)")
            continue

        if not isinstance(expected_sha, str) or not expected_sha:
            continue
        if not path.exists():
            mismatches.append(f"{rel} (missing; expected baseline file)")
            continue

        disk_text = normalize_newlines(
            _read_text_with_policy(path, encoding_errors=encoding_errors)
        )
        disk_sha = _sha256_text(disk_text)
        if disk_sha != expected_sha:
            mismatches.append(f"{rel} (baseline sha mismatch)")

    if mismatches:
        preview = ", ".join(mismatches[:5])
        suffix = "" if len(mismatches) <= 5 else ", ..."
        raise SystemExit(
            "apply: patch baseline does not match current repository state for "
            f"{len(mismatches)} file(s): {preview}{suffix}. "
            "Regenerate patch from current baseline or restore baseline files."
        )


def _validation_hint(message: str) -> str | None:
    if "expected exactly one codecrate-manifest block" in message:
        return (
            "ensure each repo section contains exactly one ```codecrate-manifest block"
        )
    if "Cross-repo anchor collision" in message:
        return (
            "make anchor ids unique across sections (or regenerate with codecrate pack)"
        )
    if "Machine header checksum mismatch" in message:
        return "manifest content changed; regenerate the pack to refresh checksum"
    if "Machine header" in message and "missing" in message:
        return "regenerate pack so machine header and manifest are emitted together"
    if "codecrate-machine-header block" in message:
        return "ensure exactly one machine header fence is present in the pack"
    if "Unsupported manifest format" in message:
        return "regenerate pack with a supported codecrate version"
    if "id_format_version" in message or "marker_format_version" in message:
        return "pack format metadata is incompatible; regenerate with current codecrate"
    if "Missing stubbed file block" in message:
        return "restore missing file block under ## Files or regenerate the pack"
    if "Manifest file missing from file blocks" in message:
        return (
            "ensure every manifest path has a matching ### `<path>` block in ## Files"
        )
    if "File block not present in manifest" in message:
        return "remove extra file blocks or regenerate manifest from source"
    if "Duplicate file block" in message:
        return "keep only one file block per path under ## Files"
    if "Missing canonical source" in message:
        return "restore the missing Function Library entry for the listed id"
    if "Orphan function-library entry" in message:
        return "remove unused Function Library entry or add matching manifest def"
    if "Missing FUNC marker" in message or "Unresolved marker mapping" in message:
        return "ensure stub contains a marker like ...  # ↪ FUNC:v1:<ID>"
    if "Repo-scope marker collision" in message:
        return "ensure each stub marker id maps to a single definition occurrence"
    if "sha mismatch" in message:
        return "pack content was edited after generation; regenerate from source files"
    if "failed to parse repository pack" in message:
        return "verify markdown fences/manifest JSON are intact"
    return None


def _split_validation_scope(message: str) -> tuple[str, str]:
    if message.startswith("repo '") and ": " in message:
        scope, rest = message.split(": ", 1)
        return scope, rest
    return "global", message


def _print_grouped_validation_report(report: object) -> None:
    warnings = list(getattr(report, "warnings", []))
    errors = list(getattr(report, "errors", []))

    if warnings:
        print("Warnings:")
        by_scope: dict[str, list[str]] = {}
        for msg in warnings:
            scope, detail = _split_validation_scope(msg)
            by_scope.setdefault(scope, []).append(detail)
        for scope, msgs in by_scope.items():
            print(f"- [{scope}]")
            for detail in msgs:
                print(f"  - {detail}")
                hint = _validation_hint(detail)
                if hint:
                    print(f"    hint: {hint}")

    if errors:
        print("Errors:")
        by_scope_err: dict[str, list[str]] = {}
        for msg in errors:
            scope, detail = _split_validation_scope(msg)
            by_scope_err.setdefault(scope, []).append(detail)
        for scope, msgs in by_scope_err.items():
            print(f"- [{scope}]")
            for detail in msgs:
                print(f"  - {detail}")
                hint = _validation_hint(detail)
                if hint:
                    print(f"    hint: {hint}")


def _validation_report_json(report: object) -> str:
    warnings = list(getattr(report, "warnings", []))
    errors = list(getattr(report, "errors", []))
    root_drift_paths = list(getattr(report, "root_drift_paths", []))
    payload = {
        "ok": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "root_drift_count": len(root_drift_paths),
        "root_drift_paths": root_drift_paths,
        "redacted_count": int(getattr(report, "redacted_count", 0)),
        "safety_skip_count": int(getattr(report, "safety_skip_count", 0)),
        "errors": errors,
        "warnings": warnings,
    }
    return json.dumps(payload, indent=2, sort_keys=False)


def _validation_policy_errors(report: object, args: argparse.Namespace) -> list[str]:
    warnings = list(getattr(report, "warnings", []))
    root_drift_paths = list(getattr(report, "root_drift_paths", []))
    redacted_count = int(getattr(report, "redacted_count", 0))
    safety_skip_count = int(getattr(report, "safety_skip_count", 0))

    errors: list[str] = []
    if bool(getattr(args, "fail_on_warning", False)) and warnings:
        errors.append(
            "Policy failure: warnings present "
            f"({len(warnings)}); use without --fail-on-warning to allow warnings"
        )
    if bool(getattr(args, "fail_on_root_drift", False)) and root_drift_paths:
        errors.append(
            "Policy failure: root drift detected for "
            f"{len(root_drift_paths)} file(s): {', '.join(root_drift_paths[:5])}"
        )
    if bool(getattr(args, "fail_on_redaction", False)) and redacted_count > 0:
        errors.append(f"Policy failure: pack reports {redacted_count} redacted file(s)")
    if bool(getattr(args, "fail_on_safety_skip", False)) and safety_skip_count > 0:
        errors.append(
            f"Policy failure: pack reports {safety_skip_count} safety-skipped file(s)"
        )
    return errors


def _validation_report_json_with_policy(
    report: object, policy_errors: list[str]
) -> str:
    warnings = list(getattr(report, "warnings", []))
    errors = list(getattr(report, "errors", []))
    root_drift_paths = list(getattr(report, "root_drift_paths", []))
    payload = {
        "ok": not errors and not policy_errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "policy_error_count": len(policy_errors),
        "root_drift_count": len(root_drift_paths),
        "root_drift_paths": root_drift_paths,
        "redacted_count": int(getattr(report, "redacted_count", 0)),
        "safety_skip_count": int(getattr(report, "safety_skip_count", 0)),
        "errors": errors,
        "warnings": warnings,
        "policy_errors": policy_errors,
    }
    return json.dumps(payload, indent=2, sort_keys=False)


def _print_top_level_help(parser: argparse.ArgumentParser) -> None:
    parser.print_help()
    print()
    print("Quick start examples:")
    print("  codecrate pack . -o context.md")
    print("  codecrate unpack context.md -o out/ --strict")
    print("  codecrate patch baseline.md . -o changes.md")
    print("  codecrate apply changes.md .")
    print("  codecrate validate-pack context.md --strict")
    print("  codecrate doctor .")
    print("  codecrate config show . --effective")
    print()
    print("Explicit-file mode notes:")
    print("  --stdin/--stdin0 treat stdin paths as the candidate set.")
    print("  Include globs are bypassed; exclude + ignore rules still apply.")
    print("  Outside-root and missing files are skipped (see --print-skipped).")


_NO_MANIFEST_HELP = (
    "packed markdown is missing a Manifest section; re-run `codecrate pack` "
    "without `--no-manifest` (or use `--manifest`)."
)


def _is_no_manifest_error(error: Exception) -> bool:
    return MISSING_MANIFEST_ERROR in str(error)


def _raise_no_manifest_error(
    parser: argparse.ArgumentParser,
    *,
    command_name: str,
) -> None:
    parser.error(f"{command_name}: {_NO_MANIFEST_HELP}")
