"""
Keyset (cursor) pagination helpers (MOO-77).

The cursor token is base64url (no padding) of the JSON
{"s": "<sort>", "o": "asc"|"desc", "k": [<last_sort_value>, <last_id>]}.
Keyset columns must be non-nullable (use id/created_at, or coalesce at write
time); every keyset pair gets a composite index. See docs/ARCHITECTURE.md.
"""
import base64
import json

from fastapi import HTTPException
from tortoise.expressions import Q


def encode_cursor(sort, order, key_values):
    """
    Builds the opaque cursor token for the next page: the sort column, the
    direction, and the (last_sort_value, last_id) keyset of the current page.
    """
    payload = {"s": sort, "o": order, "k": list(key_values)}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token):
    """
    Decodes a cursor token back to its {"s", "o", "k"} dict. Any tampered or
    undecodable token is a 422, never a 500.
    """
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("s"), str)
            or payload.get("o") not in ("asc", "desc")
            or not isinstance(payload.get("k"), list)
            or not payload["k"]
        ):
            raise ValueError("bad cursor payload")
        return payload
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid cursor")


def keyset_filter(sort, order, key_value, last_id, id_field="id"):
    """
    The keyset predicate for "rows after (key_value, last_id)":
    (sort_col, id) > (key_value, last_id) for asc, < for desc. When the sort
    column IS the id column the tuple collapses to a single comparison.
    """
    op = "gt" if order == "asc" else "lt"
    if sort == id_field:
        return Q(**{"{}__{}".format(id_field, op): last_id})
    return Q(**{"{}__{}".format(sort, op): key_value}) | (
        Q(**{sort: key_value}) & Q(**{"{}__{}".format(id_field, op): last_id})
    )
