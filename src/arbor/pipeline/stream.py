"""Incremental JSON parser for branches[i] objects.

We don't need a full streaming JSON parser. The schema is fixed:
{"root": str, "branches": [obj, obj, ...]}. We scan for the
`branches` array and extract balanced top-level objects from inside it.
"""
from __future__ import annotations

import json
import re
from typing import Iterator


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL)


def strip_fences(text: str) -> str:
    m = _FENCE_RE.match(text)
    return m.group(1) if m else text


def _find_branches_array_start(buf: str) -> int:
    key = '"branches"'
    i = buf.find(key)
    if i < 0:
        return -1
    j = buf.find("[", i + len(key))
    return j + 1 if j >= 0 else -1


def _scan_balanced_objects(buf: str, start: int) -> list[tuple[int, int]]:
    """Return (object_start, object_end_exclusive) pairs for top-level
    objects in the array starting at `start`. Stops scanning if it hits
    unbalanced state, leaving partial trailing data alone."""
    spans: list[tuple[int, int]] = []
    i = start
    n = len(buf)
    while i < n:
        # skip whitespace and commas
        while i < n and buf[i] in " \t\n\r,":
            i += 1
        if i >= n:
            break
        if buf[i] == "]":
            break  # array closed
        if buf[i] != "{":
            return spans  # unexpected; bail
        depth = 0
        in_str = False
        escape = False
        obj_start = i
        while i < n:
            ch = buf[i]
            if escape:
                escape = False
            elif ch == "\\" and in_str:
                escape = True
            elif ch == '"':
                in_str = not in_str
            elif not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        spans.append((obj_start, i + 1))
                        i += 1
                        break
            i += 1
        else:
            return spans  # ran off end mid-object
    return spans


def parse_branches_incremental(
    buf: str, already_seen: int = 0
) -> Iterator[tuple[int, dict]]:
    """Yield (branch_index, branch_dict) for branches that have just become
    complete. `already_seen` tells us how many we've already emitted so we
    skip them on re-scans."""
    cleaned = strip_fences(buf)
    arr_start = _find_branches_array_start(cleaned)
    if arr_start < 0:
        return
    spans = _scan_balanced_objects(cleaned, arr_start)
    for idx, (s, e) in enumerate(spans):
        if idx < already_seen:
            continue
        try:
            yield idx, json.loads(cleaned[s:e])
        except json.JSONDecodeError:
            return  # stop at first malformed; re-scan later when more arrives
