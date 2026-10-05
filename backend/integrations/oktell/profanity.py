"""Mask whole swear words in a spoken replica. Hints and the knowledge base stay as written."""

from __future__ import annotations

import re

# Stems are matched only at the start of a word, then the whole word becomes asterisks.
_STEMS = (
    "бля",
    "гандон",
    "еба",
    "ебе",
    "ебл",
    "ебу",
    "заеб",
    "муда",
    "муди",
    "наху",
    "оху",
    "пидар",
    "пидор",
    "пидр",
    "пизд",
    "поху",
    "сука",
    "суке",
    "суки",
    "сукой",
    "суку",
    "сучар",
    "хуе",
    "хуи",
    "хуй",
    "хуя",
)
_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")


def mask_profanity(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        word = match.group(0)
        folded = word.casefold().replace("ё", "е")
        if any(folded.startswith(stem) for stem in _STEMS):
            return "*" * len(word)
        return word

    return _WORD_RE.sub(replace, text)
