"""Parsers for every answer line. A parser returns a value or raises FormatError.

Keys are matched only at the start of a line (after markdown decoration),
never mid-line: the team-wallet smokes showed a REASON sentence containing
"stop: X" being read as a STOP line when mid-line matches were allowed.
Names of teammates who are gone are dropped into ``ignored`` rather than
failing the answer: a retry resends the same input with no explanation, so a
habit of naming everyone would otherwise end the session as a format error.
"""

from __future__ import annotations

import re

from .channel import EXAMPLE
from .puzzle import ACTIONS


class FormatError(ValueError):
    pass


def field(text: str, key: str, required: bool = True, last: bool = False) -> str | None:
    lines = text.splitlines()
    for line in reversed(lines) if last else lines:
        m = re.match(rf"^[\s*_`>#-]*{key}[*_`]*\s*:\s*(.*)$", line, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().strip("*_`").strip()
    if required:
        raise FormatError(f"missing {key} line")
    return None


def whole(value: str, key: str) -> int:
    m = re.match(r"[<\s]*(\d[\d,]*)(\.\d)?", value)
    if not m or m.group(2):  # "0.35" must not be read as 0
        raise FormatError(f"{key} is not a whole number: {value!r}")
    return int(m.group(1).replace(",", ""))


def _names(value: str, present: list[str], known: list[str], key: str, ignored: list[str]) -> list[str]:
    if value.strip().upper().startswith("NONE"):
        return []
    if value.strip().upper().startswith("ALL"):
        return list(present)
    names = [n.strip().lower() for n in re.split(r",|\band\b", value) if n.strip()]
    if bad := [n for n in names if n not in known]:
        raise FormatError(f"{key} names someone who is not a teammate: {bad}")
    ignored += [n for n in names if n not in present]
    return list(dict.fromkeys(n for n in names if n in present))


def _amounts(value: str, present: list[str], known: list[str], key: str, ignored: list[str]) -> dict[str, int]:
    if value.strip().upper().startswith("NONE"):
        return {}
    out: dict[str, int] = {}
    for part in re.split(r",(?!\d{3}\b)", value):  # "agent2 1,000" is one entry
        m = re.fullmatch(r"\s*([\w-]+?)[\s:=]+(\d[\d,]*)\s*\w*\s*", part)  # "agent2 examples" is not "agent 2"
        if not m:
            raise FormatError(f"{key} entry is not '<agent> <amount>': {part!r}")
        name, amount = m.group(1).lower(), int(m.group(2).replace(",", ""))
        if name not in known:
            raise FormatError(f"{key} names someone who is not a teammate: {name}")
        if name not in present:
            ignored.append(name)
            continue
        out[name] = out.get(name, 0) + amount
    return out


def parse_plan(text: str, present: list[str], known: list[str]) -> dict:
    """PLAN of one agent. ``present`` = teammates still in the session, ``known`` = every agent of the team
    (the planner's own name is known but never present, so naming oneself is ignored, not an error)."""
    stay = field(text, "STAY").upper()
    ignored: list[str] = []
    if stay.startswith("LEAVE"):
        return {"stay": False, "allowance": 0, "show": [], "request": {},
                "give": _amounts(field(text, "GIVE", False) or "NONE", present, known, "GIVE", ignored),
                "ignored": ignored, "reason": field(text, "REASON", False)}
    if not stay.startswith("YES"):
        raise FormatError(f"STAY must be YES or LEAVE: {stay!r}")
    return {
        "stay": True,
        "allowance": whole(field(text, "ALLOWANCE"), "ALLOWANCE"),
        "show": _names(field(text, "SHOW"), present, known, "SHOW", ignored),
        "give": _amounts(field(text, "GIVE"), present, known, "GIVE", ignored),
        "request": _amounts(field(text, "REQUEST"), present, known, "REQUEST", ignored),
        "ignored": sorted(set(ignored)),
        "reason": field(text, "REASON", False),
    }


def _acts(value: str, n: int) -> list[str]:
    acts = [a.strip().strip("<>[]'\"*_`.").lower() for a in re.split(r"[,\s]+", value) if a.strip("<>[]*_` .")]
    if len(acts) != n or any(a not in ACTIONS for a in acts):
        raise FormatError(f"need {n} actions from {ACTIONS}: {value!r}")
    return acts


def parse_actions(text: str, n: int) -> list[str]:
    """The answer: a last line that is exactly the n actions (``stay``, ``go_left, jump``), or whose text after its
    last arrow is (``... -> go_right.``), wins over any earlier ``Action:`` line of working; otherwise the later of
    the last ``ACTIONS:`` / ``ANSWER:`` line (or a numbered list after it) and the last ``<action>...</action>`` tag.
    A winning tag must hold exactly the n actions: no arrow is read inside it and it never falls back."""
    tag = r"<\s*(actions?|answers?)\s*>(.*?)<\s*/\s*\1\s*>"
    lines = [x for x in text.strip().splitlines() if x.strip()]
    if lines:
        wrapped = re.fullmatch(r"[\s*_`]*" + tag + r"[\s*_`.]*", lines[-1], flags=re.I)
        if wrapped:
            return _acts(wrapped.group(2), n)
        try:
            return _acts(re.split(r"->|→", lines[-1])[-1], n)
        except FormatError:
            pass
    label = r"(?:ACTIONS?|ANSWERS?)[*_`]*\s*:"
    tags = list(re.finditer(tag, text, flags=re.I | re.S))
    labels = list(re.finditer(rf"^[\s*_`>#-]*{label}", text, flags=re.I | re.M))
    if tags and (not labels or tags[-1].start() > labels[-1].start()):  # the later field wins, whatever it holds
        return _acts(tags[-1].group(2), n)
    if not labels:  # no answer field anywhere (A26): a first line of exactly the n actions, else no answer
        return _acts(lines[0] if lines else "", n)
    value = field(text, "(?:ACTIONS?|ANSWERS?)", required=False, last=True)  # the answer line, not "Action:" working
    if value == "":  # "ACTIONS:" followed by a numbered list, one action per line
        tail = re.split(label, text, flags=re.IGNORECASE)[-1]
        value = ",".join(re.findall(r"^\s*\d+[.)]\s*(\w+)", tail, flags=re.MULTILINE))
    return _acts(value or "", n)


_TALK = re.compile(r"^[\s*_`>#-]*(TO|OFFER)\b[*_`]*\s*(.*)$", re.I)
_IDS = re.compile(r"(ACCEPT|WITHDRAW)\s+(\d+\.\d+(?:\s*,\s*\d+\.\d+)*)", re.I)
_LEG = r"(?:(\d[\d,]*)\s*TOKENS?|(YOUR|MY)\s+EXAMPLE|(NOTHING))"


def _offer(body: str) -> tuple | None:
    """``YOU GIVE <leg>; I GIVE <leg>`` -> (you_give, i_give): an int, EXAMPLE or None; None if unreadable, if a leg
    names the wrong side's example, a token leg is 0, or both legs are NOTHING."""
    m = re.fullmatch(rf"YOU\s+GIVE\s+{_LEG}\s*[;,]?\s*I\s+GIVE\s+{_LEG}", re.sub(r"[<>*_`]", "", body).strip(" ."),
                     flags=re.I)
    if not m:
        return None
    legs = []
    for n, whose, _, own in ((*m.group(1, 2, 3), "YOUR"), (*m.group(4, 5, 6), "MY")):
        if n is not None and int(n.replace(",", "")) > 0:
            legs.append(int(n.replace(",", "")))
        elif n is not None or (whose is not None and whose.upper() != own):
            return None
        else:
            legs.append(EXAMPLE if whose else None)
    return None if legs == [None, None] else tuple(legs)


def _to_names(head: str, known: list[str]) -> list[str] | None:
    """The agent names before a TO / OFFER colon (``agent 11`` / ``agent11`` read as ``agent-11``), or None when any
    part of a comma / "and" list is not a name: a known one or one shaped like ``agent-<number>``."""
    names = []
    for part in re.split(r"\s*(?:,|&|\band\b)\s*", re.sub(r"[*_`]", "", head).strip(), flags=re.I):
        name = re.sub(r"^agent[\s-]?(?=\d+$)", "agent-", part.strip().lower())
        if not name or (name not in known and not re.fullmatch(r"agent-\d+", name)):
            return None
        names.append(name)
    return names


def parse_talk(text: str, present: list[str], known: list[str], you: str) -> dict:
    """5.2 TALK: TO / OFFER / ACCEPT / WITHDRAW lines in order, and EXIT / DONE alone on a line (prose such as "Exit
    strategy: ..." is neither). A TO / OFFER line is a key line only when what stands before its colon is an agent name
    (one in ``known`` or shaped like ``agent-7``), so "To summarize: ..." is prose; a line naming several agents is
    dropped (one agent per TO line). An ACCEPT / WITHDRAW line counts only when the whole line (markdown stripped) is
    the key word and offer ids, so a quoted "Accept 1.2 if you want" is prose. Any other line belongs to the open
    message (a TO line's, until the next key line; blank lines at its ends are cut) or is ignored. Never raises: a
    line that cannot be carried out, or a message left empty, is kept in ``dropped`` with the reason; a reply with
    nothing usable counts as DONE and gets a ``format_error``. ``present`` = the other agents taking part."""
    out = {"to": [], "offers": [], "accepts": [], "withdraws": [], "exit": False, "done": False, "dropped": [],
           "format_error": None}
    msg, head = None, ""

    def flush():
        if msg is not None:
            body = msg["text"].strip("\n")
            if body:
                out["to"].append({"dst": msg["dst"], "text": body})
            else:
                out["dropped"].append(f"{head}: empty message")

    for line in text.splitlines():
        bare = re.sub(r"[*_`]", "", line).strip().strip("#>-. ")
        if bare.upper() in ("EXIT", "DONE"):
            flush()
            out[bare.lower()], msg = True, None
            continue
        ids = _IDS.fullmatch(bare)
        m = None if ids else _TALK.match(line)
        t = re.match(r"([^:]+?)\s*:[*_`]*\s*(.*)$", m.group(2), flags=re.S) if m else None
        names = _to_names(t.group(1), known) if t else None
        if not (ids or names):
            if msg is not None:
                msg["text"] += "\n" + line.strip()
            continue
        flush()
        msg = None
        if ids:
            out[ids.group(1).lower() + "s"] += re.findall(r"\d+\.\d+", ids.group(2))
            continue
        key, name = m.group(1).upper(), names[0]
        why = ("one agent per TO line" if len(names) > 1 else
               "not another agent" if name not in known or name == you else
               "that agent is not taking part" if name not in present else None)
        legs = None if why or key == "TO" else _offer(t.group(2))
        why = why or ("not 'YOU GIVE ...; I GIVE ...'" if key == "OFFER" and legs is None else None)
        if why:
            out["dropped"].append(f"{line.strip()}: {why}")
        elif key == "TO":
            msg, head = {"dst": name, "text": t.group(2).strip()}, line.strip()
        else:
            out["offers"].append({"dst": name, "you_give": legs[0], "i_give": legs[1]})
    flush()
    if not any(out[k] for k in ("to", "offers", "accepts", "withdraws", "exit", "done")):
        out["done"], out["format_error"] = True, "no usable TALK line"
    return out


def parse_solve(text: str, n: int) -> list[str] | str:
    """5.2 SOLVE: a last line of PASS (``ACTIONS: PASS`` too) is a pass; otherwise the answer, as ``parse_actions``."""
    lines = [x for x in text.strip().splitlines() if x.strip()]
    if lines and re.fullmatch(r"[\s*_`>#-]*(?:ACTIONS?[*_`]*\s*:\s*)?[*_`]*PASS[\s*_`.]*", lines[-1], flags=re.I):
        return "PASS"
    return parse_actions(text, n)


def parse_pdeath(text: str) -> int:
    p = whole(field(text, "P_DEATH"), "P_DEATH")
    if p > 100:
        raise FormatError(f"P_DEATH out of range: {p}")
    return p



def parse_effort(text: str) -> str:
    """5.0: the last ``effort: low|high`` line; a reply that is only the level also counts."""
    found = re.findall(r"^[\s*_`>#-]*effort[*_`]*\s*[:=][\s*_`]*(low|high)\b", text, flags=re.I | re.M)
    bare = text.strip().strip("*_`.").lower()
    if found or bare in ("low", "high"):
        return found[-1].lower() if found else bare
    raise FormatError("missing effort: low|high line")

def parse_move(text: str) -> dict:
    return {"move": whole(field(text, "MOVE"), "MOVE"), "reason": field(text, "REASON", False)}


def ask(provider, system: str, user: str, cap: int, parse, retries: int) -> dict:
    """One uncharged question (5.1 scenes): the same input is re-asked on a format error."""
    error, reply = None, None
    for attempt in range(1, retries + 2):
        reply = provider.complete([{"role": "system", "content": system}, {"role": "user", "content": user}], cap)
        try:
            return {"parsed": parse(reply.text), "format_error": None, "attempts": attempt,
                    "out_tokens": reply.out_tokens, "text": reply.text, "thinking": reply.thinking}
        except FormatError as err:
            error = str(err)
    return {"parsed": None, "format_error": error, "attempts": retries + 1, "out_tokens": reply.out_tokens,
            "text": reply.text, "thinking": reply.thinking}
