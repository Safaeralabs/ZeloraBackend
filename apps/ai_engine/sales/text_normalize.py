"""
Lightweight phonetic/typo normalization for the DETERMINISTIC matching layers
only (critical-override situation detection, keyword fallbacks, the catalog
query filler-word split, the qualification guard). The LLM already understands
misspelled Spanish natively — this module exists purely so the non-LLM regex
layers don't miss common WhatsApp-style typos ("presio" -> "precio", "qe" ->
"que", "no ce" -> "no se").

Never applied to the text that is actually sent to the LLM or stored on the
Message record — only to a throwaway copy used for pattern matching.
"""
import re

# Ordered: phrase-level rules before the single-word rules they'd otherwise
# be shadowed by (e.g. "no ce" -> "no se" must run before the bare "ce" -> "se").
_SUBSTITUTIONS = (
    (r'\bno ce\b', 'no se'),
    (r'\bpresio(s)?\b', r'precio\1'),
    (r'\baser\b', 'hacer'),
    (r'\basen\b', 'hacen'),
    (r'\bqe\b', 'que'),
    (r'\bke\b', 'que'),
    (r'\bxq\b', 'porque'),
    (r'\bpq\b', 'porque'),
    (r'\bkiero\b', 'quiero'),
    (r'\bkisiera\b', 'quisiera'),
    (r'\btmb\b', 'tambien'),
    (r'\bdnd\b', 'donde'),
    (r'\bxfa\b', 'porfa'),
    (r'\bbno\b', 'bueno'),
    (r'\btoy\b', 'estoy'),
    (r'\bce\b', 'se'),
)

_COMPILED = [(re.compile(pattern, re.IGNORECASE), replacement) for pattern, replacement in _SUBSTITUTIONS]


def normalize_for_matching(text: str) -> str:
    """Return a normalized copy of ``text`` for use ONLY in regex/keyword
    matching. Not for display, storage, or the LLM prompt."""
    result = text or ''
    for pattern, replacement in _COMPILED:
        result = pattern.sub(replacement, result)
    return result
