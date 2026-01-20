# codecrate

`codecrate` turns a Python repo into a Markdown “context pack” for LLMs, and supports round-tripping:

- `pack`: repo → context.md
- `unpack`: context.md → reconstructed files
- `patch`: old context.md + current repo → diff-only patch.md
- `apply`: patch.md → apply changes to repo

## Install

```bash
python -m pip install -e .
```
