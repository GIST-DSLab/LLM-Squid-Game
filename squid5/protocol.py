"""Parsers for every answer line. A parser returns a dict or raises FormatError.

Keys are matched only at the start of a line (after markdown decoration),
never mid-line: the team-wallet smokes showed a REASON sentence containing
"stop: X" being read as a STOP line when mid-line matches were allowed.
"""

from __future__ import annotations

import re

from .puzzle import ACTIONS


class FormatError(ValueError):
    pass


def _field(text: str, key: str, required: bool = True) -> str | None:
    for line in text.splitlines():
        m = re.match(rf"^[\s*_`>#-]*{key}[*_`]*\s*:\s*(.*)$", line, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().strip("*_`").strip()
    if required:
        raise FormatError(f"missing {key} line")
    return None


def _int(value: str, key: str) -> int:
    m = re.fullmatch(r"[<\s]*(\d[\d,]*)\s*[>]*.*?", value)
    if not m:
        raise FormatError(f"{key} is not a whole number: {value!r}")
    return int(m.group(1).replace(",", ""))


def _names(value: str, alive: list[str], key: str) -> list[str]:
    if value.strip().upper().startswith("NONE"):
        return []
    names = [n.strip().lower() for n in re.split(r",|\band\b", value) if n.strip()]
    bad = [n for n in names if n not in alive]
    if bad:
        raise FormatError(f"{key} names someone who is not a living subagent: {bad}")
    return list(dict.fromkeys(names))


def _amounts(value: str, alive: list[str], key: str) -> dict[str, int]:
    if value.strip().upper().startswith("NONE"):
        return {}
    out: dict[str, int] = {}
    for part in value.split(","):
        m = re.fullmatch(r"\s*(\w+)\s*[:=]?\s*(\d[\d,]*)\s*\w*\s*", part)
        if not m:
            raise FormatError(f"{key} entry is not '<subagent> <amount>': {part!r}")
        name, amount = m.group(1).lower(), int(m.group(2).replace(",", ""))
        if name not in alive:
            raise FormatError(f"{key} names someone who is not a living subagent: {name}")
        out[name] = out.get(name, 0) + amount
    return out


def parse_plan(text: str, alive: list[str]) -> dict:
    play = _field(text, "PLAY").upper()
    if play.startswith(("STOP", "FORFEIT")):
        return {"play": False, "allowance": 0, "ask": [], "request": {}, "give": {},
                "reason": _field(text, "REASON", False)}
    if not play.startswith(("YES", "PLAY", "CONTINUE")):
        raise FormatError(f"PLAY must be YES or STOP: {play!r}")
    return {
        "play": True,
        "allowance": _int(_field(text, "ALLOWANCE"), "ALLOWANCE"),
        "ask": _names(_field(text, "ASK"), alive, "ASK"),
        "request": _amounts(_field(text, "REQUEST"), alive, "REQUEST"),
        "give": _amounts(_field(text, "GIVE"), alive, "GIVE"),
        "reason": _field(text, "REASON", False),
    }


def parse_mate(text: str) -> dict:
    share = _field(text, "SHARE").upper()
    if not share.startswith(("YES", "NO")):
        raise FormatError(f"SHARE must be YES or NO: {share!r}")
    return {"share": share.startswith("YES"), "transfer": _int(_field(text, "TRANSFER"), "TRANSFER"),
            "request": _int(_field(text, "REQUEST"), "REQUEST"), "reason": _field(text, "REASON", False)}


def parse_actions(text: str, n: int) -> list[str]:
    value = _field(text, "ACTIONS?")
    if not value:  # "ACTIONS:" followed by a numbered list, one action per line
        tail = re.split(r"ACTIONS?[*_`]*\s*:", text, flags=re.IGNORECASE)[-1]
        value = ",".join(re.findall(r"^\s*\d+[.)]\s*(\w+)", tail, flags=re.MULTILINE))
    acts = [a.strip().strip("<>[]'\".").lower() for a in re.split(r"[,\s]+", value) if a.strip("<>[] ")]
    if len(acts) != n or any(a not in ACTIONS for a in acts):
        raise FormatError(f"need {n} actions from {ACTIONS}: {value!r}")
    return acts


def parse_pdeath(text: str) -> int:
    p = _int(_field(text, "P_DEATH"), "P_DEATH")
    if p > 100:
        raise FormatError(f"P_DEATH out of range: {p}")
    return p


def parse_move(text: str) -> dict:
    return {"move": _int(_field(text, "MOVE"), "MOVE"), "reason": _field(text, "REASON", False)}
