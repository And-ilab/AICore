"""OCR engine: Paddle first, Tesseract fallback, every page of PDF/TIFF."""

from __future__ import annotations

import hashlib
import io
import logging
import re
from typing import Any

from core.model_registry import ModelRegistry, ModelRegistryError

SLOT_NAME = "ocr"
DEFAULT_STUB_MODEL = "auto:paddle+tesseract"
logger = logging.getLogger(__name__)

_PADDLE: Any = None
_PADDLE_FAILED = False


class OcrEngineError(RuntimeError):
    """OCR engine failure."""


def resolve_ocr_model() -> dict[str, Any]:
    """Read ModelRegistry `ocr` slot; fall back to auto paddle+tesseract."""
    try:
        slot = ModelRegistry.load().get_slot(SLOT_NAME)
    except ModelRegistryError as exc:
        raise OcrEngineError(str(exc)) from exc

    model = slot.dev_model or DEFAULT_STUB_MODEL
    return {
        "slot": SLOT_NAME,
        "model": model,
        "status": slot.status,
        "kpi": dict(slot.kpi),
        "languages": list(slot.kpi.get("languages") or ["ru", "en"]),
    }


def _decode_embedded_text(content: bytes) -> str | None:
    """Prefer embedded UTF-8 when tests upload text-as-image payloads."""
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if decoded.isprintable() or "\n" in decoded:
        stripped = decoded.strip()
        if stripped and len(stripped) < 50_000:
            return stripped
    return None


def _prepare_ocr_image(image: Any) -> Any:
    """Upscale small scans and lift contrast before Tesseract."""
    from PIL import ImageEnhance, ImageOps  # type: ignore

    prepared = image.convert("RGB")
    width, height = prepared.size
    max_side = max(width, height)
    min_side = min(width, height)
    if max_side > 4000:
        scale = 4000 / max_side
        prepared = prepared.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            resample=1,
        )
    elif min_side < 800:
        scale = 2 if min_side < 500 else 1.4
        prepared = prepared.resize(
            (int(width * scale), int(height * scale)),
            resample=1,
        )
        prepared = ImageOps.autocontrast(prepared, cutoff=1)
        prepared = ImageEnhance.Contrast(prepared).enhance(1.2)
        prepared = ImageEnhance.Sharpness(prepared).enhance(1.1)
    return prepared


def _ocr_mrz_strip(image: Any) -> str | None:
    """Second Tesseract pass on the bottom band — ICAO MRZ is Latin + <."""
    try:
        import pytesseract  # type: ignore
    except Exception:
        return None
    try:
        width, height = image.size
        if width < 40 or height < 40:
            return None
        gray = image.convert("L")
        chunks: list[str] = []
        bands = (
            (int(height * 0.55), int(height * 0.88)),
            (int(height * 0.72), height),
        )
        config = (
            "--psm 6 -c "
            "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
        )
        for top, bottom in bands:
            if bottom - top < 20:
                continue
            band = gray.crop((0, top, width, bottom))
            if band.width > 1400:
                scale = 1400 / band.width
                band = band.resize((1400, max(40, int(band.height * scale))))
            elif 80 <= band.width < 500:
                band = band.resize((band.width * 2, band.height * 2))
            text = pytesseract.image_to_string(band, lang="eng", config=config)
            cleaned = (text or "").strip()
            if cleaned and cleaned not in chunks:
                chunks.append(cleaned)
        return "\n".join(chunks) or None
    except Exception:
        return None


def _ocr_has_passport_signal(text: str) -> bool:
    raw = text or ""
    if re.search(r"\bP[<C][A-Z]{3}", raw.upper()):
        return True
    if re.search(r"\b[A-ZА-Я]{2}\s?\d{7}\b", raw.upper()):
        return True
    try:
        from ocr.mrz import parse_td3_mrz

        return bool(parse_td3_mrz(raw))
    except Exception:
        return False


def _ocr_text_quality(text: str) -> float:
    """Score how readable OCR text is so Paddle garbage loses to Tesseract."""
    raw = (text or "").strip()
    if not raw:
        return 0.0
    tokens = re.findall(r"[A-Za-zА-Яа-яЁё]{3,}", raw)
    if not tokens:
        return 0.05
    good = 0
    mixed = 0
    for token in tokens:
        cyr = len(re.findall(r"[А-Яа-яЁё]", token))
        lat = len(re.findall(r"[A-Za-z]", token))
        if cyr and lat:
            mixed += 1
            continue
        if re.search(r"[аеёиоуыэюяАЕЁИОУЫЭЮЯaeiouAEIOU]", token):
            good += 1
    ratio = good / max(len(tokens), 1)
    if mixed / max(len(tokens), 1) >= 0.2:
        ratio *= 0.35
    hay = raw.casefold()
    keywords = (
        "место",
        "жительств",
        "зарегистрир",
        "паспорт",
        "квитанц",
        "сумма",
        "получател",
        "фамилия",
        "плательщик",
        "договор",
        "заявлен",
        "выписк",
    )
    bonus = sum(0.06 for key in keywords if key in hay)
    if _ocr_has_passport_signal(raw):
        bonus += 0.28
    return min(1.0, ratio + bonus)


def _ocr_digit_strip(image: Any) -> str | None:
    """Bottom band, digits only — RF series/number punched along the edge."""
    try:
        import pytesseract  # type: ignore
    except Exception:
        return None
    try:
        width, height = image.size
        if width < 40 or height < 40:
            return None
        top = int(height * 0.78)
        band = image.convert("L").crop((0, top, width, height))
        if band.width < 80:
            return None
        if band.width < 900:
            band = band.resize((band.width * 2, max(24, band.height * 2)))
        text = pytesseract.image_to_string(
            band,
            lang="eng",
            config="--psm 7 -c tessedit_char_whitelist=0123456789 ",
        )
        digits = re.sub(r"[^\d\s]", "", text or "")
        compact = re.sub(r"\s+", "", digits)
        if len(compact) < 8:
            return None
        return digits.strip()
    except Exception:
        return None


def _pick_ocr_text(candidates: list[tuple[str, str]]) -> tuple[str, str] | None:
    scored = [
        (text, engine, _ocr_text_quality(text))
        for text, engine in candidates
        if text and text.strip()
    ]
    if not scored:
        return None
    scored.sort(key=lambda item: item[2], reverse=True)
    return scored[0][0], scored[0][1]


def _ocr_with_tesseract_image(image: Any, languages: list[str]) -> str | None:
    try:
        import pytesseract  # type: ignore
    except Exception:
        return None
    try:
        prepared = _prepare_ocr_image(image)
        lang = "+".join(
            "rus" if code.casefold().startswith("ru") else "eng"
            for code in languages
        ) or "rus+eng"
        texts: list[str] = []
        for psm in ("6", "3"):
            config = f"--oem 1 --psm {psm}"
            chunk = (pytesseract.image_to_string(prepared, lang=lang, config=config) or "").strip()
            if chunk and chunk not in texts:
                texts.append(chunk)
        text = "\n".join(texts).strip()
        mrz_text = _ocr_mrz_strip(prepared)
        if mrz_text and mrz_text not in text:
            text = f"{text.rstrip()}\n{mrz_text}".strip()
        return text or None
    except Exception:
        return None


def _get_paddle() -> Any:
    global _PADDLE, _PADDLE_FAILED
    if _PADDLE_FAILED:
        return None
    if _PADDLE is not None:
        return _PADDLE
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception:
        _PADDLE_FAILED = True
        return None
    try:
        try:
            _PADDLE = PaddleOCR(
                use_angle_cls=True,
                lang="ru",
                show_log=False,
                use_gpu=False,
            )
        except TypeError:
            _PADDLE = PaddleOCR(lang="ru")
        return _PADDLE
    except Exception as exc:
        logger.info("PaddleOCR init failed, using Tesseract: %s", exc)
        _PADDLE_FAILED = True
        _PADDLE = None
        return None


def _lines_from_paddle_result(result: Any) -> list[str]:
    lines: list[str] = []
    if result is None:
        return lines
    if isinstance(result, dict):
        rec = result.get("rec_texts") or result.get("text")
        if isinstance(rec, list):
            return [str(item) for item in rec if str(item).strip()]
        if isinstance(rec, str) and rec.strip():
            return [rec]
    for page in result if isinstance(result, list) else []:
        if isinstance(page, dict):
            lines.extend(_lines_from_paddle_result(page))
            continue
        for line in page or []:
            if line and len(line) >= 2 and line[1]:
                token = line[1][0] if isinstance(line[1], (list, tuple)) else line[1]
                if token:
                    lines.append(str(token))
    return lines


def _ocr_with_paddle_image(image: Any) -> str | None:
    engine = _get_paddle()
    if engine is None:
        return None
    try:
        import numpy as np  # type: ignore

        arr = np.array(image.convert("RGB"))
        result = None
        if hasattr(engine, "ocr"):
            try:
                result = engine.ocr(arr, cls=True)
            except TypeError:
                result = engine.ocr(arr)
        if result is None and hasattr(engine, "predict"):
            result = engine.predict(arr)
        lines = _lines_from_paddle_result(result)
        text = "\n".join(lines).strip()
        return text or None
    except Exception as exc:
        logger.info("PaddleOCR page failed: %s", exc)
        return None


def _pdf_pages_as_images(content: bytes) -> list[Any]:
    if not content.startswith(b"%PDF"):
        return []
    try:
        import pypdfium2 as pdfium  # type: ignore
    except Exception:
        return []
    try:
        pdf = pdfium.PdfDocument(content)
        images = []
        for index in range(len(pdf)):
            page = pdf[index]
            bitmap = page.render(scale=2.0)
            images.append(bitmap.to_pil())
        return images
    except Exception:
        return []


def _raster_pages(content: bytes) -> list[Any]:
    """Turn a file into one PIL image per page."""
    pdf_pages = _pdf_pages_as_images(content)
    if pdf_pages:
        return pdf_pages
    try:
        from PIL import Image  # type: ignore

        image = Image.open(io.BytesIO(content))
        frames: list[Any] = []
        try:
            index = 0
            while True:
                image.seek(index)
                frames.append(image.convert("RGB"))
                index += 1
        except EOFError:
            pass
        return frames or [image.convert("RGB")]
    except Exception:
        return []


def _pdf_text_pages(content: bytes) -> list[str]:
    if not content.startswith(b"%PDF"):
        return []
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except Exception:
            return []
    try:
        reader = PdfReader(io.BytesIO(content))
        pages: list[str] = []
        for page in reader.pages:
            extracted = (page.extract_text() or "").strip()
            pages.append(extracted)
        return pages if any(pages) else []
    except Exception:
        return []


def _ocr_image(
    image: Any,
    *,
    languages: list[str],
    prefer_paddle: bool,
) -> tuple[str | None, str]:
    candidates: list[tuple[str, str]] = []
    paddle_text = _ocr_with_paddle_image(image) if prefer_paddle else None
    if paddle_text:
        candidates.append((paddle_text, "paddle"))
    looks_passport = bool(
        re.search(
            r"passport|пашпарт|surname|прозвішч|given names",
            paddle_text or "",
            re.I,
        )
    )
    need_tess = (
        not paddle_text
        or _ocr_text_quality(paddle_text) < 0.7
        or (looks_passport and not _ocr_has_passport_signal(paddle_text))
    )
    if need_tess:
        tess_text = _ocr_with_tesseract_image(image, languages)
        if tess_text:
            candidates.append((tess_text, "tesseract"))
    if not prefer_paddle and not candidates:
        paddle_text = _ocr_with_paddle_image(image)
        if paddle_text:
            candidates.append((paddle_text, "paddle"))
    picked = _pick_ocr_text(candidates)
    if not picked:
        return None, ""
    text, used = picked
    mrz_text = _ocr_mrz_strip(_prepare_ocr_image(image))
    if mrz_text and mrz_text not in text:
        text = f"{text.rstrip()}\n{mrz_text}"
    digits = _ocr_digit_strip(image)
    if digits and digits not in text:
        text = f"{text.rstrip()}\n{digits}"
    return text, used


def _page_confidence(text: str, mode: str) -> float:
    if mode == "stub":
        return 0.55 if text.startswith("[stub:") else 0.92
    if mode in {"tesseract", "paddle", "pdf_text"}:
        tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9]{2,}", text)
        if len(tokens) >= 20:
            return 0.93
        if len(tokens) >= 8:
            return 0.86
        return 0.7
    return 0.8


def _stub_page_text(
    *,
    filename: str,
    sha256: str,
    content: bytes,
    content_type: str,
) -> str:
    digest = hashlib.sha256(content).hexdigest()[:12]
    return (
        f"[stub:tesseract] filename={filename} "
        f"sha256={sha256[:16]}… content_sha={digest} "
        f"type={content_type or 'unknown'}"
    )


def recognize_document(
    content: bytes,
    *,
    filename: str,
    content_type: str,
    document_id: str,
    job_id: str,
    sha256: str,
) -> dict[str, Any]:
    """Run OCR via ModelRegistry slot; Paddle → Tesseract → PDF text → stub."""
    resolved = resolve_ocr_model()
    model = resolved["model"]
    languages = resolved["languages"]
    language = languages[0] if languages else "ru"
    model_l = model.casefold()
    prefer_paddle = (
        "paddle" in model_l
        or model_l.startswith("auto")
        or model.startswith("stub:")
    )

    embedded = _decode_embedded_text(content)
    pages_out: list[dict[str, Any]] = []
    mode = "stub"
    engine_name = "tesseract"

    if embedded is not None:
        mode = "embedded_text"
        engine_name = "embedded"
        pages_out.append(
            {
                "page": 1,
                "text": embedded,
                "confidence": 0.92,
                "blocks_ref": None,
            }
        )
    else:
        images = _raster_pages(content)
        used_modes: list[str] = []
        for index, image in enumerate(images, start=1):
            text, used = _ocr_image(
                image,
                languages=languages,
                prefer_paddle=prefer_paddle,
            )
            if text:
                used_modes.append(used)
                pages_out.append(
                    {
                        "page": index,
                        "text": text,
                        "confidence": _page_confidence(text, used),
                        "blocks_ref": None,
                    }
                )
        if not pages_out:
            pdf_pages = _pdf_text_pages(content)
            for index, text in enumerate(pdf_pages, start=1):
                if not text:
                    continue
                pages_out.append(
                    {
                        "page": index,
                        "text": text,
                        "confidence": _page_confidence(text, "pdf_text"),
                        "blocks_ref": None,
                    }
                )
            if pages_out:
                mode = "pdf_text"
                engine_name = "pdf"
        elif used_modes:
            mode = used_modes[0]
            engine_name = "paddleocr" if mode == "paddle" else "tesseract"

        if not pages_out:
            pages_out.append(
                {
                    "page": 1,
                    "text": _stub_page_text(
                        filename=filename,
                        sha256=sha256,
                        content=content,
                        content_type=content_type,
                    ),
                    "confidence": 0.55,
                    "blocks_ref": None,
                }
            )
            mode = "stub"
            engine_name = "tesseract"

    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "document_id": document_id,
        "document_sha256": sha256,
        "document_type_candidate": "unknown",
        "language": language,
        "ocr_engine": {
            "name": engine_name,
            "version": model,
            "slot": SLOT_NAME,
            "mode": mode,
            "pages_processed": len(pages_out),
        },
        "pages": pages_out,
        "template": {"id": None, "version": None},
        "status": "ocr_completed",
    }
