from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .ids import stable_body_hash
from .model import ClassRef, DefRef, FilePack, PackResult
from .parse import module_name_for, parse_symbols
from .stubber import stub_file_text
from .symbol_backend import extract_non_python_symbols


def _extract_canonical_source(text: str, d: DefRef) -> str:
    lines = text.splitlines(keepends=True)
    i0 = max(0, d.decorator_start - 1)
    i1 = min(len(lines), d.end_line)
    return "".join(lines[i0:i1]).rstrip() + "\n"


def _line_count(text: str) -> int:
    return text.count("\n") + 1 if text else 0


def pack_repo(
    root: Path,
    files: list[Path],
    keep_docstrings: bool = True,
    dedupe: bool = False,
    symbol_backend: str = "auto",
) -> tuple[PackResult, dict[str, str]]:
    filepacks: list[FilePack] = []
    all_defs: list[DefRef] = []
    all_classes: list[ClassRef] = []

    local_canon: dict[str, str] = {}

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")

        if path.suffix.lower() == ".py":
            classes, defs = parse_symbols(path=path, root=root, text=text)
            file_module = module_name_for(path, root)

            for d in defs:
                local_canon[d.local_id] = _extract_canonical_source(text, d)

            stubbed = stub_file_text(text, defs, keep_docstrings=keep_docstrings)
        else:
            # Non-Python files are included verbatim.
            # Optional symbol extraction is index-only.
            classes = []
            sym = extract_non_python_symbols(
                path=path,
                root=root,
                text=text,
                backend=symbol_backend,
            )
            defs = sym.defs
            file_module = ""
            stubbed = text

        fp = FilePack(
            path=path,
            module=file_module,
            original_text=text,
            stubbed_text=stubbed,
            line_count=_line_count(text),
            classes=classes,
            defs=defs,
        )
        filepacks.append(fp)
        all_defs.extend(defs)
        all_classes.extend(classes)

    canonical_sources: dict[str, str] = {}
    if not dedupe:
        canonical_sources = {
            d.local_id: local_canon[d.local_id]
            for d in all_defs
            if d.local_id in local_canon
        }
    else:
        seen_by_hash: dict[str, str] = {}
        remapped_defs: list[DefRef] = []

        for d in all_defs:
            code = local_canon.get(d.local_id)
            if code is None:
                remapped_defs.append(d)
                continue
            h = stable_body_hash(code)
            cid = seen_by_hash.get(h)
            if cid is None:
                cid = d.local_id
                seen_by_hash[h] = cid
                canonical_sources[cid] = code
            remapped_defs.append(replace(d, id=cid))

        all_defs = remapped_defs

        defs_by_file: dict[Path, list[DefRef]] = {}
        for d in all_defs:
            defs_by_file.setdefault(d.path, []).append(d)

        filepacks2: list[FilePack] = []
        for fp in filepacks:
            defs2 = defs_by_file.get(fp.path, [])
            if fp.path.suffix.lower() == ".py":
                stubbed2 = stub_file_text(
                    fp.original_text,
                    defs2,
                    keep_docstrings=keep_docstrings,
                )
            else:
                stubbed2 = fp.original_text
            filepacks2.append(
                FilePack(
                    path=fp.path,
                    module=fp.module,
                    original_text=fp.original_text,
                    stubbed_text=stubbed2,
                    line_count=fp.line_count,
                    classes=fp.classes,
                    defs=defs2,
                )
            )
        filepacks = filepacks2

    pack = PackResult(root=root, files=filepacks, classes=all_classes, defs=all_defs)
    return pack, canonical_sources
