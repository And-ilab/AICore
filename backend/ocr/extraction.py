"""Deterministic field extraction from OCR text (FR-OCR-13).

Works without an LLM: regex + label heuristics per document type.
Confidence is estimated from match strength / label proximity.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ocr.mrz import parse_td3_mrz
from ocr.page_templates import (
    detect_document_type_from_pages,
    detect_page_kind,
    collapse_extracted_fields,
    extract_generic_fields,
    extract_labeled_fields,
    extract_registration_fields,
    merge_field_maps,
    normalize_ocr_date,
    _label_value as _shared_label_value,
)

FieldValue = dict[str, Any]

OPEN_ENDED_DOC_TYPES = frozenset({"", "unknown", "ml", "auto"})


def is_open_ended_doc_type(value: str | None) -> bool:
    return (value or "").strip().lower() in OPEN_ENDED_DOC_TYPES


def _field(value: str, confidence: float, *, source: str = "regex") -> FieldValue:
    return {
        "value": value.strip(),
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "source": source,
    }


_NAME_TOKEN = r"[A-ZА-ЯЁ][A-ZА-ЯЁa-zа-яё\-']{1,40}"
_GEO_WORDS = frozenset(
    {
        "ГОРОД",
        "Г",
        "ОБЛ",
        "ОБЛАСТЬ",
        "РЕСП",
        "РЕСПУБЛИКА",
        "КРАЙ",
        "РАЙОН",
        "СЕЛО",
        "ДЕР",
        "ДЕРЕВНЯ",
        "ПОС",
        "ПОСЁЛОК",
        "ПОСЕЛОК",
        "СТАНЦИЯ",
        "МОСКВА",
        "САНКТ",
        "ПЕТЕРБУРГ",
        "РОССИЯ",
        "РОССИЙСКАЯ",
        "ФЕДЕРАЦИЯ",
        "PASSPORT",
        "ПАСПОРТ",
        "МУЖ",
        "ЖЕН",
        "MALE",
        "FEMALE",
        "REPUBLIC",
        "OF",
        "BELARUS",
        "BELARUSIAN",
        "IDENTITY",
        "NATIONALITY",
        "MINISTRY",
        "INTERNAL",
        "AFFAIRS",
        "HOLDER",
        "SIGNATURE",
        "AUTHORITY",
        "ISSUING",
        "TYPE",
        "CODE",
        "SEX",
        "ПОЛ",
        "ГРАЖДАНСТВО",
        "ГРАМАДЗЯНСТВА",
        "РЭСПУБЛИКА",
        "БЕЛАРУСЬ",
        "UNITED",
        "STATES",
        "AMERICA",
        "AZERBAIJAN",
        "AZORBAYCAN",
        "AZERBAYCAN",
        "RESPUBLIKASI",
        "PASPORT",
        "SURNAME",
        "GIVEN",
        "NAMES",
        "DATE",
        "BIRTH",
        "ISSUE",
        "EXPIRY",
        "PERSONAL",
        "PLACE",
        "NUMBER",
        "MINISTRY",
    }
)


_DATE_VALUE = (
    r"\d{2}[./-]\d{2}[./-]\d{4}"
    r"|\d{2}\s*[./-]\s*\d{2}\s*[./-]\s*\d{4}"
    r"|\d{2}\s+\d{2}\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
)


def _label_value(
    text: str,
    labels: tuple[str, ...],
    *,
    pattern: str,
    confidence: float = 0.9,
) -> FieldValue | None:
    """Match `Label: value` or bilingual `Label / OTHER` with value on the next line."""
    return _shared_label_value(
        text, labels, pattern=pattern, confidence=confidence
    )


def _normalize_date(raw: str) -> str:
    return normalize_ocr_date(raw)


def _date_key(value: str) -> tuple[int, int, int] | None:
    text = _normalize_date(value)
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if not match:
        return None
    day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
        return None
    return year, month, day


def _find_all_dates(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(_DATE_VALUE, text):
        normalized = _normalize_date(match.group(0))
        if not _date_key(normalized) or normalized in seen:
            continue
        seen.add(normalized)
        found.append(normalized)
    return found


def _issue_date_from_others(text: str, fields: dict[str, FieldValue]) -> FieldValue | None:
    """ICAO MRZ has birth + expiry, but never issue date — take the leftover visual date."""
    birth = _normalize_date(str((fields.get("birth_date") or {}).get("value") or ""))
    expiry = _normalize_date(str((fields.get("expiry_date") or {}).get("value") or ""))
    leftovers = [item for item in _find_all_dates(text) if item not in {birth, expiry}]
    if not leftovers:
        return None
    birth_key = _date_key(birth)
    expiry_key = _date_key(expiry)
    if birth_key and expiry_key:
        between = [
            item
            for item in leftovers
            if (key := _date_key(item)) and birth_key < key < expiry_key
        ]
        if between:
            leftovers = between
    return _field(leftovers[0], 0.76, source="date_remainder")


def _is_geo_or_junk_name(value: str) -> bool:
    tokens = [part for part in re.split(r"\s+", value.strip()) if part]
    if not tokens:
        return True
    if re.search(r"[A-Za-z]", value) and re.search(r"[А-Яа-яЁё]", value):
        return True
    hay = value.upper().replace("Ё", "Е")
    if any(
        frag in hay
        for frag in (
            "РЕСП",
            "ВОТКИН",
            "УДМУРТ",
            "ЗАРЕГ",
            "ЖИТЕЛЬ",
            "ГОРОД",
            "УЛИЦ",
            "ОБЛАСТ",
        )
    ):
        return True
    upper = [token.casefold().replace("ё", "е").upper() for token in tokens]
    if any(token in _GEO_WORDS for token in upper):
        return True
    if any(len(token) <= 2 for token in tokens):
        return True
    if len(tokens) == 1 and tokens[0].upper() in _GEO_WORDS:
        return True
    return False


def _visual_repeated_names(text: str) -> tuple[str, str] | None:
    """Pick surname/given from tokens that OCR saw twice (label + value / two langs)."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for token in re.findall(r"[A-ZА-ЯЁ]{4,20}", text.upper().replace("Ё", "Е")):
        if token in _GEO_WORDS or _is_geo_or_junk_name(token):
            continue
        if token not in counts:
            order.append(token)
            counts[token] = 0
        counts[token] += 1
    repeated = [token for token in order if counts[token] >= 2]
    if len(repeated) >= 2:
        return repeated[0], repeated[1]
    return None


def extract_passport_fields(
    text: str,
    *,
    allow_name_guess: bool = True,
) -> dict[str, FieldValue]:
    fields: dict[str, FieldValue] = {}
    normalized = text.replace("\r\n", "\n")
    mrz = parse_td3_mrz(normalized)
    if mrz:
        conf = float(mrz["confidence"])
        if mrz.get("surname"):
            fields["surname"] = _field(mrz["surname"], conf, source="mrz")
        if mrz.get("given_name"):
            fields["given_name"] = _field(mrz["given_name"], conf, source="mrz")
        if mrz.get("full_name"):
            fields["full_name"] = _field(mrz["full_name"], conf, source="mrz")
        if mrz.get("series"):
            fields["series"] = _field(mrz["series"], conf, source="mrz")
        if mrz.get("number"):
            fields["number"] = _field(mrz["number"], conf, source="mrz")
        if mrz.get("document_number"):
            fields["document_number"] = _field(
                mrz["document_number"],
                conf,
                source="mrz",
            )
        if mrz.get("birth_date"):
            fields["birth_date"] = _field(mrz["birth_date"], conf, source="mrz")
        if mrz.get("expiry_date"):
            fields["expiry_date"] = _field(mrz["expiry_date"], 0.9, source="mrz")

    surname = _label_value(
        normalized,
        ("Фамилия", "Surname", "Family name", "Прозвішча", "ПРОЗВІШЧА"),
        pattern=_NAME_TOKEN,
        confidence=0.94,
    )
    name = _label_value(
        normalized,
        ("Имя", "Given names", "Given name", "Given Names", "Імя", "ІМЯ"),
        pattern=_NAME_TOKEN,
        confidence=0.93,
    )
    patronymic = _label_value(
        normalized,
        ("Отчество", "Patronymic", "Middle name"),
        pattern=_NAME_TOKEN,
        confidence=0.91,
    )

    # Drop OCR garbage that matched labels incorrectly.
    if surname and _is_geo_or_junk_name(str(surname["value"])):
        surname = None
    if name and _is_geo_or_junk_name(str(name["value"])):
        name = None
    if patronymic and _is_geo_or_junk_name(str(patronymic["value"])):
        patronymic = None

    fio = _label_value(
        normalized,
        ("ФИО", "Full name", "Ф.И.О."),
        pattern=rf"{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{1,2}}",
        confidence=0.96,
    )
    if fio and _is_geo_or_junk_name(str(fio["value"])):
        fio = None

    if "full_name" not in fields:
        if fio:
            fields["full_name"] = fio
        elif surname and name:
            parts = [str(surname["value"]), str(name["value"])]
            if patronymic:
                parts.append(str(patronymic["value"]))
            conf = min(
                float(surname["confidence"]),
                float(name["confidence"]),
                float(patronymic["confidence"]) if patronymic else 1.0,
            )
            fields["full_name"] = _field(" ".join(parts), conf, source="compose")

    if surname and "surname" not in fields:
        fields["surname"] = surname
    if name and "given_name" not in fields:
        fields["given_name"] = name
    if patronymic and "patronymic" not in fields:
        fields["patronymic"] = patronymic

    # RF passport: "45 11 532704" / "4511 532704"; BY: "PD 0000000" / "KH2430485"
    rf_id = re.search(
        r"(?m)(?<![\d])(\d{2})\s*(\d{2})\s*(\d{6})(?!\d)",
        normalized,
    )
    by_id = re.search(
        r"(?i)\b([A-ZА-Я]{2})\s*[-–]?\s*(\d{7})\b",
        normalized,
    )
    by_labeled = _label_value(
        normalized,
        (
            "Passport No",
            "Passport No.",
            "PASSPORT NO",
            "НУМАР ПАШПАРТА",
            "Номер паспорта",
        ),
        pattern=r"[A-ZА-Я]{2}\s*[-–]?\s*\d{7}",
        confidence=0.93,
    )
    if by_labeled and not by_id:
        compact = re.sub(r"[\s\-–]+", "", str(by_labeled["value"]).upper())
        labeled_match = re.fullmatch(r"([A-ZА-Я]{2})(\d{7})", compact)
        if labeled_match:
            by_id = labeled_match
    series = _label_value(
        normalized,
        ("Серия", "Series", "Серия паспорта"),
        pattern=r"(?:\d{2}\s*\d{2}|[A-ZА-Я]{2})",
        confidence=0.92,
    )
    number = _label_value(
        normalized,
        ("Номер", "Number", "№", "N"),
        pattern=r"\d{6,7}",
        confidence=0.9,
    )
    if rf_id:
        series = series or _field(
            f"{rf_id.group(1)} {rf_id.group(2)}",
            0.9,
            source="rf_id",
        )
        number = number or _field(rf_id.group(3), 0.9, source="rf_id")
    if by_id:
        by_series = by_id.group(1).upper()
        by_number = by_id.group(2)
        series_val = str(series["value"]).replace(" ", "") if series else ""
        number_val = str(number["value"]) if number else ""
        if not series or not re.fullmatch(r"[A-ZА-Я]{2}", series_val):
            series = _field(by_series, 0.9, source="by_id")
        if not number or not re.fullmatch(r"\d{7}", number_val):
            number = _field(by_number, 0.9, source="by_id")
    intl_id = re.search(r"\b([A-Z]\d{8})\b", normalized.upper())
    if (
        intl_id
        and "document_number" not in fields
        and not fields.get("series")
    ):
        fields["document_number"] = _field(
            intl_id.group(1), 0.8, source="intl_id"
        )
        number = number or _field(intl_id.group(1), 0.8, source="intl_id")
    if series and "series" not in fields:
        # Normalize RF series to "45 11"
        series_val = re.sub(r"\s+", " ", str(series["value"]).strip())
        compact = series_val.replace(" ", "")
        if re.fullmatch(r"\d{4}", compact):
            series = _field(
                f"{compact[:2]} {compact[2:]}",
                float(series["confidence"]),
                source=str(series.get("source") or "regex"),
            )
        fields["series"] = series
    if number and "number" not in fields:
        fields["number"] = number
    if (
        "document_number" not in fields
        and fields.get("series")
        and fields.get("number")
    ):
        series_val = str(fields["series"]["value"]).replace(" ", "")
        number_val = str(fields["number"]["value"])
        if re.fullmatch(r"[A-ZА-Я]{2}", series_val) and re.fullmatch(
            r"\d{7}", number_val
        ):
            fields["document_number"] = _field(
                f"{series_val}{number_val}",
                min(
                    float(fields["series"]["confidence"]),
                    float(fields["number"]["confidence"]),
                ),
                source="compose",
            )

    issue_date = _label_value(
        normalized,
        (
            "Дата выдачи",
            "Date of issue",
            "DATE OF ISSUE",
            "Issued",
            "Выдан",
            "Дата выдачы",
            "Дата выдач",
        ),
        pattern=_DATE_VALUE,
        confidence=0.9,
    )
    if not issue_date:
        date_match = re.search(
            rf"(?is)(?:выдач|issued|issve|issue\b).{{0,80}}?({_DATE_VALUE})",
            normalized,
        )
        if date_match:
            issue_date = _field(
                _normalize_date(date_match.group(1)),
                0.72,
                source="proximity",
            )
    birth_date = _label_value(
        normalized,
        (
            "Дата рождения",
            "Date of birth",
            "DATE OF BIRTH",
            "Birth",
            "Рождения",
            "Дата нараджэння",
            "Дата нараджэння",
        ),
        pattern=_DATE_VALUE,
        confidence=0.9,
    )
    if birth_date and "birth_date" not in fields:
        fields["birth_date"] = _field(
            _normalize_date(str(birth_date["value"])),
            float(birth_date["confidence"]),
            source=str(birth_date.get("source") or "regex"),
        )
    if issue_date and "issue_date" not in fields:
        fields["issue_date"] = _field(
            _normalize_date(str(issue_date["value"])),
            float(issue_date["confidence"]),
            source=str(issue_date.get("source") or "regex"),
        )
    if "issue_date" not in fields:
        remainder = _issue_date_from_others(normalized, fields)
        if remainder:
            fields["issue_date"] = remainder

    if "full_name" not in fields:
        visual = _visual_repeated_names(normalized)
        if visual:
            fields["surname"] = fields.get("surname") or _field(
                visual[0], 0.78, source="repeat"
            )
            fields["given_name"] = fields.get("given_name") or _field(
                visual[1], 0.78, source="repeat"
            )
            fields["full_name"] = _field(
                f"{visual[0]} {visual[1]}", 0.78, source="repeat"
            )

    # Free-form FIO only when labels failed — never take geo / stamp lines.
    if allow_name_guess and "full_name" not in fields:
        for match in re.finditer(
            rf"(?m)^\s*({_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{1,2}})\s*$",
            normalized,
        ):
            candidate = match.group(1)
            if _is_geo_or_junk_name(candidate):
                continue
            # Prefer 3-token FIO (surname + name + patronymic).
            token_count = len(candidate.split())
            conf = 0.7 if token_count >= 3 else 0.58
            fields["full_name"] = _field(candidate, conf, source="caps_line")
            if token_count >= 3:
                break

    if "issue_date" not in fields and "birth_date" not in fields:
        any_date = re.search(
            r"\b(\d{2})[./-](\d{2})[./-](\d{4})\b",
            normalized,
        )
        if any_date:
            fields["issue_date"] = _field(
                f"{any_date.group(1)}.{any_date.group(2)}.{any_date.group(3)}",
                0.45,
                source="any_date",
            )

    return fields


def extract_payment_order_fields(text: str) -> dict[str, FieldValue]:
    fields: dict[str, FieldValue] = {}
    normalized = text.replace("\r\n", "\n")

    doc_no = _label_value(
        normalized,
        ("Номер", "№", "Document number", "Платёжное поручение"),
        pattern=r"\d{1,10}",
        confidence=0.88,
    )
    if not doc_no:
        match = re.search(r"(?im)payment order\s*#?\s*(\d{1,10})", normalized)
        if match:
            doc_no = _field(match.group(1), 0.8, source="proximity")
    if doc_no:
        fields["document_number"] = doc_no

    date = _label_value(
        normalized,
        ("Дата", "Date"),
        pattern=r"\d{2}[./-]\d{2}[./-]\d{4}|\d{4}-\d{2}-\d{2}",
        confidence=0.85,
    )
    if date:
        fields["date"] = date

    payer = _label_value(
        normalized,
        ("Плательщик", "Payer"),
        pattern=r".{2,120}",
        confidence=0.84,
    )
    if payer:
        fields["payer"] = payer

    beneficiary = _label_value(
        normalized,
        ("Получатель", "Beneficiary"),
        pattern=r".{2,120}",
        confidence=0.84,
    )
    if beneficiary:
        fields["beneficiary"] = beneficiary

    amount = _label_value(
        normalized,
        ("Сумма", "Amount"),
        pattern=r"[\d\s]+[.,]\d{2}",
        confidence=0.9,
    )
    if not amount:
        match = re.search(r"(?im)amount\s*:\s*([\d\s]+[.,]\d{2})", normalized)
        if match:
            amount = _field(match.group(1), 0.82, source="proximity")
    if amount:
        fields["amount"] = amount

    purpose = _label_value(
        normalized,
        ("Назначение", "Purpose"),
        pattern=r".{3,200}",
        confidence=0.8,
    )
    if purpose:
        fields["purpose"] = purpose

    currency = _label_value(
        normalized,
        ("Валюта", "Currency"),
        pattern=r"BYN|USD|EUR|RUB",
        confidence=0.95,
    )
    if not currency:
        match = re.search(r"\b(BYN|USD|EUR|RUB)\b", normalized, re.I)
        if match:
            currency = _field(match.group(1).upper(), 0.88, source="token")
    if currency:
        fields["currency"] = currency

    return fields


_EXTRACTORS = {
    "passport": extract_passport_fields,
    "payment_order": extract_payment_order_fields,
}


def detect_document_type(text: str, filename: str = "") -> str:
    hay = f"{filename}\n{text}".casefold()
    if (
        any(
            token in hay
            for token in (
                "паспорт",
                "passport",
                "pasport",
                "удостоверени",
                "p<blr",
                "p<rus",
                "surname",
                "given name",
            )
        )
        or "p<" in hay
        or parse_td3_mrz(text) is not None
    ):
        return "passport"
    if any(
        token in hay
        for token in (
            "платёжн",
            "платежн",
            "payment order",
            "поручен",
            "poruchen",
            "platezh",
        )
    ):
        return "payment_order"
    if any(
        token in hay
        for token in (
            "егрн",
            "недвижим",
            "кадастр",
            "реестр недвижимости",
        )
    ):
        pass
    elif any(
        token in hay
        for token in (
            "остаток",
            "выписк по сч",
            "statement of account",
            "opening balance",
        )
    ) or (
        any(token in hay for token in ("выписк", "vypisk", "справк", "spravk"))
        and any(
            token in hay
            for token in ("счёт", "счет", "iban", "зачисление", "по счету", "по счёту")
        )
    ):
        return "account_statement"
    if any(token in hay for token in ("кредитн", "kredit", "loan agreement")):
        return "loan_agreement"
    if any(token in hay for token in ("квитанц", "kvitan", "receipt")):
        return "payment_receipt"
    if any(
        token in hay
        for token in ("заявлен", "zayavl", "application", "анкет")
    ):
        return "banking_application"
    if any(
        token in hay
        for token in ("прописк", "регистрац", "место жительства", "residence")
    ):
        return "passport"
    voted = detect_document_type_from_pages([text], filename=filename)
    if voted != "unknown":
        return voted
    return "unknown"


def _schema_keys_for(doc_type: str, field_schema: Mapping[str, Any] | None = None) -> set[str]:
    keys: set[str] = set()
    raw = field_schema or {}
    nested = raw.get("fields") if isinstance(raw.get("fields"), Mapping) else raw
    if isinstance(nested, Mapping):
        keys.update(str(name) for name in nested if name != "fields")
    if not doc_type or doc_type in {"unknown", ""}:
        return keys
    try:
        from ocr.templates_registry import template_schema_for

        keys.update(str(name) for name in (template_schema_for(doc_type).get("fields") or {}))
    except Exception:
        pass
    return keys


def extract_fields(
    text: str,
    *,
    document_type: str | None = None,
    filename: str = "",
    pages: list[str] | None = None,
    field_schema: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, FieldValue]]:
    page_texts = [item for item in (pages or [text]) if item and item.strip()]
    combined = "\n\n".join(page_texts) or text
    requested = None if is_open_ended_doc_type(document_type) else document_type
    doc_type = requested or detect_document_type(combined, filename)
    if doc_type == "unknown":
        doc_type = detect_document_type_from_pages(page_texts or [combined], filename)
    forced = bool(requested)
    labeled = extract_labeled_fields(combined)
    generic = {} if forced else extract_generic_fields(combined)
    page_kind = detect_page_kind(combined)
    extractor = _EXTRACTORS.get(doc_type)
    specialist: dict[str, FieldValue] = {}
    if extractor is extract_passport_fields:
        specialist = extract_passport_fields(
            combined,
            allow_name_guess=page_kind
            not in {"passport_registration", "passport_children"},
        )
    elif extractor is not None:
        specialist = extractor(combined)
    if page_kind == "passport_registration" or doc_type == "passport":
        specialist = merge_field_maps(
            extract_registration_fields(combined),
            specialist,
        )
        if page_kind == "passport_registration":
            for key in ("full_name", "surname", "given_name", "patronymic"):
                specialist.pop(key, None)
                labeled.pop(key, None)
    if extractor is None and doc_type in {"unknown", ""}:
        guessed = extract_passport_fields(combined)
        if guessed.get("full_name") or guessed.get("document_number"):
            return "passport", collapse_extracted_fields(
                merge_field_maps(generic, labeled, guessed)
            )
    merged = collapse_extracted_fields(merge_field_maps(generic, labeled, specialist))
    if not merged and specialist:
        merged = specialist
    if "currency" not in merged:
        currency = re.search(r"\b(BYN|USD|EUR|RUB)\b", combined, re.I)
        if currency:
            merged["currency"] = _field(
                currency.group(1).upper(),
                0.88,
                source="token",
            )
    if doc_type in {"unknown", ""} and merged:
        voted = detect_document_type_from_pages(page_texts or [combined], filename)
        if voted != "unknown":
            doc_type = voted
    allowed = _schema_keys_for(doc_type, field_schema)
    if allowed and (forced or field_schema):
        merged = {key: value for key, value in merged.items() if key in allowed}
    return doc_type or "unknown", merged


def fields_as_plain(fields: Mapping[str, FieldValue]) -> dict[str, Any]:
    """Flatten `{value, confidence}` for validators that accept either form."""
    plain: dict[str, Any] = {}
    for key, payload in fields.items():
        if isinstance(payload, Mapping) and "value" in payload:
            plain[key] = payload
        else:
            plain[key] = payload
    return dict(plain)
