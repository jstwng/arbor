"""Incremental JSON branch parser tests."""
from arbor.pipeline.stream import parse_branches_incremental, strip_fences


def test_strip_fences_basic():
    assert strip_fences("```json\n{\"x\":1}\n```") == '{"x":1}'
    assert strip_fences('{"x":1}') == '{"x":1}'
    assert strip_fences("```\n{\"x\":1}\n```") == '{"x":1}'


def test_complete_single_branch():
    raw = '{"root":"T","branches":[{"label":"A","children":[]}]}'
    out = list(parse_branches_incremental(raw))
    assert len(out) == 1
    idx, branch = out[0]
    assert idx == 0
    assert branch["label"] == "A"


def test_complete_multiple_branches():
    raw = (
        '{"root":"T","branches":['
        '{"label":"A","children":[]},'
        '{"label":"B","children":[]}'
        ']}'
    )
    out = list(parse_branches_incremental(raw))
    assert [i for i, _ in out] == [0, 1]
    assert [b["label"] for _, b in out] == ["A", "B"]


def test_incremental_via_chunks():
    chunks = [
        '{"root":"T",',
        '"branches":[',
        '{"label":"A","children":[]},',
        '{"label":"B",',
        '"children":[]}',
        ']}',
    ]
    seen: list[tuple[int, dict]] = []
    buf = ""
    for chunk in chunks:
        buf += chunk
        for evt in parse_branches_incremental(buf, already_seen=len(seen)):
            seen.append(evt)
    assert [b["label"] for _, b in seen] == ["A", "B"]


def test_handles_fenced_output():
    raw = '```json\n{"root":"T","branches":[{"label":"A","children":[]}]}\n```'
    out = list(parse_branches_incremental(raw))
    assert out[0][1]["label"] == "A"


def test_partial_branch_not_emitted():
    raw = '{"root":"T","branches":[{"label":"A","child'
    out = list(parse_branches_incremental(raw))
    assert out == []
