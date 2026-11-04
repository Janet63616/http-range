"""Core parsing for HTTP Range and Content-Range header fields.

Design decisions:

* ``parse_range`` returns a list of absolute, inclusive ``ByteRange`` objects.
  A suffix range (``bytes=-N``) is only resolvable to an absolute interval when
  the representation length is known, so a length is required for suffix ranges
  and for open-ended ranges (``bytes=N-``).  When the length is not supplied,
  those forms raise ``RangeError`` rather than guessing.

* Unsatisfiable ranges are rejected with ``RangeError``.  RFC 9110 allows a
  server to ignore unsatisfiable parts of a multi-range request, but silently
  dropping input makes it impossible for a caller to distinguish "the client
  asked for nothing valid" from "the client sent malformed syntax".  The caller
  can catch ``RangeError`` and decide.

* ``parse_content_range`` accepts both the ``bytes`` unit and the legacy ``*``
  unit for responses whose length is unknown.  The returned ``ContentRange``
  always has concrete ``start``/``end`` when the unit is ``bytes``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

__all__ = [
    "ByteRange",
    "ContentRange",
    "RangeError",
    "parse_range",
    "parse_content_range",
]


class RangeError(ValueError):
    """Raised when a Range or Content-Range header field cannot be parsed."""


@dataclass(frozen=True)
class ByteRange:
    """An absolute, inclusive byte interval ``[start, end]``.

    Both endpoints are inclusive, matching the HTTP syntax where
    ``bytes=0-499`` denotes the first 500 bytes.  ``start`` is never greater
    than ``end``; empty intervals are not representable.
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0:
            raise RangeError(f"byte range start must be non-negative: {self.start}")
        if self.end < self.start:
            raise RangeError(
                f"byte range end {self.end} precedes start {self.start}"
            )

    @property
    def length(self) -> int:
        """Number of bytes covered by the interval."""
        return self.end - self.start + 1


@dataclass(frozen=True)
class ContentRange:
    """A parsed Content-Range header.

    ``start`` and ``end`` are inclusive.  For an unsatisfied range
    (``bytes */123``) both are ``None`` and ``length`` is the representation
    length.  For ``*/*`` all three are ``None``.
    """

    start: Optional[int]
    end: Optional[int]
    length: Optional[int]

    def __post_init__(self) -> None:
        if self.start is None and self.end is not None:
            raise RangeError("Content-Range end without start")
        if self.end is None and self.start is not None:
            raise RangeError("Content-Range start without end")
        if self.start is not None and self.end is not None:
            if self.start < 0:
                raise RangeError(f"Content-Range start must be non-negative: {self.start}")
            if self.end < self.start:
                raise RangeError(
                    f"Content-Range end {self.end} precedes start {self.start}"
                )
        if self.length is not None and self.length < 0:
            raise RangeError(f"Content-Range length must be non-negative: {self.length}")

    @property
    def satisfied(self) -> bool:
        """True when the range carries concrete start/end positions."""
        return self.start is not None and self.end is not None


_DIGITS = frozenset("0123456789")


def _is_digits(text: str) -> bool:
    return bool(text) and all(ch in _DIGITS for ch in text)


def _parse_uint(text: str, what: str) -> int:
    if not _is_digits(text):
        raise RangeError(f"invalid {what}: {text!r}")
    return int(text)


def _split_unit(value: str, separator: str = "=") -> tuple[str, str]:
    """Split ``unit=spec`` (or ``unit spec``) and return ``(unit, spec)``.

    The unit is case-insensitive per HTTP token rules, but the spec is
    case-sensitive for the ``*`` placeholder.  We normalize the unit to lower
    case and leave the spec alone.
    """
    if separator not in value:
        raise RangeError(f"missing {separator!r} in header value: {value!r}")
    unit, spec = value.split(separator, 1)
    unit = unit.strip().lower()
    if not unit:
        raise RangeError(f"empty range unit in header value: {value!r}")
    return unit, spec.strip()


def _normalize_interval(raw_start: str, raw_end: str, length: Optional[int]) -> ByteRange:
    """Turn one ``start-end`` pair into an absolute ByteRange.

    ``raw_start`` may be empty for suffix ranges; ``raw_end`` may be empty for
    open-ended ranges.  Both empty is rejected: ``bytes=-`` has no meaning.
    """
    if raw_start == "" and raw_end == "":
        raise RangeError("range interval has neither start nor end")

    if raw_start == "":
        # Suffix range: bytes=-N means the final N bytes.
        if length is None:
            raise RangeError("suffix range requires a known representation length")
        suffix = _parse_uint(raw_end, "suffix length")
        if suffix == 0:
            raise RangeError("suffix length must be greater than zero")
        if length == 0:
            raise RangeError("suffix range on an empty representation is unsatisfiable")
        if suffix >= length:
            return ByteRange(0, length - 1)
        return ByteRange(length - suffix, length - 1)

    start = _parse_uint(raw_start, "range start")

    if raw_end == "":
        if length is None:
            raise RangeError("open-ended range requires a known representation length")
        if length == 0 or start >= length:
            raise RangeError(
                f"range start {start} is outside representation of length {length}"
            )
        return ByteRange(start, length - 1)

    end = _parse_uint(raw_end, "range end")
    if end < start:
        raise RangeError(f"range end {end} precedes start {start}")
    if length is not None:
        if start >= length:
            raise RangeError(
                f"range start {start} is outside representation of length {length}"
            )
        if end >= length:
            end = length - 1
    return ByteRange(start, end)


def parse_range(value: str, length: Optional[int] = None) -> List[ByteRange]:
    """Parse a Range header value into absolute byte intervals.

    ``value`` is the raw header value, e.g. ``"bytes=0-499"`` or
    ``"bytes=0-0,-1"``.  ``length`` is the size of the selected
    representation; it is required to resolve suffix ranges (``bytes=-N``)
    and open-ended ranges (``bytes=N-``).  When ``length`` is provided, all
    returned intervals are clamped to ``[0, length - 1]``.

    Only the ``bytes`` unit is supported.  Any other unit raises
    ``RangeError``; this is deliberate because the semantics of other units
    are not defined by the base HTTP specification.

    Raises ``RangeError`` for malformed syntax, unsupported units, and ranges
    that cannot be satisfied against ``length``.
    """
    if not isinstance(value, str):
        raise RangeError("Range header value must be a string")

    unit, spec = _split_unit(value, "=")
    if unit != "bytes":
        raise RangeError(f"unsupported range unit: {unit!r}")
    if spec == "":
        raise RangeError("empty range set")

    if length is not None:
        if not isinstance(length, int) or length < 0:
            raise RangeError(f"representation length must be a non-negative int: {length!r}")

    parts = [p.strip() for p in spec.split(",")]
    if any(p == "" for p in parts):
        raise RangeError(f"empty interval in range set: {spec!r}")

    ranges: List[ByteRange] = []
    for part in parts:
        if "-" not in part:
            raise RangeError(f"interval missing '-': {part!r}")
        raw_start, raw_end = part.split("-", 1)
        ranges.append(_normalize_interval(raw_start, raw_end, length))
    return ranges


def parse_content_range(value: str, length: Optional[int] = None) -> ContentRange:
    """Parse a Content-Range header value.

    Accepts ``bytes start-end/length``, ``bytes start-end/*``, and
    ``bytes */length``.  The legacy ``*`` unit (``*/*``) is accepted and
    yields a ContentRange with all fields ``None``.

    When ``length`` is supplied and the header uses ``*`` for the total, the
    supplied length fills in the missing total.  A header total that disagrees
    with a supplied ``length`` raises ``RangeError``; the two sources of truth
    cannot both be right.
    """
    if not isinstance(value, str):
        raise RangeError("Content-Range header value must be a string")

    if value.strip() == "*/*":
        return ContentRange(None, None, length)

    unit, spec = _split_unit(value, " ")

    if unit == "*":
        if spec != "*":
            raise RangeError(f"invalid Content-Range with '*' unit: {value!r}")
        return ContentRange(None, None, length)

    if unit != "bytes":
        raise RangeError(f"unsupported Content-Range unit: {unit!r}")

    if "/" not in spec:
        raise RangeError(f"Content-Range missing '/': {value!r}")
    range_part, total_part = spec.split("/", 1)
    range_part = range_part.strip()
    total_part = total_part.strip()

    if total_part == "*":
        total: Optional[int] = length
    else:
        total = _parse_uint(total_part, "Content-Range total")
        if length is not None and total != length:
            raise RangeError(
                f"Content-Range total {total} disagrees with supplied length {length}"
            )

    if range_part == "*":
        if total is None:
            raise RangeError("unsatisfied Content-Range requires a known total")
        return ContentRange(None, None, total)

    if "-" not in range_part:
        raise RangeError(f"Content-Range interval missing '-': {range_part!r}")
    raw_start, raw_end = range_part.split("-", 1)
    start = _parse_uint(raw_start, "Content-Range start")
    end = _parse_uint(raw_end, "Content-Range end")
    if end < start:
        raise RangeError(f"Content-Range end {end} precedes start {start}")
    if total is not None and end >= total:
        raise RangeError(
            f"Content-Range end {end} is outside representation of length {total}"
        )
    return ContentRange(start, end, total)
