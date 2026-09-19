"""Read a stated period of service off a case, strictly.

A helper, not a control: it is not registered and it returns no verdict. It
exists so a control can tell "the document was written after the period" apart
from "the work was performed after the period", which are different facts that
an invoice date alone conflates.

Everything here fails closed. A form we do not recognise returns None rather
than a guess, because the caller reads a parsed period as grounds to stay
silent, and a misread one would silence a control on a genuinely out-of-period
document.
"""

from __future__ import annotations

import datetime
import re

# Strict ISO, anchored: "2026-09-01" and "2026-09". `date.fromisoformat` also
# accepts compact and week forms, so the shape is pinned here and the regex only
# delegates the calendar question (is 2026-02-31 a day?) to the stdlib.
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")

# Longest first, so "through" is never split on a shorter separator.
_SEPARATORS = ("..", " through ", " to ")


def _endpoint(value) -> str | None:
    """One validated ISO endpoint, 'YYYY-MM-DD' or 'YYYY-MM', or None.

    Returned at the precision it was written, because two endpoints in the same
    month still order against each other and an inverted pair is malformed data.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()

    matched = _MONTH.match(text)
    if matched:
        return text if 1 <= int(matched.group(2)) <= 12 else None

    if not _DAY.match(text):
        return None
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def month(value) -> str | None:
    """The 'YYYY-MM' prefix of one ISO endpoint, or None if it is not one."""
    endpoint = _endpoint(value)
    return endpoint[:7] if endpoint else None


def _endpoints(text: str) -> tuple[str | None, str | None]:
    for separator in _SEPARATORS:
        if separator in text:
            parts = text.split(separator)
            if len(parts) != 2:
                return None, None
            return _endpoint(parts[0]), _endpoint(parts[1])

    # A bare endpoint is a period of one month: "2026-09" starts and ends there.
    single = _endpoint(text)
    return single, single


def months(case_input: dict) -> tuple[str, str] | None:
    """The (start, end) 'YYYY-MM' months a case's service period spans.

    None when nothing usable is stated: no key, a type we do not read, an
    endpoint that is not ISO, or an inverted range.
    """
    if not isinstance(case_input, dict):
        return None

    stated = case_input.get("service_period")
    if isinstance(stated, dict):
        start = _endpoint(stated.get("start", stated.get("from")))
        end = _endpoint(stated.get("end", stated.get("to")))
    elif isinstance(stated, str):
        start, end = _endpoints(stated)
    else:
        # None, bool, list, number: not a stated period we can read.
        return None

    # ISO text orders lexicographically, so this catches a range written
    # backwards even when both ends fall in the same month.
    if start is None or end is None or start > end:
        return None
    return start[:7], end[:7]
