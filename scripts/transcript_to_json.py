#!/usr/bin/env python3
"""Convert a plain-text Feishu/Lark meeting transcript into the JSON shape that
``extract_speaker_turns.py`` consumes.

Why this exists: ``lark-cli minutes +detail --transcript`` writes a plain-text
transcript file (not JSON). The speaker-turn extractor wants JSON. This bridges
them without changing the extractor, so de-identification still happens in one
place (the extractor replaces every non-me speaker with ``[对方]``).

Input (stdin): the plain-text transcript. The common lark-cli shape is a header
line ``<speaker> HH:MM:SS(.mmm)`` followed by one or more text lines, repeating:

    2026-08-19 17:13:37 CST|45min 14s

    Keywords:
    ...

    Speaker A 00:00:11.251
    你先看一下这几件事的优先级。

    Speaker B 00:00:12.821
    好，我们一块过一遍。

It also tolerates a few near variants:
  - ``[HH:MM:SS] Name: text`` on one line
  - ``Name: text`` (no timestamp)
Leading metadata (title line, ``Keywords:`` block, blank lines) is skipped:
any line before the first recognized speaker header is ignored.

Output (stdout): JSON ``{"sentences": [{"speaker": "...", "text": "..."}, ...]}``
ready to pipe into ``extract_speaker_turns.py``. No disk writes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

# "<speaker> HH:MM:SS" or "<speaker> HH:MM:SS.mmm" at end of line (lark-cli shape).
HEADER_TS_END = re.compile(r"^(?P<speaker>.+?)\s+(?P<ts>\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\s*$")
# "[HH:MM:SS] Name: text" or "[HH:MM] Name: text" on one line.
BRACKET_TS_LINE = re.compile(r"^\[(?:\d{1,2}:){1,2}\d{2}(?:\.\d+)?\]\s*(?P<speaker>[^:：]{1,40})[:：]\s*(?P<text>.+)$")
# "Name: text" (no timestamp); speaker kept short to avoid eating prose.
NAME_COLON_LINE = re.compile(r"^(?P<speaker>[^:：\d]{1,20})[:：]\s*(?P<text>.+)$")
# Lines that are clearly metadata, not dialogue.
META_PREFIXES = ("keywords:", "关键词", "摘要", "summary:", "标题", "title:")


def _looks_meta(line: str) -> bool:
    low = line.strip().lower()
    return any(low.startswith(p) for p in META_PREFIXES)


def parse_transcript(text: str) -> list[dict[str, str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    turns: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    seen_first_speaker = False

    def flush() -> None:
        nonlocal current
        if current and current["text"].strip():
            current["text"] = current["text"].strip()
            turns.append(current)
        current = None

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue

        # One-line forms first.
        m = BRACKET_TS_LINE.match(line)
        if m:
            flush()
            seen_first_speaker = True
            turns.append({"speaker": m.group("speaker").strip(), "text": m.group("text").strip()})
            continue

        # Header line: "<speaker> HH:MM:SS(.mmm)" — starts a new turn.
        m = HEADER_TS_END.match(line)
        if m:
            flush()
            seen_first_speaker = True
            current = {"speaker": m.group("speaker").strip(), "text": ""}
            continue

        # "Name: text" one-liner (only after we've skipped the metadata head,
        # and only if it's not obviously prose with a colon).
        m = NAME_COLON_LINE.match(line)
        if m and not _looks_meta(line):
            flush()
            seen_first_speaker = True
            turns.append({"speaker": m.group("speaker").strip(), "text": m.group("text").strip()})
            continue

        # Body line for the current turn; ignore anything before the first speaker
        # (title, keywords, duration header).
        if current is not None:
            current["text"] += line.strip()
        elif seen_first_speaker:
            # A stray body line with no open turn: attach to the last turn.
            if turns:
                turns[-1]["text"] = (turns[-1]["text"] + line.strip()).strip()
        # else: pre-transcript metadata, skip.

    flush()
    return turns


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert a plain-text meeting transcript to speaker-turn JSON.")
    ap.add_argument("--file", help="read transcript from a file instead of stdin")
    args = ap.parse_args()

    if args.file:
        try:
            text = open(args.file, encoding="utf-8").read()
        except OSError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
    else:
        text = sys.stdin.read()

    if not text.strip():
        print(json.dumps({"ok": False, "error": "empty transcript input"}, ensure_ascii=False), file=sys.stderr)
        return 2

    turns = parse_transcript(text)
    payload: dict[str, Any] = {"sentences": turns}
    print(json.dumps(payload, ensure_ascii=False))
    if not turns:
        # Parsed nothing recognizable: signal via exit code, but valid JSON is on stdout.
        print(json.dumps({"ok": False, "error": "no speaker turns recognized"}, ensure_ascii=False), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
