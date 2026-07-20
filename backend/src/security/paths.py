"""
Path confinement (MOO-89): resolve a user-supplied name under a fixed root and
refuse anything that escapes it (`../`, absolute paths, symlink tricks).

Any endpoint that turns user input into a filename (uploads, art, exports)
MUST route through safe_join.
"""
import os

from fastapi import HTTPException


def safe_join(root: str, name: str) -> str:
    """
    Return realpath(root/name) if it stays inside realpath(root), else raise
    HTTPException(400). `name` is treated as a single path component -- its
    directory parts are stripped first, so callers cannot walk out with `../`.
    """
    if not name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid path.")
    # Collapse to a bare filename: strip any directory the caller supplied.
    base = os.path.basename(name.replace("\\", "/"))
    if not base or base in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid path.")
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, base))
    if candidate != root_real and not candidate.startswith(root_real + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path.")
    return candidate
