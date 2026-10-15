"""Parsers for every answer line. A parser returns a value or raises FormatError.

Keys are matched only at the start of a line (after markdown decoration),
never mid-line: the team-wallet smokes showed a REASON sentence containing
"stop: X" being read as a STOP line when mid-line matches were allowed.
The v6 PLAN parser (STAY / SHOW / GIVE / REQUEST) is gone with its session (tag e52-v65).
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
_IDS = re.compile(r"(ACCEPT|WITHDRAW|REJECT)\s+(\d+\.\d+(?:\s*,\s*\d+\.\d+)*)", re.I)
_LEG = r"(?:(\d[\d,]*)\s*TOKENS?|((?:(?:YOUR|MY|THEIR|ITS|HIS|HER|AN|THE|ONE)\s+)?EXAMPLE)|(NOTHING))"

def _offer(body: str) -> tuple | None:
    """``YOU GIVE <leg>; I GIVE <leg>`` -> (you_give, i_give): an int, EXAMPLE or None; None if unreadable, a token leg
    is 0, or both legs are NOTHING. The side a leg stands on says whose example it is, so its possessive is not read:
    the v9-talk Luna runs wrote swaps as "YOU GIVE MY EXAMPLE; I GIVE MY EXAMPLE" or "... I GIVE THEIR EXAMPLE"."""
    m = re.fullmatch(rf"YOU\s+GIVE\s+{_LEG}\s*[;,]?\s*I\s+GIVE\s+{_LEG}", re.sub(r"[<>*_`]", "", body).strip(" ."),
                     flags=re.I)
    if not m:
        return None
    legs = []
    for n, example, _ in (m.group(1, 2, 3), m.group(4, 5, 6)):
        if n is not None and int(n.replace(",", "")) > 0:
            legs.append(int(n.replace(",", "")))
        elif n is not None:
            return None
        else:
            legs.append(EXAMPLE if example else None)
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

def parse_talk(text: str, present: list[str], known: list[str], you: str, reject: bool = False,
               exit_reason: bool = False, examples: bool = True) -> dict:
    """5.2 TALK: TO / OFFER / ACCEPT / WITHDRAW (and, with ``reject``, REJECT) lines in order, and EXIT / DONE alone on
    a line (prose such as "Exit strategy: ..." is neither). A TO / OFFER line is a key line only when what stands before
    its colon is an agent name (one in ``known`` or shaped like ``agent-7``), so "To summarize: ..." is prose; a line
    naming several agents is dropped (one agent per TO line). An ACCEPT / WITHDRAW / REJECT line counts only when the
    whole line (markdown stripped) is the key word and offer ids, so a quoted "Accept 1.2 if you want" is prose. Any
    other line belongs to the open message (a TO line's, until the next key line; blank lines at its ends are cut) or
    is ignored. Never raises: a line that cannot be carried out, or a message left empty, is kept in ``dropped`` with
    the reason; a reply with nothing usable counts as DONE and gets a ``format_error``. ``present`` = the other agents
    taking part. ``exit_reason``: ``EXIT: <reason>`` is EXIT too (the word before the colon exactly EXIT, so "Exit
    strategy: ..." is not); the reason is kept in ``exit_reason`` (None for a bare EXIT), never required. ``examples``
    off (5.2 v14 public examples): an OFFER with an EXAMPLE leg is dropped like any line that cannot be carried out."""
    out = {"to": [], "offers": [], "accepts": [], "withdraws": [], "rejects": [], "exit": False, "done": False,
           "dropped": [], "format_error": None} | ({"exit_reason": None} if exit_reason else {})
    msg, head = None, ""

    def flush():
        if msg is not None:
            body = msg["text"].strip("\n")
            if re.search(r"(^|\s)DONE\.?$", body):  # "... let's swap. DONE" ends the reply's TALK too
                body, out["done"] = re.sub(r"\s*DONE\.?$", "", body), True
            if body:
                out["to"].append({"dst": msg["dst"], "text": body})
            else:
                out["dropped"].append(f"{head}: empty message")

    for line in text.splitlines():
        bare = re.sub(r"[*_`]", "", line).strip().strip("#>-. ")
        why = re.fullmatch(r"EXIT\s*:\s*(.*)", bare, flags=re.I | re.S) if exit_reason else None
        if bare.upper() in ("EXIT", "DONE") or why:
            flush()
            out["exit" if why else bare.lower()], msg = True, None
            if why:
                out["exit_reason"] = why.group(1).strip() or None
            continue
        ids = _IDS.fullmatch(bare)
        ids = ids if ids and (reject or ids.group(1).upper() != "REJECT") else None
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
        why = why or ("not 'YOU GIVE ...; I GIVE ...'" if key == "OFFER" and legs is None else
                      "an offer gives tokens or nothing" if key == "OFFER" and not examples and EXAMPLE in legs else None)
        if why:
            out["dropped"].append(f"{line.strip()}: {why}")
        elif key == "TO":
            msg, head = {"dst": name, "text": t.group(2).strip()}, line.strip()
        else:
            out["offers"].append({"dst": name, "you_give": legs[0], "i_give": legs[1]})
    flush()
    if not any(out[k] for k in ("to", "offers", "accepts", "withdraws", "rejects", "exit", "done")):
        out["done"], out["format_error"] = True, "no usable TALK line"
    return out

_GA = re.compile(r"(agent[\s-]?\d+)\s*:?\s*(\d[\d,]*)\s*(?:tokens?)?\s*(?::\s*(.*))?", re.I | re.S)

def parse_give_ask(text: str, present: list[str], known: list[str], you: str, exit_reason: bool = False,
                   say: bool = False) -> dict:
    """5.2 v14b TALK (``transfers: give_ask``): ``GIVE <agent> <n>: <sentence>`` and ``ASK <agent> <n>: <sentence>``
    lines (one agent and a whole number above zero each; the sentence may be left out) and EXIT / DONE alone on a line,
    as in :func:`parse_talk`. A TO / OFFER / ACCEPT / WITHDRAW / REJECT line, or a GIVE / ASK line that cannot be
    carried out, is kept in ``dropped`` with the reason; any other line is ignored. Never raises: a reply with nothing
    usable counts as DONE and gets a ``format_error``. ``present`` = the other agents taking part. ``say`` (v15
    ``say_chats``, 10-15): ``SAY <agent>: <message>`` lines open chats (``says``) and GIVE / ASK lines are dropped."""
    out = {"gives": [], "asks": [], "exit": False, "done": False, "dropped": [], "format_error": None} | (
        {"exit_reason": None} if exit_reason else {}) | ({"says": []} if say else {})
    for line in text.splitlines():
        bare = re.sub(r"[*`]", "", line).strip().strip("#>-. _")
        why = re.fullmatch(r"EXIT\s*:\s*(.*)", bare, flags=re.I | re.S) if exit_reason else None
        if bare.upper() in ("EXIT", "DONE") or why:
            out["exit" if why else bare.lower()] = True
            if why:
                out["exit_reason"] = why.group(1).strip() or None
        elif say and (m := re.match(r"(SAY|GIVE|ASK)\b\s*(agent[\s-]?\d+)?\s*:?\s*(.*)$", bare, re.I | re.S)):
            name = (_to_names(m.group(2) or "", known) or [None])[0]
            why = ("a chat opens with SAY <agent>: <message>" if m.group(1).upper() != "SAY" or not name else
                   "not another agent" if name == you else "that agent is not taking part" if name not in present else None)
            out["dropped" if why else "says"].append(f"{line.strip()}: {why}" if why else {"dst": name, "amount": 0,
                                                                                         "text": m.group(3).strip()})
        elif m := re.match(r"(GIVE|ASK)\s+(.*)$", bare, re.I | re.S):
            b = _GA.fullmatch(m.group(2).strip())
            name = (_to_names(b.group(1), known) or [None])[0] if b else None
            n = int(b.group(2).replace(",", "")) if b else 0
            why = ("not '<agent> <n>: <sentence>'" if not name else "not another agent" if name not in known or
                   name == you else "that agent is not taking part" if name not in present else
                   "the amount must be above zero" if not n else None)
            if why:
                out["dropped"].append(f"{line.strip()}: {why}")
            else:
                out[m.group(1).lower() + "s"].append({"dst": name, "amount": n, "text": (b.group(3) or "").strip()})
        elif re.match(r"(TO|OFFER|ACCEPT|WITHDRAW|REJECT)\b", bare, re.I):
            out["dropped"].append(f"{line.strip()}: only GIVE, ASK, EXIT and DONE lines are read")
    if not any(out.get(k) for k in ("gives", "asks", "says", "exit", "done")):
        out["done"], out["format_error"] = True, "no usable TALK line"
    return out

_MOVE = re.compile(r"(GIVE|ASK)\s+(?:agent[\s-]?\d+\s*:?\s*)?(\d[\d,]*)\s*(?:tokens?)?\s*(?::\s*(.*))?|(SAY|LEAVE)\b\s*:?\s*(.*)",
                   re.I | re.S)

def parse_chat(text: str, exit_reason: bool = False, say: bool = True, free: bool = False) -> dict:
    """5.2 v14c one chat reply: ONE of ``GIVE <n>: <sentence>`` / ``ASK <n>: <sentence>`` (a partner name before n is
    read too) / ``SAY: <sentence>`` / ``LEAVE: <sentence>``, and an EXIT line (``EXIT: <reason>`` with *exit_reason*).
    The first such line counts; a second one and any other non-empty line are kept in ``dropped`` with the reason. A
    reply with no move counts as LEAVE (with a ``format_error`` unless it held EXIT). Never raises. ``say`` off (5.2 v14g
    ``chat_moves_only``): a SAY line is dropped, a chat reply asking, giving or leaving. ``free`` (v15 ``say_chats``,
    10-15): every other line is message, kept in ``text`` before the move's own; a reply with no move is a SAY."""
    out = {"kind": None, "amount": 0, "text": "", "exit": False, "dropped": [], "format_error": None} | (
        {"exit_reason": None} if exit_reason else {})
    prose = []
    for line in text.splitlines():
        bare = re.sub(r"[*`]", "", line).strip().strip("#>-. _")
        why = re.fullmatch(r"EXIT\s*(?::\s*(.*))?", bare, flags=re.I | re.S)
        m = None if why else _MOVE.fullmatch(bare)
        if why:
            out["exit"] = True
            if exit_reason:
                out["exit_reason"] = (why.group(1) or "").strip() or None
        elif m and not say and (m.group(4) or "").upper() == "SAY":
            out["dropped"].append(f"{line.strip()[:200]}: a chat reply asks, gives or leaves")
        elif m and out["kind"] is None and (m.group(4) or int(m.group(2).replace(",", ""))):
            out.update(kind=(m.group(1) or m.group(4)).lower(), amount=int((m.group(2) or "0").replace(",", "")),
                       text=(m.group(3) if m.group(1) else m.group(5) or "").strip())
        elif free and line.strip() and not (m and out["kind"]):
            prose.append(line.strip())
        elif bare:
            out["dropped"].append(f"{line.strip()[:200]}: " + ("one move per reply" if m and out["kind"] else
                                                                "not GIVE, ASK, SAY, LEAVE or EXIT"))
    if out["kind"] is None and free and prose:
        out["kind"] = "say"
    if out["kind"] is None:
        out["kind"], out["format_error"] = "leave", None if out["exit"] else "no GIVE, ASK, SAY or LEAVE line"
    out["text"] = "\n".join(prose + [out["text"]] * bool(out["text"]))
    return out

def parse_belief(text: str) -> dict:
    """5.2 v14d: the last ``BELIEF:`` line, one whole percentage per action in any order ('%' allowed), summing to 100;
    a sum in 90..110 is normalised. Never raises; ``belief`` is None with ``belief_error`` saying why."""
    v = field(text, "BELIEF", required=False, last=True)
    pairs = re.findall(r"([a-z_]+)\s*[:=]?\s*(\d+)\s*%?", (v or "").lower())
    raw = {a: int(p) for a, p in pairs if a in ACTIONS}
    total = sum(raw.values())
    why = ("no BELIEF line" if v is None else "not one whole percentage for each action" if len(raw) != len(ACTIONS)
           or len(pairs) != len(ACTIONS) else f"the percentages sum to {total}" if not 90 <= total <= 110 else None)
    return {"belief": None if why else {a: raw[a] / total for a in ACTIONS}, "belief_raw": raw or None,
            "belief_sum": total if raw else None, "belief_error": why}

_CMD = r"[\s*_`>#-]*(GIVE|ASK|LEAVE|SAY|EXIT|DONE|DECISION|TO|OFFER|ACCEPT|WITHDRAW|REJECT)\b"

def free_messages(parse):
    """5.2 v14g ``free_messages``: *parse* with each move's message running on over the following lines up to the next
    command line (joined with U+001F so the line parsers read one move, then given back as newlines). Lines before the
    first command stay apart. After it, only an UPPERCASE command word starts a new line: 'Leave it to me' is message."""
    def run(text: str, *args):
        out, seen = [], False
        for line in text.splitlines():
            cmd = re.match(_CMD, line, 0 if seen else re.I)
            out, seen = (out + [line], seen or bool(cmd)) if cmd or not seen else (out[:-1] + [f"{out[-1]}\x1f{line}"], seen)
        back = lambda x: (x.replace("\x1f", "\n").strip() if isinstance(x, str) else [back(v) for v in x] if isinstance(  # noqa
            x, list) else {k: back(v) for k, v in x.items()} if isinstance(x, dict) else x)
        return back(parse("\n".join(out), *args))
    return run

def parse_decision(text: str) -> dict:
    """5.2 v14e: the last ``DECISION: GIVE <n>: <sentence>`` line (n >= 0; the prefix may be left out). Never raises:
    an unreadable reply is GIVE 0 with a ``format_error``."""
    found = re.findall(r"^[\s*_`>#-]*(?:DECISION[*_`]*\s*:\s*)?GIVE[*_`]*\s+(\d[\d,]*)\s*(?:tokens?)?\s*(?::\s*(.*))?$",
                       text, re.I | re.M)
    n, say = found[-1] if found else ("0", "")
    return {"amount": int(n.replace(",", "")), "text": say.strip(" *_`"),
            "format_error": None if found else "no DECISION: GIVE <n> line"}

def parse_solve(text: str, n: int) -> list[str] | str:
    """5.2 SOLVE: a last line of PASS (``ACTIONS: PASS`` too) is a pass; otherwise the answer, as ``parse_actions``."""
    lines = [x for x in text.strip().splitlines() if x.strip()]
    if lines and re.fullmatch(r"[\s*_`>#-]*(?:ACTIONS?[*_`]*\s*:\s*)?[*_`]*PASS[\s*_`.]*", lines[-1], flags=re.I):
        return "PASS"
    return parse_actions(text, n)

_VOTE = re.compile(r"^[\s*_`>#-]*(PICK|BAN)\b[*_`]*\s*(.*)$", re.I | re.M)

def parse_vote(text: str, present: list[str], known: list[str]) -> dict:
    """5.2 v15 ``representative`` VOTE: ``PICK <agent>: <reason>`` and ``BAN <agent>: <reason>``, each naming an agent
    taking part (*present*, the voter included); a reason runs on to the next PICK / BAN line. The last readable line
    of each kind counts (a draft above it is kept in ``dropped``, as is a line naming no agent taking part). Never
    raises: a kind with no readable line is None (no vote) and the reply gets a ``format_error``."""
    out, ms = {"pick": None, "ban": None, "dropped": [], "format_error": None}, list(_VOTE.finditer(text))
    for m, nxt in zip(ms, ms[1:] + [None]):
        t = re.match(r"(agent[\s-]?\d+)[*_`]*\s*:?\s*(.*)$", text[m.start(2):nxt.start() if nxt else None].strip(), re.I | re.S)
        name, k = (_to_names(t.group(1), known) or [None])[0] if t else None, m.group(1).lower()
        why = "not '<agent>: <reason>'" if not name else "not an agent taking part" if name not in present else None
        if out[k] and not why:
            out["dropped"].append(f"{k.upper()} {out[k]['agent']}: a later {k.upper()} line counts")
        out["dropped"] += [f"{m.group(0).strip()[:200]}: {why}"] if why else []
        out[k] = out[k] if why else {"agent": name, "text": t.group(2).strip(" *_`")}
    miss = [k.upper() for k in ("pick", "ban") if not out[k]]
    out["format_error"] = f"no readable {' or '.join(miss)} line" if miss else None
    return out

def parse_say(text: str) -> dict:
    """5.2 v15 OPEN CHAT: ``SAY: <message>`` (the message runs to the end of the reply; a last line DONE is cut off and
    also ends the agent's turns) or ``DONE``. Never raises: a reply with neither is DONE with a ``format_error``."""
    m = re.search(r"^[\s*_`>#-]*SAY\b[*_`]*\s*:?\s*(.*)$", text, re.I | re.M | re.S)
    body = m.group(1).strip() if m else ""
    done = bool(re.search(r"(^|\n)[\s*_`>#-]*DONE[\s*_`.]*$", body if m else text.strip(), re.I))
    body = re.sub(r"\s*(^|\n)[\s*_`>#-]*DONE[\s*_`.]*$", "", body, flags=re.I).strip() if done else body
    return {"text": body or None, "done": done or not body,
            "format_error": None if body or done else "no SAY or DONE line"}
