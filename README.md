# http-range

Parse and normalize the `Range` and `Content-Range` header field syntax into absolute byte intervals.

```python
from http_range import parse_range, parse_content_range

# bytes=0-499,1000- over a 2000-byte representation
parse_range("bytes=0-499,1000-", 2000)
# [ByteRange(start=0, end=499), ByteRange(start=1000, end=1999)]

# A suffix range needs the representation length to become absolute.
parse_range("bytes=-200", 1000)
# [ByteRange(start=800, end=999)]

parse_content_range("bytes 0-499/1000")
# ContentRange(start=0, end=499, length=1000)
```

## Why this exists

HTTP byte ranges look simple until you have to resolve them. `bytes=-200`
means the last 200 bytes, but only if you know the representation length;
`bytes=0-` means everything from byte zero, again only with a length. A parser
that returns the raw text leaves every caller to reimplement the same
normalization, and each one gets a different answer for a suffix longer than
the representation or an end offset past the end.

This library makes one decision: **the caller supplies the representation
length when the header form cannot be resolved without it.** Suffix ranges and
open-ended ranges raise `RangeError` when `length` is omitted. That is a hard
line rather than a best-effort guess, because guessing produces silently wrong
intervals. Closed ranges (`bytes=0-499`) are parsed without a length, and any
range that is given a length is clamped to `[0, length - 1]`.

Unsatisfiable input is also an error. RFC 9110 permits a server to ignore
unsatisfiable ranges in a multi-range request, but this parser raises
`RangeError` so the caller can distinguish malformed syntax from a range that
simply cannot be satisfied. Catch the exception at the layer that owns the
policy.

## The awkward edge

A suffix range larger than the representation is legal and means the whole
representation: `parse_range("bytes=-2000", 1000)` returns
`[ByteRange(0, 999)]`, not an error. A suffix of exactly zero (`bytes=-0`) is
rejected, because it selects no bytes and has no defined meaning.

## API

- `parse_range(value, length=None) -> list[ByteRange]`
- `parse_content_range(value, length=None) -> ContentRange`
- `ByteRange(start, end)` — inclusive interval; `.length` is `end - start + 1`.
- `ContentRange(start, end, length)` — `start`/`end` are `None` for an
  unsatisfied range; `.satisfied` reports whether they are present.
- `RangeError` — subclass of `ValueError`, raised for malformed syntax,
  unsupported units, and unsatisfiable ranges.

Only the `bytes` unit is supported for `Range`. `Content-Range` also accepts
the legacy `*` unit (`*/*`).

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

