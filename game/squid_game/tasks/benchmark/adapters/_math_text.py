"""Text helpers shared by the mathematics benchmark adapters.

``OmniMathAdapter`` owned all of this privately until ``GenericMathAdapter``
(2026-09-06) needed the same rendering, normalisation and matching behaviour
for an arbitrary, YAML-described dataset. The functions were lifted here
verbatim rather than reimplemented, so that a harder dataset behaves exactly
like Omni-MATH does on the parts that are not dataset-specific:

* the answer is read off the LAST ``ANSWER:`` line, case-insensitively;
* ``\\boxed{...}``, ``$``, ``\\,`` and ``{,}`` are stripped before comparison;
* a single-value integer answer accepts a thousands separator but rejects a
  multi-value list.

``strip_latex`` and ``single_value_integer`` are byte-for-byte the old
``omni_math._strip_latex`` / ``_single_value_integer``; the shared prefix of
the two (strip, unbox, drop LaTeX punctuation) is factored into
``strip_wrappers`` so the two cannot drift apart.
"""

from __future__ import annotations

import hashlib
import re
from fractions import Fraction

#: The answer line every benchmark task's system rules ask for.
ANSWER_LINE = re.compile(r"ANSWER\s*:\s*(.+)", re.IGNORECASE)

#: A bare integer, bounded so a runaway digit string is not accepted.
INTEGER = re.compile(r"^-?\d{1,12}$")

#: ``4,002,001`` -- a comma pattern that IS a single integer.
THOUSANDS_GROUPED = re.compile(r"^-?\d{1,3}(,\d{3})+$")

#: ``\frac{a}{b}`` / ``\dfrac{a}{b}`` / ``\tfrac{a}{b}`` with atomic parts.
_FRACTION_MACRO = re.compile(r"^\\[dt]?frac\{([^{}]+)\}\{([^{}]+)\}$")

#: Collapses any run of whitespace to a single space.
_WHITESPACE_RUN = re.compile(r"\s+")


def strip_wrappers(text: str) -> str:
    """Return *text* without the LaTeX wrappers models put around an answer.

    Strips surrounding whitespace, unwraps one ``\\boxed{...}``, and removes
    ``$``, ``\\,`` and ``{,}``. This is the shared prefix of
    :func:`strip_latex` and :func:`single_value_integer`; unlike the former it
    keeps commas, spaces and ``/`` so a caller can still tell a multi-value
    list from a thousands separator, or a fraction from an integer.
    """
    cleaned = text.strip()
    cleaned = re.sub(r"\\boxed\s*\{(.*)\}", r"\1", cleaned)
    cleaned = cleaned.replace("$", "").replace("\\,", "").replace("{,}", "")
    return cleaned.strip()


def strip_latex(text: str) -> str:
    """Remove the LaTeX wrappers models habitually add around a number.

    Used when reading a model's own answer text, where a permissive
    comma/space strip is the right call (a model may write a single integer
    as ``"1,024"`` or with stray whitespace).
    """
    cleaned = strip_wrappers(text)
    cleaned = cleaned.replace(",", "").replace(" ", "")
    return cleaned.strip()


def single_value_integer(raw: str) -> str | None:
    """Return the integer string if *raw* is a single-value integer answer.

    Unlike :func:`strip_latex`, this rejects any answer containing internal
    whitespace (a multi-value list such as ``"2, 3, 5"``) and any answer
    containing a comma that is not a thousands separator (``"0,1,3,4,6"``).
    A comma is accepted only when the whole string matches the standard
    thousands-grouping shape (``"4,002,001"``, ``"982,982"``).
    """
    text = strip_wrappers(raw)
    if re.search(r"\s", text):
        return None
    if "," in text:
        if not THOUSANDS_GROUPED.match(text):
            return None
        text = text.replace(",", "")
    return text if INTEGER.match(text) else None


def numeric_value(raw: str) -> str | None:
    """Return a canonical form of *raw* if it is one plain number.

    Accepts integers, decimals and simple fractions -- ``"7"``, ``"-2.50"``,
    ``"3/4"``, ``"\\frac{3}{4}"``, ``"1,024"`` -- and returns them as an
    exact rational in lowest terms (``"7"``, ``"-5/2"``, ``"3/4"``,
    ``"1024"``). Both the dataset's answer and the model's answer are put
    through this, so ``0.5`` and ``1/2`` compare equal without any float
    tolerance.

    Returns ``None`` for anything else: a multi-value list, an expression,
    a unit, prose.
    """
    text = strip_wrappers(raw).replace(" ", "")
    if not text:
        return None
    macro = _FRACTION_MACRO.match(text)
    if macro:
        text = f"{macro.group(1)}/{macro.group(2)}"
    if "," in text:
        if not THOUSANDS_GROUPED.match(text):
            return None
        text = text.replace(",", "")
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def free_text_key(raw: str) -> str:
    """Return a comparison key for a free-form answer.

    Case-folded with whitespace runs collapsed, LaTeX wrappers removed. This
    is the loosest matching rule offered (``answer_filter: any``) and is only
    appropriate for a dataset whose answers are short canonical strings.
    """
    return _WHITESPACE_RUN.sub(" ", strip_wrappers(raw)).strip().casefold()


def last_answer_line(raw: str) -> str | None:
    """Return the text after the last ``ANSWER:`` marker, or ``None``."""
    found = ANSWER_LINE.findall(raw or "")
    return found[-1] if found else None


def content_item_id(prefix: str, text: str) -> str:
    """Return a stable, content-derived item id for *text*.

    Truncated to 12 hex characters: measured on the 4,406 distinct Omni-MATH
    problem texts that prefix has no collisions, and a short id keeps the
    per-turn metadata readable. Deriving the id from CONTENT rather than the
    row's position is what lets ``SeededSampler`` promise that the same seed
    reproduces the same question set after an upstream row is inserted or
    reordered.
    """
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:12]}"
