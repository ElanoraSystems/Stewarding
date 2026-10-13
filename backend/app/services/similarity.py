"""Finds item names that are the same item written differently: spacing, order, plurals, punctuation or a typo."""
import re
from collections.abc import Iterable

WORDS = re.compile(r"[a-z0-9]+")


def _stem(word: str) -> str:
    """A very small singular form: glasses to glass, boxes to box, plates to plate."""
    if len(word) > 4 and word.endswith(("sses", "xes", "ches", "shes", "zes")):
        return word[:-2]
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def tokens(text: str) -> frozenset[str]:
    """The words of a name, lower case and singular, as a set so their order does not matter."""
    return frozenset(_stem(w) for w in WORDS.findall(text.lower()))


def compact(text: str) -> str:
    """Letters and digits only, so 'Dinner Plate 27 cm' and 'dinner-plate 27cm' become the same string."""
    return "".join(WORDS.findall(text.lower()))


def token_key(text: str) -> str:
    """The words of a name, singular and sorted, as one string; equal keys mean the same words in any order."""
    return " ".join(sorted(tokens(text)))


SCAN_LIMIT = 5000  # up to this many items every name is compared; beyond it the database narrows the candidates first


def within_edits(a: str, b: str, limit: int) -> bool:
    """Whether the edit distance is at most `limit`. Two-row dynamic programming that stops once a row exceeds the limit."""
    if abs(len(a) - len(b)) > limit:
        return False
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        if min(current) > limit:
            return False
        previous = current
    return previous[-1] <= limit


def classify(query: str, name: str) -> str | None:
    """'same' when the two names are the same item, 'similar' when they are close enough to warn, otherwise None."""
    q, n = compact(query), compact(name)
    if not q or not n:
        return None
    tq, tn = tokens(query), tokens(name)
    if q == n or tq == tn:
        return "same"
    if len(q) >= 3 and (q in n or n in q):
        return "similar"
    if within_edits(q, n, 1 if max(len(q), len(n)) < 10 else 2):
        return "similar"
    if len(tq | tn) > 1 and len(tq & tn) / len(tq | tn) >= 0.6:
        return "similar"
    return None


def find_similar(query: str, names: Iterable[tuple[int, str, str, bool]], limit: int = 8) -> list[dict]:
    """Ranks (id, code, name, active) rows against the query: the same item first, then the closest."""
    tq = tokens(query)
    ranked = []
    for item_id, code, name, active in names:
        match = classify(query, name)
        if match:
            tn = tokens(name)
            overlap = len(tq & tn) / len(tq | tn) if tq | tn else 0
            ranked.append((match != "same", -overlap, name.lower(), {"id": item_id, "code": code, "name": name, "active": active, "match": match}))
    ranked.sort(key=lambda r: r[:3])
    return [r[3] for r in ranked[:limit]]
