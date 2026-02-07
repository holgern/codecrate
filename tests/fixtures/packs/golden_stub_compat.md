# Codecrate Context Pack

## Machine Header

```codecrate-machine-header
{"format":"codecrate.v4","manifest_sha256":"3b784e413ad12b16847bbaeae6f01b3c2defb59de1e11f4d444166ef4275649a","repo_label":"golden-stub","repo_slug":"golden-stub"}
```

## Manifest

```codecrate-manifest
{
  "format": "codecrate.v4",
  "id_format_version": "sha1-8-upper:v1",
  "marker_format_version": "v1",
  "root": ".",
  "files": [
    {
      "path": "a.py",
      "line_count": 3,
      "sha256_original": "5b76d0962c09ab4ee309fac65fad3568c97abdec983b405146ae3e86a235e352",
      "sha256_stubbed": "8ab825c6df9a183209e8c44b1dbd89e83bf39bcf1eb888f0b523dbe23c5105f2",
      "defs": [
        {
          "path": "a.py",
          "module": "a",
          "qualname": "f",
          "id": "DEADBEEF",
          "local_id": "DEADBEEF",
          "has_marker": true
        }
      ],
      "classes": [],
      "module": "a"
    }
  ]
}
```

## Function Library

### DEADBEEF — `a.f` (a.py:L1-L2)

```python
def f():
    return 1
```

## Files

### `a.py`

```python
def f():
    ...  # ↪ FUNC:v1:DEADBEEF
```
