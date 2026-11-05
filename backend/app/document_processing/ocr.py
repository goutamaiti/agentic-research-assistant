"""OCR fallback for pages without a usable text layer (Tesseract via pytesseract)."""

from __future__ import annotations

import io
import logging
import shutil
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class OcrError(RuntimeError):
    """OCR was attempted but failed."""


@dataclass(slots=True)
class OcrLine:
    text: str
    y0: float  # in image pixels
    y1: float


@dataclass(slots=True)
class OcrResult:
    lines: list[OcrLine]
    mean_confidence: float | None  # Tesseract word confidence, 0-100; not a probability


class OcrEngine(Protocol):
    def is_available(self) -> bool: ...

    def recognize(self, png_bytes: bytes) -> OcrResult: ...


class TesseractOcr:
    """Runs the Tesseract binary through pytesseract. The binary is a system install."""

    def __init__(self, tesseract_cmd: str | None = None, language: str = "eng") -> None:
        self._cmd = tesseract_cmd
        self._language = language
        self._available: bool | None = None

    def _resolved_cmd(self) -> str | None:
        return self._cmd or shutil.which("tesseract")

    def is_available(self) -> bool:
        if self._available is None:
            cmd = self._resolved_cmd()
            if cmd is None:
                self._available = False
            else:
                import pytesseract

                pytesseract.pytesseract.tesseract_cmd = cmd
                try:
                    pytesseract.get_tesseract_version()
                    self._available = True
                except Exception as exc:  # binary present but unusable
                    logger.warning("Tesseract not usable: %s", type(exc).__name__)
                    self._available = False
        return self._available

    def recognize(self, png_bytes: bytes) -> OcrResult:
        if not self.is_available():
            raise OcrError("Tesseract is not available")
        import pytesseract
        from PIL import Image

        try:
            with Image.open(io.BytesIO(png_bytes)) as image:
                data = pytesseract.image_to_data(
                    image, lang=self._language, output_type=pytesseract.Output.DICT
                )
        except Exception as exc:
            raise OcrError(f"Tesseract failed: {type(exc).__name__}") from exc
        return _lines_from_tesseract(data)


def _lines_from_tesseract(data: dict[str, list]) -> OcrResult:
    """Group Tesseract word boxes into lines, keeping reading order."""
    lines: dict[tuple[int, int, int], list[int]] = {}
    confidences: list[float] = []
    for i, word in enumerate(data["text"]):
        if not str(word).strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(i)
        conf = float(data["conf"][i])
        if conf >= 0:
            confidences.append(conf)
    result: list[OcrLine] = []
    for indices in lines.values():
        words = [str(data["text"][i]).strip() for i in indices]
        tops = [data["top"][i] for i in indices]
        bottoms = [data["top"][i] + data["height"][i] for i in indices]
        result.append(OcrLine(text=" ".join(words), y0=min(tops), y1=max(bottoms)))
    mean = sum(confidences) / len(confidences) if confidences else None
    return OcrResult(lines=result, mean_confidence=mean)
