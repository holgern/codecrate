from __future__ import annotations

PACK_FORMAT_VERSION = "codecrate.v4"
PATCH_FORMAT_VERSION = "codecrate.patch.v1"
MANIFEST_JSON_FORMAT_VERSION = "codecrate.manifest-json.v1"

FENCE_MACHINE_HEADER = "codecrate-machine-header"
FENCE_MANIFEST = "codecrate-manifest"
FENCE_PATCH_META = "codecrate-patch-meta"

MISSING_MANIFEST_ERROR = (
    "No codecrate-manifest block found. This pack cannot be used for "
    "unpack/patch/validate-pack; re-run `codecrate pack` with --manifest "
    "(or omit --no-manifest)."
)
