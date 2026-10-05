"""Page-level templates for any document, not only the passport data page.

Detects page kind from keywords, then pulls labeled values. Specialists
(passport MRZ, payment order) still win on the same key when confidence
is higher.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

FieldValue = dict[str, Any]

_VALUE = r".{1,160}"
_DATE = r"\d{2}[./-]\d{2}[./-]\d{4}|\d{2}\s+\d{2}\s+\d{4}|\d{4}-\d{2}-\d{2}"
_MONEY = r"[\d\s]+[.,]\d{2}"
_NAME = r"[A-ZА-ЯЁ][A-ZА-ЯЁa-zа-яё\-']{1,40}(?:\s+[A-ZА-ЯЁ][A-ZА-ЯЁa-zа-яё\-']{1,40}){0,3}"

# page_kind → (doc_type, signal phrases)
PAGE_KINDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "passport_mrz",
        "passport",
        ("p<", "<<<<<<", "passport no", "паспорт no"),
    ),
    (
        "passport_registration",
        "passport",
        (
            "прописк",
            "регистрац",
            "место жительства",
            "зарегистрирован",
            "снят с регистрац",
            "residence",
            "registered at",
        ),
    ),
    (
        "passport_children",
        "passport",
        ("сведения о детях", "дети", "children", "ребёнок", "ребенок"),
    ),
    (
        "passport_issued",
        "passport",
        (
            "орган выдачи",
            "код подразделен",
            "выдан",
            "authority",
            "issuing",
            "department code",
        ),
    ),
    (
        "passport_data",
        "passport",
        (
            "фамилия",
            "surname",
            "given name",
            "отчество",
            "дата рождения",
            "date of birth",
            "паспорт",
            "passport",
        ),
    ),
    (
        "payment_order",
        "payment_order",
        ("платёжн", "платежн", "payment order", "поручен"),
    ),
    (
        "account_statement",
        "account_statement",
        (
            "выписк по сч",
            "остаток",
            "opening balance",
            "statement of account",
        ),
    ),
    (
        "loan_agreement",
        "loan_agreement",
        ("кредитн", "loan agreement", "процентн"),
    ),
    (
        "payment_receipt",
        "payment_receipt",
        ("квитанц", "чек ", "receipt", "операция выполн"),
    ),
    (
        "banking_application",
        "banking_application",
        ("заявлен", "анкета", "application form"),
    ),
)

FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "full_name": ("ФИО", "Ф.И.О.", "Full name", "Фамилия Имя Отчество"),
    "surname": (
        "Фамилия",
        "Surname",
        "Family name",
        "Прозвішча",
        "ПРОЗВІШЧА",
        "Прэзвішча",
        "ПРЭЗВІШЧА",
        "SURNAME",
    ),
    "given_name": (
        "Имя",
        "Given names",
        "Given name",
        "Given Names",
        "GIVEN NAMES",
        "Імя",
        "ІМЯ",
    ),
    "patronymic": ("Отчество", "Patronymic", "Middle name"),
    "series": ("Серия", "Series", "Серия паспорта"),
    "number": ("Номер", "Number", "№ документа", "Passport No", "Passport No."),
    "document_number": (
        "Номер документа",
        "Document number",
        "Passport No.",
        "Passport No",
        "PASSPORT NO",
        "НУМАР ПАШПАРТА",
    ),
    "birth_date": ("Дата рождения", "Date of birth", "Birth", "Рождения"),
    "issue_date": ("Дата выдачи", "Date of issue", "Issued", "Выдан"),
    "expiry_date": (
        "Срок действия",
        "Date of expiry",
        "Expiry date",
        "expiry date",
        "Expiry",
        "Годен до",
    ),
    "birth_place": ("Место рождения", "Place of birth", "Birth place"),
    "address": (
        "Адрес",
        "Место жительства",
        "Прописка",
        "Зарегистрирован",
        "Адрес регистрации",
        "Residence",
        "Registered at",
    ),
    "issued_by": (
        "Орган выдачи",
        "Кем выдан",
        "Issuing authority",
        "Authority",
    ),
    "department_code": ("Код подразделения", "Department code"),
    "nationality": ("Гражданство", "Nationality", "Citizenship"),
    "sex": ("Пол", "Sex", "Gender"),
    "inn": ("ИНН", "INN", "Tax ID"),
    "personal_number": (
        "Личный номер",
        "Personal number",
        "Идентификационный номер",
        "Identification No",
        "Identification No.",
        "Identification number",
        "Асабісты нумар",
    ),
    "payer": ("Плательщик", "Payer"),
    "beneficiary": ("Получатель", "Beneficiary"),
    "amount": ("Сумма", "Amount"),
    "currency": ("Валюта", "Currency"),
    "purpose": ("Назначение", "Назначение платежа", "Purpose"),
    "account_number": ("Счёт", "Счет", "Расчётный счёт", "Account", "IBAN"),
    "period": ("Период", "Period"),
    "opening_balance": ("Входящий остаток", "Opening balance"),
    "closing_balance": ("Исходящий остаток", "Closing balance"),
    "agreement_number": ("Номер договора", "Договор №", "Agreement number"),
    "agreement_date": ("Дата договора", "Agreement date"),
    "principal": ("Сумма кредита", "Principal"),
    "interest_rate": ("Процентная ставка", "Interest rate", "Ставка"),
    "term": ("Срок", "Term"),
    "application_number": ("Номер заявления", "Application number"),
    "application_date": ("Дата заявления", "Application date"),
    "product": ("Продукт", "Product", "Вид продукта"),
    "operation_id": (
        "Номер операции",
        "№ операции",
        "Operation id",
        "ID операции",
        "RRN",
    ),
    "operation_date": ("Дата операции", "Operation date"),
    "status": ("Статус", "Status"),
}

_FIELD_PATTERNS: dict[str, str] = {
    "full_name": _NAME,
    "surname": _NAME,
    "given_name": _NAME,
    "patronymic": _NAME,
    "series": r"(?:\d{2}\s*\d{2}|[A-ZА-Я]{2})",
    "number": r"\d{6,10}",
    "document_number": r"[A-ZА-Я]{0,2}\s?\d{6,9}",
    "birth_date": _DATE,
    "issue_date": _DATE,
    "expiry_date": _DATE,
    "agreement_date": _DATE,
    "application_date": _DATE,
    "operation_date": _DATE,
    "amount": _MONEY,
    "principal": _MONEY,
    "opening_balance": _MONEY,
    "closing_balance": _MONEY,
    "currency": r"BYN|USD|EUR|RUB",
    "inn": r"\d{9,12}",
    "personal_number": r"[A-ZА-Я0-9]{10,16}",
    "department_code": r"\d{3}-\d{3}",
    "account_number": r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}|\d{10,20}",
    "interest_rate": r"\d{1,2}(?:[.,]\d{1,2})?\s*%?",
    "term": r"\d{1,4}",
    "sex": r"МУЖ\.?|ЖЕН\.?|M|F|MALE|FEMALE",
}


def _field(value: str, confidence: float, *, source: str = "page") -> FieldValue:
    return {
        "value": value.strip(),
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "source": source,
    }


def normalize_ocr_date(raw: str) -> str:
    text = (raw or "").strip()
    spaced = re.fullmatch(r"(\d{2})\s+(\d{2})\s+(\d{4})", text)
    if spaced:
        return f"{spaced.group(1)}.{spaced.group(2)}.{spaced.group(3)}"
    return text.replace("/", ".").replace("-", ".")


def _normalize_date(raw: str) -> str:
    return normalize_ocr_date(raw)


def _label_value(
    text: str,
    labels: tuple[str, ...],
    *,
    pattern: str,
    confidence: float = 0.86,
) -> FieldValue | None:
    """Match `Label: value`, or `Label / OTHER LANG` with the value on the next line."""
    for label in labels:
        same_line = re.compile(
            rf"(?im)(?:^|\n)\s*{re.escape(label)}\s*[:\-–.]?\s*({pattern})\s*(?:\n|$)",
        )
        match = same_line.search(text)
        if match:
            return _field(match.group(1), confidence, source=f"label:{label}")
        # Same line after bilingual tail: "DATE OF ISSUE / ДАТА ВЫДАЧЫ 12 09 2014".
        # Only for structured values (dates / IDs) — names would eat ПРОЗВІШЧА / ІМЯ.
        if len(label) >= 3 and r"\d{" in pattern:
            same_line_tail = re.compile(
                rf"(?im)(?:^|\n)\s*{re.escape(label)}\b[^\n]{{0,80}}?({pattern})\s*(?:\n|$)",
            )
            match = same_line_tail.search(text)
            if match:
                return _field(
                    match.group(1),
                    confidence - 0.02,
                    source=f"label_tail:{label}",
                )
        # ICAO data page: "DATE OF BIRTH / ДАТА НАРАДЖЭННЯ" then "23 02 1992".
        if len(label) >= 3:
            bilingual = re.compile(
                rf"(?im)(?:^|\n)\s*{re.escape(label)}\b[^\n]{{0,80}}\n\s*({pattern})\s*(?:\n|$)",
            )
            match = bilingual.search(text)
            if match:
                return _field(
                    match.group(1),
                    confidence - 0.03,
                    source=f"label_nl:{label}",
                )
        next_line = re.compile(
            rf"(?im)(?:^|\n)\s*{re.escape(label)}\s*[:\-–.]?\s*\n\s*({pattern})\s*(?:\n|$)",
        )
        match = next_line.search(text)
        if match:
            return _field(
                match.group(1),
                confidence - 0.03,
                source=f"label_nl:{label}",
            )
    return None


def detect_page_kind(text: str) -> str:
    hay = (text or "").casefold()
    best = "generic"
    best_hits = 0
    banking = {
        "payment_order",
        "account_statement",
        "loan_agreement",
        "payment_receipt",
        "banking_application",
    }
    for kind, _doc_type, signals in PAGE_KINDS:
        hits = sum(1 for token in signals if token in hay)
        if hits > best_hits or (
            hits == best_hits
            and hits
            and kind in banking
            and best.startswith("passport")
        ):
            best = kind
            best_hits = hits
    return best


def detect_document_type_from_pages(texts: list[str], filename: str = "") -> str:
    votes: dict[str, int] = {}
    hay = filename.casefold()
    for _kind, doc_type, signals in PAGE_KINDS:
        if any(token in hay for token in signals):
            votes[doc_type] = votes.get(doc_type, 0) + 2
    for text in texts:
        kind = detect_page_kind(text)
        for candidate, doc_type, _signals in PAGE_KINDS:
            if candidate == kind:
                votes[doc_type] = votes.get(doc_type, 0) + 1
                break
    if not votes:
        return "unknown"
    return max(votes, key=votes.get)


_HEADER_NOISE = re.compile(
    r"^(прописка|residence|паспорт|passport|место жительства|"
    r"зарегистрирован|address)$",
    re.I,
)


def _is_junk_labeled_value(key: str, value: str) -> bool:
    compact = re.sub(r"[\s/.\-–|]+", " ", value).strip()
    if len(compact) < 2:
        return True
    if _HEADER_NOISE.fullmatch(compact):
        return True
    if key == "address" and not re.search(r"\d|[А-Яа-яA-Za-z]{4,}", compact):
        return True
    if key == "address" and re.fullmatch(
        r"\d{1,2}\s+[А-Яа-яA-Za-z]+\s+\d{4}г?\.?",
        compact,
        re.I,
    ):
        return True
    return False


_LABEL_TO_KEY: dict[str, str] = {}
for _key, _labels in FIELD_LABELS.items():
    for _label in _labels:
        _LABEL_TO_KEY[_label.casefold()] = _key


_VOWELS = set("аеёиоуыэюяaeiouyіў")
_NOISE_CHARS = re.compile(r"[ħһɨı]")
_KNOWN_KEYS = frozenset(FIELD_LABELS) | frozenset(_LABEL_TO_KEY.values())
_ALIASES_LONGEST = tuple(
    sorted(_LABEL_TO_KEY.items(), key=lambda item: len(item[0]), reverse=True)
)
_HEADER_MARKERS = (
    "тип/type",
    "type /",
    "code of issuing",
    "код дзяржавы",
    "код государства",
    "нумар пашпарта",
    "passport no",
    "код дзяржавы/code",
)


def _folded_label(label: str) -> str:
    return re.sub(r"[\s_]+", " ", label or "").strip().casefold()


def is_form_header_label(label: str) -> bool:
    compact = _folded_label(label)
    if not compact:
        return False
    if compact.count("/") >= 2:
        return True
    if len(compact) > 48:
        return True
    hits = sum(1 for marker in _HEADER_MARKERS if marker in compact)
    return hits >= 2


def canonical_field_key(label: str) -> str | None:
    folded = _folded_label(label)
    if not folded:
        return None
    if folded in _LABEL_TO_KEY:
        return _LABEL_TO_KEY[folded]
    underscored = folded.replace(" ", "_")
    if underscored in FIELD_LABELS:
        return underscored
    if is_form_header_label(label):
        return None
    generic = {
        "number",
        "номер",
        "series",
        "серия",
        "date",
        "expiry",
        "issued",
        "birth",
        "name",
        "имя",
        "status",
        "срок",
        "account",
        "счёт",
        "счет",
    }
    for alias, key in _ALIASES_LONGEST:
        if len(alias) < 5 or alias in generic:
            continue
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", folded):
            return key
    return None


def _slug_label(label: str) -> str:
    mapped = canonical_field_key(label)
    if mapped:
        return mapped
    slug = re.sub(r"[^\wа-яё]+", "_", label.casefold(), flags=re.IGNORECASE)
    return (slug.strip("_") or "field")[:80]


def collapse_extracted_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Map aliases to known keys and drop printed headers / duplicate OCR rows."""
    collapsed: dict[str, Any] = {}
    leftovers: list[tuple[str, Any]] = []

    def confidence(payload: Any) -> float:
        if isinstance(payload, Mapping):
            try:
                return float(payload.get("confidence") or 0)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def value_of(payload: Any) -> str:
        if isinstance(payload, Mapping) and "value" in payload:
            return re.sub(r"\s+", " ", str(payload.get("value") or "")).strip().casefold()
        return re.sub(r"\s+", " ", str(payload or "")).strip().casefold()

    def take(key: str, payload: Any) -> None:
        current = collapsed.get(key)
        if current is None or confidence(payload) > confidence(current):
            if isinstance(payload, dict) and key in FIELD_LABELS:
                payload = {**payload, "label": FIELD_LABELS[key][0]}
            collapsed[key] = payload

    for key, payload in fields.items():
        label = ""
        if isinstance(payload, Mapping):
            label = str(payload.get("label") or "")
        if is_form_header_label(key) or is_form_header_label(label):
            continue
        canon = canonical_field_key(key) or canonical_field_key(label)
        if canon:
            take(canon, payload)
        else:
            leftovers.append((key, payload))

    known_values = {value_of(item) for item in collapsed.values() if value_of(item)}
    for key, payload in leftovers:
        value = value_of(payload)
        if value and value in known_values:
            continue
        take(key, payload)
    return collapsed


def _letter_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁёІіЎў]+", text)


def _has_vowel(word: str) -> bool:
    return any(char.casefold() in _VOWELS for char in word)


def _single_script(word: str) -> bool:
    has_latin = bool(re.search(r"[A-Za-z]", word))
    has_cyrillic = bool(re.search(r"[А-Яа-яЁёІіЎў]", word))
    return not (has_latin and has_cyrillic)


def _is_ocr_noise(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text or "").strip(" .-•·*|:_")
    if not compact:
        return True
    if _NOISE_CHARS.search(compact):
        return True
    letters = re.sub(r"[^A-Za-zА-Яа-яЁёІіЎў]", "", compact)
    if letters and not _single_script(letters) and len(letters) <= 14:
        return True
    words = _letter_words(compact)
    if words and all(len(word) <= 8 and not _has_vowel(word) for word in words):
        return True
    return False


def is_usable_field_key(key: str) -> bool:
    compact = re.sub(r"[_\s]+", " ", key or "").strip()
    if not compact:
        return False
    folded = compact.casefold()
    if folded in _LABEL_TO_KEY or folded in _KNOWN_KEYS or key in _KNOWN_KEYS:
        return True
    if canonical_field_key(key):
        return True
    if is_form_header_label(key) or _is_ocr_noise(compact):
        return False
    return _looks_like_label(compact)


def _looks_like_label(label: str) -> bool:
    compact = re.sub(r"\s+", " ", label).strip(" .-•·*|")
    if len(compact) < 3 or len(compact) > 48:
        return False
    if is_form_header_label(compact):
        return False
    if not re.search(r"[A-Za-zА-Яа-яЁёІі]", compact):
        return False
    if re.fullmatch(r"[\d\s.:/-]+", compact):
        return False
    if _is_ocr_noise(compact):
        return False
    if compact.casefold() in {
        "http",
        "https",
        "www",
        "стр",
        "стр.",
        "page",
        "n",
        "№",
        "or",
        "of",
        "the",
        "and",
    }:
        return False
    return True


def _looks_like_value(value: str) -> bool:
    compact = re.sub(r"\s+", " ", value).strip(" .-•·*|")
    if len(compact) < 1 or len(compact) > 400:
        return False
    if compact in {":", "-", "—", "–", "нет", "n/a"}:
        return False
    if _is_ocr_noise(compact):
        return False
    return True


def _is_next_line_label(label: str) -> bool:
    compact = re.sub(r"\s+", " ", label).strip(" .-•·*|")
    if not _looks_like_label(compact):
        return False
    if compact.casefold() in _LABEL_TO_KEY:
        return True
    return len(compact.split()) >= 2


def extract_generic_fields(text: str) -> dict[str, FieldValue]:
    """Any 'Label: value' / two-column line — not limited to a document template."""
    fields: dict[str, FieldValue] = {}
    normalized = (text or "").replace("\r\n", "\n")
    lines = normalized.split("\n")

    def add(label: str, value: str, confidence: float, source: str) -> None:
        clean_label = re.sub(r"\s+", " ", label).strip(" .-•·*|")
        clean_value = re.sub(r"\s+", " ", value).strip(" .-•·*|")
        if not _looks_like_label(clean_label) or not _looks_like_value(clean_value):
            return
        key = _slug_label(clean_label)
        if key in fields:
            return
        payload = _field(clean_value, confidence, source=source)
        payload["label"] = clean_label
        fields[key] = payload

    colon = re.compile(
        r"^\s*([^:\n]{2,80}?)\s*[:：]\s*(.+?)\s*$",
    )
    spaced = re.compile(
        r"^\s*([A-Za-zА-Яа-яЁё][^:\n]{1,70}?)\s{2,}(.+?)\s*$",
    )
    for line in lines:
        match = colon.match(line)
        if match:
            add(match.group(1), match.group(2), 0.84, "colon")
            continue
        match = spaced.match(line)
        if match:
            add(match.group(1), match.group(2), 0.78, "columns")

    used_as_value: set[int] = set()
    for index, line in enumerate(lines[:-1]):
        if index in used_as_value:
            continue
        label = line.strip()
        nxt = lines[index + 1].strip()
        if (
            _is_next_line_label(label)
            and ":" not in label
            and _looks_like_value(nxt)
            and not (
                colon.match(nxt)
                and _looks_like_label(colon.match(nxt).group(1))
            )
            and not spaced.match(nxt)
        ):
            add(label, nxt, 0.74, "label_nl")
            used_as_value.add(index + 1)
    return fields


def extract_labeled_fields(text: str) -> dict[str, FieldValue]:
    """Pull any labeled field the page happens to contain."""
    fields: dict[str, FieldValue] = {}
    normalized = (text or "").replace("\r\n", "\n")
    for key, labels in FIELD_LABELS.items():
        pattern = _FIELD_PATTERNS.get(key, _VALUE)
        found = None
        for label in labels:
            candidate = _label_value(
                normalized, (label,), pattern=pattern, confidence=0.86
            )
            if not candidate:
                continue
            value = str(candidate["value"]).strip(" .;,:/")
            if _is_junk_labeled_value(key, value):
                continue
            found = candidate
            break
        if not found:
            continue
        value = str(found["value"]).strip(" .;,:/")
        if key.endswith("_date") or key in {
            "birth_date",
            "issue_date",
            "expiry_date",
        }:
            value = _normalize_date(value)
        fields[key] = _field(
            value,
            float(found["confidence"]),
            source=str(found.get("source") or f"page:{key}"),
        )
    return fields


def merge_field_maps(*maps: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in maps:
        for key, value in payload.items():
            if key not in merged:
                merged[key] = value
                continue
            left = merged[key]
            right = value
            left_conf = (
                float(left.get("confidence") or 0)
                if isinstance(left, dict)
                else 0.0
            )
            right_conf = (
                float(right.get("confidence") or 0)
                if isinstance(right, dict)
                else 0.0
            )
            if right_conf > left_conf:
                merged[key] = right
    return merged


_MONTHS_RU = {
    "января": "01",
    "февраля": "02",
    "марта": "03",
    "апреля": "04",
    "мая": "05",
    "июня": "06",
    "июля": "07",
    "августа": "08",
    "сентября": "09",
    "октября": "10",
    "ноября": "11",
    "декабря": "12",
}


def extract_registration_fields(text: str) -> dict[str, FieldValue]:
    """Address / date / UFMS from a Russian passport registration stamp."""
    hay = (text or "").casefold()
    if not any(
        token in hay
        for token in ("зарегистрир", "место жительства", "прописк", "residence")
    ):
        return {}

    fields: dict[str, FieldValue] = {}
    date_match = re.search(
        r"(?i)\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|"
        r"августа|сентября|октября|ноября|декабря)\s+(\d{4})",
        text,
    )
    if date_match:
        fields["registration_date"] = _field(
            f"{int(date_match.group(1)):02d}."
            f"{_MONTHS_RU[date_match.group(2).casefold()]}."
            f"{date_match.group(3)}",
            0.9,
            source="reg_date",
        )

    region = re.search(
        r"([А-ЯЁ]{5,}(?:СКАЯ|СКИЙ|СКОЕ)?)\s+РЕСП\.?",
        text,
        re.I,
    )
    city = re.search(
        r"(?:(?<!\d)ГОР\.|(?<!\d)город\.?|(?<!\d)г\.)\s*"
        r"([А-ЯЁ][А-ЯЁа-яё\-]{2,})",
        text,
        re.I,
    )
    street = re.search(
        r"(?:УЛ\.|улица[:.]?)\s*([0-9А-ЯЁ][0-9А-ЯЁа-яё\s\-]{1,40})",
        text,
        re.I,
    )
    house = re.search(
        r"(?:дом|д)\s*[:.]?\s*(\d+[А-Яа-яA-Za-z]?)\b",
        text,
        re.I,
    )
    if not house:
        house = re.search(r"(?i)(?:дом|д|fon)\s*[:.]?\s*(\d+)\s+Кор", text)

    parts: list[str] = []
    if region:
        parts.append(f"{region.group(1).title()} Респ.")
    if city:
        parts.append(f"г. {city.group(1).title()}")
    if street:
        street_val = re.sub(r"\s+", " ", street.group(1)).strip(" .;,:|")
        street_val = re.sub(r"(?i)\s*года$", " года", street_val)
        if street_val:
            parts.append(f"ул. {street_val}")
    if house:
        parts.append(f"д. {house.group(1)}")
    if parts:
        fields["address"] = _field(", ".join(parts), 0.92, source="reg_stamp")

    authority = re.search(
        r"(ОТДЕЛ УФМС[\s\S]{10,160}?)(?:\n\s*\d{3}-\d{3}|\n\s*заверил|$)",
        text,
        re.I,
    )
    if authority:
        cleaned = re.sub(r"[|\"“”]+", " ", authority.group(1))
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .;,:")
        if len(cleaned) >= 12:
            fields["issued_by"] = _field(cleaned, 0.8, source="ufms")
    return fields


def extract_from_pages(
    pages: list[str],
    *,
    filename: str = "",
) -> tuple[str, dict[str, FieldValue], list[str]]:
    kinds = [detect_page_kind(page) for page in pages]
    combined = "\n\n".join(page for page in pages if page.strip())
    fields = extract_labeled_fields(combined)
    doc_type = detect_document_type_from_pages(pages, filename=filename)
    return doc_type, fields, kinds
