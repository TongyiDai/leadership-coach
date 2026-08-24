#!/usr/bin/env python3
"""Extract the current user's own speaking turns from a meeting transcript.

Privacy-first: keeps only turns spoken by "me" (matched by display name /
alias / open_id), and replaces every OTHER speaker with a fixed ``[对方]``
placeholder so conversational rhythm survives while third parties are
de-identified. Raw other-party text is dropped, never emitted.

Input: a Feishu minutes/note transcript as JSON on stdin. The transcript shape
varies across tenants, so this reads several common shapes:

  - {"sentences": [{"speaker": "...", "text": "..."}, ...]}
  - {"data": {"sentences": [...]}}
  - {"paragraphs": [{"speaker_name": "...", "content": "..."}]}
  - {"transcript": [{"user_name": "...", "sentence": "..."}]}
  - a bare list of turn objects

Each turn object is scanned for a speaker field (speaker / speaker_name /
user_name / from_name / name / userName / speakerName) and a text field
(text / content / sentence / words / value / body).

Output (stdout): JSON
  {
    "ok": true,
    "total_turns": <int>,          # all turns parsed
    "my_turns": <int>,             # turns attributed to me
    "matched_by": "name|id|none",
    "dialogue": [                  # ordered, de-identified
      {"role": "me", "text": "<my words>"},
      {"role": "other"}            # placeholder, no text
    ],
    "my_turns_only": ["<my words>", ...]
  }

Nothing is written to disk. Callers keep the raw transcript in-process only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

SPEAKER_KEYS = (
    "speaker",
    "speaker_name",
    "speakerName",
    "user_name",
    "userName",
    "from_name",
    "fromName",
    "name",
)
TEXT_KEYS = ("text", "content", "sentence", "words", "value", "body")
ID_KEYS = ("speaker_id", "speakerId", "user_id", "userId", "open_id", "openId", "from_id", "fromId")
SENTENCE_CONTAINER_KEYS = ("sentences", "paragraphs", "transcript", "items", "turns", "records")


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _find_turns(payload: Any) -> list[dict[str, Any]]:
    """Locate the list of turn objects inside an arbitrary transcript payload."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in SENTENCE_CONTAINER_KEYS:
            value = payload.get(key)
            if isinstance(value, list) and value:
                return [item for item in value if isinstance(item, dict)]
        # Recurse one level into common wrappers like {"data": {...}}.
        for key in ("data", "result", "content", "body"):
            value = payload.get(key)
            if isinstance(value, (dict, list)):
                found = _find_turns(value)
                if found:
                    return found
    return []


def _pick(turn: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = turn.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        # words is sometimes a list of {"text": ...}
        if isinstance(value, list):
            joined = "".join(
                w.get("text", "") for w in value if isinstance(w, dict) and isinstance(w.get("text"), str)
            ).strip()
            if joined:
                return joined
    return None


def _is_me(
    speaker: str | None,
    speaker_id: str | None,
    my_names: list[str],
    my_ids: list[str],
) -> tuple[bool, str]:
    if speaker_id and my_ids and any(speaker_id == mid for mid in my_ids):
        return True, "id"
    if speaker and my_names:
        s = _norm(speaker)
        for name in my_names:
            n = _norm(name)
            if n and (n == s or n in s or s in n):
                return True, "name"
    return False, "none"


def extract(
    payload: Any,
    my_names: list[str],
    my_ids: list[str],
) -> dict[str, Any]:
    turns = _find_turns(payload)
    dialogue: list[dict[str, Any]] = []
    my_turns_only: list[str] = []
    matched_by = "none"
    for turn in turns:
        speaker = _pick(turn, SPEAKER_KEYS)
        speaker_id = None
        for key in ID_KEYS:
            value = turn.get(key)
            if isinstance(value, str) and value.strip():
                speaker_id = value.strip()
                break
        text = _pick(turn, TEXT_KEYS)
        if text is None:
            continue
        is_me, how = _is_me(speaker, speaker_id, my_names, my_ids)
        if is_me:
            if matched_by == "none":
                matched_by = how
            dialogue.append({"role": "me", "text": text})
            my_turns_only.append(text)
        else:
            dialogue.append({"role": "other"})
    return {
        "ok": True,
        "total_turns": len(turns),
        "my_turns": len(my_turns_only),
        "matched_by": matched_by,
        "dialogue": dialogue,
        "my_turns_only": my_turns_only,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract the current user's own speaking turns, de-identifying others.")
    ap.add_argument("--me", action="append", default=[], help="my display name or alias (repeatable)")
    ap.add_argument("--me-id", action="append", default=[], help="my open_id / user_id (repeatable, more precise)")
    args = ap.parse_args()

    if not args.me and not args.me_id:
        print(json.dumps({"ok": False, "error": "provide at least one --me name or --me-id"}, ensure_ascii=False),
              file=sys.stderr)
        return 2

    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"ok": False, "error": "empty transcript on stdin"}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"invalid JSON: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    result = extract(payload, args.me, args.me_id)
    print(json.dumps(result, ensure_ascii=False))
    if result["my_turns"] == 0:
        # Not an error: transcript may genuinely contain no turns by me, or the
        # speaker labels did not match. Signal via exit code for scripting.
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
