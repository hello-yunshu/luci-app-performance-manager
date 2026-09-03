#!/usr/bin/env python3
"""Small gettext PO parser for the repository's source-level catalog checks."""
from __future__ import annotations

import ast
import re

_MSGID = re.compile(r"^msgid\s+(\".*\")\s*$")
_QUOTED = re.compile(r"^(\".*\")\s*$")


def _decode_quoted(token: str, line_number: int) -> str:
    try:
        value = ast.literal_eval(token)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"invalid PO string on line {line_number}: {exc}") from exc
    if not isinstance(value, str):
        raise ValueError(f"PO string on line {line_number} is not a string")
    return value


def parse_po_msgids(text: str) -> list[str]:
    """Return decoded msgids, including the empty header msgid.

    PO strings may use a literal on the ``msgid`` line followed by any number
    of gettext continuation lines.  Parsing each quoted literal independently
    preserves escaped quotes, backslashes, and ``\\n`` semantics.
    """
    msgids: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line_number = index + 1
        match = _MSGID.match(lines[index])
        if not match:
            index += 1
            continue

        value = _decode_quoted(match.group(1), line_number)
        index += 1
        while index < len(lines):
            continuation = _QUOTED.match(lines[index])
            if not continuation:
                break
            value += _decode_quoted(continuation.group(1), index + 1)
            index += 1
        msgids.append(value)
    return msgids


def missing_msgids(po_text: str, required_msgids: set[str]) -> list[str]:
    """Return required decoded msgids absent from a PO catalog."""
    available = set(parse_po_msgids(po_text))
    return sorted(required_msgids - available)
