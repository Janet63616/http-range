"""HTTP Range header parsing and normalization.

Public API:
    parse_range(value, length=None) -> list[ByteRange]
    parse_content_range(value, length=None) -> ContentRange
    ByteRange
    ContentRange
    RangeError
"""

from .core import ByteRange, ContentRange, RangeError, parse_content_range, parse_range

__all__ = [
    "ByteRange",
    "ContentRange",
    "RangeError",
    "parse_range",
    "parse_content_range",
]
