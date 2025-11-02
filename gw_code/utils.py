"""
Utility helpers.
"""

import unicodedata


def slugify(text: str, allow_unicode: bool = False) -> str:
    """Convert text to URL-friendly slug without regex."""
    text = str(text)
    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    out = []
    prev_dash = False
    for ch in text.lower().strip():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif ch in (" ", "_", "-"):
            if out and not prev_dash:
                out.append("-")
                prev_dash = True
        else:
            # skip punctuation/symbols
            pass
    slug = "".join(out).strip("-")
    return slug


__all__ = ["slugify"]
