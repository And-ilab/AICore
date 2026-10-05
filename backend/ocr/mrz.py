"""ICAO TD3 MRZ parser for passports (no extra dependency).

Belarus / ICAO biometric passports use two 44-character lines, e.g.:

    P<BLRSAYAPIN<<ANDREI<<<<<<<<<<<<<<<<<<<<<<<<<<
    MP24178795BLR8304265M28042683260483A011PB648
"""

from __future__ import annotations

import re
from typing import Any

_TD3_LEN = 44
_CHECK_WEIGHTS = (7, 3, 1)


def _char_value(char: str) -> int:
    if char.isdigit():
        return int(char)
    if "A" <= char <= "Z":
        return ord(char) - 55
    if char == "<":
        return 0
    return -1


def mrz_check_digit(payload: str) -> str:
    total = 0
    for index, char in enumerate(payload):
        value = _char_value(char)
        if value < 0:
            return ""
        total += value * _CHECK_WEIGHTS[index % 3]
    return str(total % 10)


_CYR_TO_LATIN = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "У": "Y",
        "Х": "X",
    }
)


def _normalize_mrz_line(line: str) -> str:
    cleaned = re.sub(r"\s+", "", line.upper())
    cleaned = cleaned.replace("«", "<").replace("»", "<")
    cleaned = cleaned.replace("(O", "07").replace("(", "0").replace(")", "0")
    cleaned = cleaned.translate(_CYR_TO_LATIN)
    return cleaned


def _clean_name(value: str) -> str:
    tokens = [part for part in re.split(r"[^A-ZА-ЯЁ\-]+", value.upper()) if part]
    kept: list[str] = []
    for token in tokens:
        letters = set(token)
        if letters <= set("SKC"):
            continue
        if len(token) >= 3 and len(letters) == 1:
            continue
        # Tesseract often turns MRZ '<' into 'K'.
        if len(token) >= 4 and token.count("K") / len(token) >= 0.5:
            continue
        kept.append(token)
    return " ".join(kept)


def _looks_like_td3_line1(line: str) -> bool:
    if len(line) < 20:
        return False
    return bool(re.match(r"^P[A-Z<][A-Z]{3}[A-Z<]+$", line))


def _looks_like_td3_line2(line: str) -> bool:
    if len(line) < 20:
        return False
    return bool(re.match(r"^[A-Z0-9<]{20,}$", line)) and any(ch.isdigit() for ch in line)


def find_td3_pairs(text: str) -> list[tuple[str, str]]:
    raw_lines = [_normalize_mrz_line(item) for item in text.splitlines()]
    raw_lines = [item for item in raw_lines if item]
    pairs: list[tuple[str, str]] = []
    for index, line in enumerate(raw_lines):
        if not (_looks_like_td3_line1(line) or line.startswith("P<") or line.startswith("PC")):
            continue
        if index + 1 >= len(raw_lines):
            continue
        nxt = raw_lines[index + 1]
        if _looks_like_td3_line2(nxt):
            pairs.append(
                (
                    line.ljust(_TD3_LEN, "<")[: max(len(line), _TD3_LEN)],
                    nxt.ljust(_TD3_LEN, "<")[: max(len(nxt), _TD3_LEN)],
                )
            )
    return pairs


_LINE2_BODY = re.compile(
    r"([A-Z0-9]{8,9})([0-9O])([A-Z]{3})(\d{6})([0-9O])([MF])(\d{6})"
)


def find_td3_line2_strings(text: str) -> list[str]:
    """Recover TD3 line 2 even when OCR split number / dates across lines."""
    lines = [_normalize_mrz_line(item) for item in text.splitlines() if item.strip()]
    blobs = list(lines)
    for index, line in enumerate(lines[:-1]):
        nxt = lines[index + 1]
        blobs.append(line + nxt)
        if 7 <= len(line) <= 12 and nxt[:1] in {"O", "0"}:
            blobs.append(line + "0" + nxt[1:])
    found: list[str] = []
    seen: set[str] = set()
    for blob in blobs:
        for match in _LINE2_BODY.finditer(blob):
            doc, check, nationality, birth, birth_check, sex, expiry = match.groups()
            if check == "O":
                check = "0"
            if birth_check == "O":
                birth_check = "0"
            doc9 = doc.ljust(9, "<")[:9]
            line2 = f"{doc9}{check}{nationality}{birth}{birth_check}{sex}{expiry}"
            line2 = line2.ljust(_TD3_LEN, "<")[:_TD3_LEN]
            if line2 not in seen:
                seen.add(line2)
                found.append(line2)
    return found


def _names_from_line1(line: str) -> tuple[str, str]:
    rest = line[5:] if len(line) > 5 else line
    rest = rest.rstrip("<")
    parts = rest.split("<<", 1)
    surname = _clean_name(parts[0].replace("<", " "))
    given = _clean_name(parts[1].replace("<", " ")) if len(parts) > 1 else ""
    return surname, given


def _yyMMdd_to_date(raw: str) -> str:
    if not re.fullmatch(r"\d{6}", raw):
        return ""
    year, month, day = raw[:2], raw[2:4], raw[4:6]
    century = "19" if int(year) >= 50 else "20"
    return f"{day}.{month}.{century}{year}"


def _parse_td3_pair(line1: str, line2: str) -> dict[str, Any] | None:
    if len(line2) < 28:
        return None
    surname, given = _names_from_line1(line1)
    document_id = line2[0:9].replace("<", "")
    doc_check = line2[9:10]
    nationality = line2[10:13].replace("<", "")
    birth_raw = line2[13:19]
    sex = line2[20:21]
    expiry_raw = line2[21:27]
    expected_doc = mrz_check_digit(line2[0:9])
    checksum_ok = not (
        expected_doc and doc_check.isdigit() and expected_doc != doc_check
    )
    series = ""
    number = ""
    if re.fullmatch(r"[A-ZА-Я]{2}\d{7}", document_id):
        series, number = document_id[:2], document_id[2:]
    elif re.fullmatch(r"\d{9}|[A-ZА-Я]\d{8}", document_id):
        number = document_id
    full_name = " ".join(part for part in (surname, given) if part)
    if not full_name and not document_id:
        return None
    return {
        "surname": surname,
        "given_name": given,
        "full_name": full_name,
        "document_number": document_id,
        "series": series,
        "number": number,
        "nationality": nationality,
        "birth_date": _yyMMdd_to_date(birth_raw),
        "expiry_date": _yyMMdd_to_date(expiry_raw),
        "sex": sex if sex in {"M", "F", "<"} else "",
        "confidence": 0.96 if checksum_ok else 0.82,
        "checksum_ok": checksum_ok,
        "source": "mrz",
    }


def parse_td3_mrz(text: str) -> dict[str, Any] | None:
    """Parse TD3 MRZ from OCR text. Returns None if lines are not found."""
    hay = re.sub(r"[^A-ZА-ЯЁ0-9]+", " ", text.upper())
    candidates: list[dict[str, Any]] = []

    def _with_hay_id(item: dict[str, Any]) -> dict[str, Any]:
        doc = str(item.get("document_number") or "")
        if re.fullmatch(r"\d{8}", doc):
            match = re.search(rf"\b([A-Z]{doc})\b", hay)
            if match:
                item["document_number"] = match.group(1)
                item["number"] = match.group(1)
                item["checksum_ok"] = True
        return item
    for line1, line2 in find_td3_pairs(text):
        parsed = _parse_td3_pair(line1, line2)
        if parsed:
            candidates.append(_with_hay_id(parsed))
    known_line2 = {item.get("document_number") for item in candidates}
    for line2 in find_td3_line2_strings(text):
        parsed = _parse_td3_pair("", line2)
        if parsed:
            parsed = _with_hay_id(parsed)
            if parsed.get("document_number") not in known_line2:
                candidates.append(parsed)
    if not candidates:
        return None

    def _score(item: dict[str, Any]) -> tuple[int, int, int, int, int]:
        tokens = [part for part in str(item.get("full_name") or "").split() if part]
        hits = sum(1 for token in tokens if token in hay.split())
        document_id = str(item.get("document_number") or "")
        return (
            1 if item.get("checksum_ok") else 0,
            hits,
            1 if document_id and document_id in hay.split() else 0,
            1 if tokens else 0,
            -len(tokens),
        )

    return max(candidates, key=_score)
