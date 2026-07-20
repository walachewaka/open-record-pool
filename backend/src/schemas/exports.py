"""
API schemas for DJ bundle exports (MOO-86). The response envelope is the
MOO-77 JobOut -- an export is just a background job.
"""
import re
from typing import Optional

from pydantic import BaseModel, Field, validator

from src.export.naming import FORMATS

VOLUME_LABEL = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
# A POSIX mount point ("/Volumes/ORP_USB") or a Windows drive ("E:").
REKORDBOX_ROOT = re.compile(r"^([A-Za-z]:|(/[^/\x00]{1,64}){1,8})$")


class ExportRequest(BaseModel):
    """
    Ask for one bundle. [format] defaults to the crate's dj_target; the two
    path hints only matter for the formats that address files absolutely
    (rekordbox) or by volume name (Traktor).
    """

    format: Optional[str] = None
    volume_label: str = Field("ORP_USB", max_length=32)
    rekordbox_root: Optional[str] = Field(None, max_length=256)

    @validator("format")
    def known_format(cls, value):  # noqa: N805
        if value is not None and value not in FORMATS:
            raise ValueError("format must be one of: {}".format(", ".join(FORMATS)))
        return value

    @validator("volume_label")
    def usb_safe_label(cls, value):  # noqa: N805
        if not VOLUME_LABEL.match(value or ""):
            raise ValueError("volume_label must be 1-32 chars of A-Z, 0-9, _ or -")
        return value

    @validator("rekordbox_root")
    def plausible_root(cls, value):  # noqa: N805
        if value is not None and not REKORDBOX_ROOT.match(value):
            raise ValueError(
                "rekordbox_root must be a mount point (/Volumes/ORP_USB) "
                "or a Windows drive (E:)"
            )
        return value
