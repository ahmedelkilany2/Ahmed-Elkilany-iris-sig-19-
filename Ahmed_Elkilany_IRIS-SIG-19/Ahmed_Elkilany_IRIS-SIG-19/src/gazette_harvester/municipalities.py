"""Work out which municipalities a gazette covers.

The Kiosk only gives a publication title, e.g.
  "Mitteilungsblatt der Gemeinden Wehingen, Reichenbach a. H., Egesheim"
so the municipality list is derived from the title. Titles that don't name a place
fall back to the URL slug and are flagged as inferred.
"""
from __future__ import annotations

import re

_OF_PLACE = re.compile(r"\b(?:der|von)\s+(?:Gemeinden|Gemeinde|Städten|Städte|Stadt)\s+", re.IGNORECASE)
_TRAILING = re.compile(r"\s+mit\s+(?:den\s+)?Ortsteilen?\b.*$", re.IGNORECASE)
_SPLIT = re.compile(r"\s*,\s*|\s+und\s+|\s+&\s+|\s*/\s*")
_SLUG_PREFIX = re.compile(r"^(?:amtsblatt|mitteilungsblatt|gemeindenachrichten|nachrichten)-", re.IGNORECASE)


def municipalities_from_title(title: str, slug: str = "") -> tuple[list[str], bool]:
    """Return (names, inferred_from_slug)."""
    matches = list(_OF_PLACE.finditer(title))
    if matches:
        tail = _TRAILING.sub("", title[matches[-1].end():]).strip()
        names = [p.strip() for p in _SPLIT.split(tail) if p.strip()]
        if names:
            return names, False
    if slug:
        guess = _SLUG_PREFIX.sub("", slug).replace("-", " ").strip()
        if guess:
            return [guess.title()], True
    return [], True
