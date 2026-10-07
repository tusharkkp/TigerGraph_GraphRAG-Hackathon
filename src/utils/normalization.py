"""
Unified text normalization and transliteration architecture.

Used consistently by:
1. Ingestion structured parser (clean storage in NFC)
2. Graph schema indexing & alias generation
3. Entity linking in GraphRAG & Agentic pipelines
4. Deterministic Judge Matcher in benchmark evaluation
"""

from __future__ import annotations

import difflib
import re
import unicodedata

# Extended transliteration map for characters not fully handled by standard NFKD decomposition
TRANSLITERATION_MAP: dict[str, str] = {
    "ı": "i",
    "İ": "I",
    "ø": "o",
    "Ø": "O",
    "ł": "l",
    "Ł": "L",
    "đ": "d",
    "Đ": "D",
    "ß": "ss",
    "æ": "ae",
    "Æ": "AE",
    "œ": "oe",
    "Œ": "OE",
}

# Real unicode dashes are always standardized to ' - '
UNICODE_DASH_REGEX = re.compile(r"\s*[\u2010\u2011\u2012\u2013\u2014\u2015]\s*")

# U+FFFD is treated as a dash ONLY when flanked by whitespace or between numbers/title parts
FFFD_DASH_REGEX = re.compile(
    r"(?:\s+\ufffd\s+)|"
    r"(?<=\w)\s+\ufffd(?=\w)|"
    r"(?<=\w)\ufffd\s+(?=\w)|"
    r"(?<=\d)\s*\ufffd\s*(?=\d)"
)


def replace_dash_context(text: str) -> str:
    """
    Replace U+FFFD (replacement character) and unicode dashes with ' - ' ONLY in dash contexts.
    
    If U+FFFD appears internal to a word without spaces (e.g. K\ufffdk\ufffdny where it replaced diacritics),
    it is not replaced with a dash.
    """
    if not text:
        return ""
    # Standardize genuine unicode dashes
    res = UNICODE_DASH_REGEX.sub(" - ", text)
    # Standardize U+FFFD only when in dash context
    res = FFFD_DASH_REGEX.sub(" - ", res)
    # Remaining standalone word-internal U+FFFD (e.g. K\ufffdk\ufffdny) is stripped
    res = res.replace("\ufffd", "")
    return res


def clean_text_for_storage(text: str) -> str:
    """
    Produce canonical, clean string representation for persistent graph storage.
    
    Invariants:
    - Canonical Unicode composition: NFC.
    - Strips non-printable ASCII control characters (keeps space, newline, tab).
    - Resolves dash context corruptions.
    """
    if not text:
        return ""
    t = replace_dash_context(text)
    # Strip ASCII control characters \x00-\x1f except tab and newline
    t = "".join(ch for ch in t if ord(ch) >= 32 or ch in "\n\t")
    # Normalize to canonical NFC for storage
    t = unicodedata.normalize("NFC", t)
    # Collapse multiple spaces
    t = re.sub(r"[ \t]+", " ", t).strip()
    return t


def build_match_key(text: str) -> str:
    """
    Generate normalized match key for entity linking and evaluation matching.
    
    Invariants:
    - Transliterates special latin letters (ı, ø, ł, đ, ß, æ).
    - Resolves dash contexts.
    - Decomposes to NFKD and removes combining diacritical marks.
    - Case-folds to lowercase and collapses whitespace/punctuation.
    """
    if not text:
        return ""
    # 1. Transliterate special letters
    t = text
    for src, dst in TRANSLITERATION_MAP.items():
        t = t.replace(src, dst)

    # 2. Handle dash context
    t = replace_dash_context(t)

    # 3. NFKD decomposition to separate base characters from accents
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))

    # 4. Remove punctuation except alphanumeric and spaces
    t = re.sub(r"[^\w\s]", " ", t)

    # 5. Lowercase and collapse whitespace
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def fuzzy_name_match(name1: str, name2: str, threshold: float = 0.92) -> bool:
    """
    Fallback fuzzy similarity matching using token-sorted sequence matcher.
    
    Returns True if similarity ratio >= threshold.
    """
    key1 = build_match_key(name1)
    key2 = build_match_key(name2)
    if not key1 or not key2:
        return False
    if key1 == key2:
        return True

    # Token-sorted comparison
    sorted1 = " ".join(sorted(key1.split()))
    sorted2 = " ".join(sorted(key2.split()))
    if sorted1 == sorted2:
        return True

    ratio = difflib.SequenceMatcher(None, sorted1, sorted2).ratio()
    return ratio >= threshold
