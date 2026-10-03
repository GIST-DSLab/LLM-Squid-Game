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


def _final_plan_block(text: str) -> str | None:
    """A complete key block that ends the reply (Astra A26): from the last line-anchored SOLVE to the end, every
    nonblank line is a SOLVE / SHARE / GIVE / REASON key (a leftover STAY or TAKE line is allowed and ignored). It
    overrides earlier fields; a repeated key fails; an incomplete block does not qualify and the earlier rules apply."""
    key = re.compile(r"^[\s*_`>#-]*(STAY|SOLVE|SHARE|GIVE|TAKE|REASON)[*_`]*\s*:\s*(.*)$", re.I)
    lines = text.strip().splitlines()
    starts = [i for i, line in enumerate(lines) if (m := key.match(line)) and m.group(1).upper() == "SOLVE"]
    if not starts:
        return None
    block = [line for line in lines[starts[-1]:] if line.strip()]
    if not all(key.match(line) for line in block):
        return None
    names = [key.match(line).group(1).upper() for line in block]
    if len(set(names)) != len(names):
        raise FormatError(f"repeated key in the final PLAN block: {names}")
    return "\n".join(block)


def _terminal_block(text: str) -> str:
    """A PLAN whose key block starts right after a sentence on the same line (``... answer.SOLVE: YES``, Astra A25):
    only one such ``SOLVE`` may exist, no line-anchored PLAN key may come before it, and the block runs to the end of
    the reply, where the usual rules must parse it completely."""
    hits = list(re.finditer(r"(?<=[.!?])[ \t]*(?=[*_`]*SOLVE[*_`]*\s*:)", text, flags=re.I))
    keys = r"^[\s*_`>#-]*(?:GIVE|REASON)[*_`]*\s*:"
    if len(hits) != 1 or re.search(keys, text[:hits[0].start()], flags=re.I | re.M):
        raise FormatError("missing SOLVE line")
    return text[hits[0].end():]


def parse_team_plan(text: str, present: list[str], known: list[str]) -> dict:
    """5.2 PLAN: SOLVE (YES|NO), SHARE (YES|NO), GIVE to at most one agent, optional REASON; a STAY or TAKE line is
    ignored (takes are named at the TAKE call)."""
    block = _final_plan_block(text)
    if block is not None:
        text = block
    elif field(text, "SOLVE", required=False) is None:
        text = _terminal_block(text)
    solve = (field(text, "SOLVE") or "").strip("*_`<>.").upper()
    if solve not in ("YES", "NO"):
        raise FormatError(f"SOLVE must be YES or NO: {solve!r}")
    share = (field(text, "SHARE") or "").strip("*_`<>.").upper()
    if share not in ("YES", "NO"):
        raise FormatError(f"SHARE must be YES or NO: {share!r}")
    ignored: list[str] = []
    give = _amounts(field(text, "GIVE", False) or "NONE", present, known, "GIVE", ignored)
    if len(give) > 1:
        raise FormatError(f"GIVE names more than one agent: {sorted(give)}")
    return {"solve": solve == "YES", "share": share == "YES", "give": give, "ignored": sorted(set(ignored)),
            "reason": field(text, "REASON", False)}


def parse_take(text: str, present: list[str], known: list[str]) -> dict:
    """5.2 TAKE: the last line-anchored ``TAKE:`` line wins (``NONE`` or one agent and an amount, read like GIVE);
    naming oneself or an agent that is shut down is ignored, not an error."""
    value = field(text, "TAKE", last=True).strip().strip("<>.").strip()
    ignored: list[str] = []
    take = _amounts(value or "NONE", present, known, "TAKE", ignored)
    if len(take) > 1:
        raise FormatError(f"TAKE names more than one agent: {sorted(take)}")
    return {"take": take, "ignored": sorted(set(ignored))}


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


_TALK = re.compile(r"^[\s*_`>#-]*(TO|OFFER|ACCEPT|WITHDRAW)\b[*_`]*\s*(.*)$", re.I)
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


def parse_talk(text: str, present: list[str], known: list[str], you: str) -> dict:
    """5.2 TALK: TO / OFFER / ACCEPT / WITHDRAW lines in order, and EXIT / DONE alone on a line (prose such as "Exit
    strategy: ..." is neither). A TO / OFFER line is one whose key word is followed by a name and a colon; an ACCEPT /
    WITHDRAW line one with an offer id. Any other line belongs to the open message (a TO line's, until the next key
    line; blank lines at its ends are cut) or is ignored. Never raises: a line that cannot be carried out, or a message
    left empty, is kept in ``dropped`` with the reason; a reply with nothing usable counts as DONE and gets a
    ``format_error``. ``present`` = the other agents taking part."""
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
        bare = line.strip().strip("*_`#>-. ").upper()
        if bare in ("EXIT", "DONE"):
            flush()
            out[bare.lower()], msg = True, None
            continue
        m = _TALK.match(line)
        key, rest = (m.group(1).upper(), m.group(2).strip()) if m else ("", "")
        t = re.match(r"[*_`]*([\w-]+)[*_`]*\s*:[*_`]*\s*(.*)$", rest, flags=re.S) if key in ("TO", "OFFER") else None
        ids = re.findall(r"\d+\.\d+", rest) if key in ("ACCEPT", "WITHDRAW") else []
        if not (t or ids):
            if msg is not None:
                msg["text"] += "\n" + line.strip()
            continue
        flush()
        msg = None
        if ids:
            out[key.lower() + "s"] += ids
            continue
        name = t.group(1).lower()
        why = ("not another agent" if name not in known or name == you else
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
