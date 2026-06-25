"""
Motor de OCR. Usa pytesseract como engine principal com fallback gracioso.
Pipeline: PDF -> Imagem -> Pré-processamento -> Tesseract -> Texto
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from utils.logger import get_logger
from .preprocessor import preprocess_image

log = get_logger(__name__)

# Verifica disponibilidade do Tesseract
try:
    import os
    import shutil
    import pytesseract
    from PIL import Image
    # No Windows o tesseract normalmente nao esta no PATH: procura nos caminhos padrao
    if not shutil.which("tesseract"):
        for _p in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        ):
            if os.path.exists(_p):
                pytesseract.pytesseract.tesseract_cmd = _p
                break
    # Testa se o tesseract está instalado no sistema
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
    log.info("Tesseract OCR disponível.")
except Exception as e:
    TESSERACT_AVAILABLE = False
    log.warning(f"Tesseract não disponível: {e}. OCR desativado.")

# Configuração do Tesseract para documentos financeiros
TESSERACT_CONFIG = "--oem 3 --psm 6 -l por+eng"


def ocr_page_image(pil_image) -> str:
    """
    Aplica OCR em uma imagem PIL e retorna o texto extraído.
    """
    if not TESSERACT_AVAILABLE:
        raise RuntimeError(
            "Tesseract não está instalado. "
            "No Windows: winget install UB-Mannheim.TesseractOCR"
        )

    # Pré-processa para melhorar qualidade
    processed = preprocess_image(pil_image)

    text = pytesseract.image_to_string(processed, config=TESSERACT_CONFIG)
    return text


def ocr_pdf_file(pdf_path: str | Path) -> list[str]:
    """
    Aplica OCR em todas as páginas de um PDF.
    Retorna lista de textos (uma string por página).
    Estratégia: converte cada página para imagem via PyMuPDF ou pdf2image.
    """
    pdf_path = Path(pdf_path)
    pages_text = []

    # Tenta PyMuPDF (mais rápido)
    if _try_pymupdf_ocr(pdf_path, pages_text):
        return pages_text

    # Fallback: pdf2image + pytesseract
    if _try_pdf2image_ocr(pdf_path, pages_text):
        return pages_text

    log.error("Nenhum método de OCR disponível ou falhou.")
    return pages_text


def _try_pymupdf_ocr(pdf_path: Path, pages_text: list) -> bool:
    """Tenta OCR usando PyMuPDF para renderizar páginas."""
    try:
        import fitz
        from PIL import Image
        import io

        doc = fitz.open(str(pdf_path))
        log.info(f"OCR com PyMuPDF: {len(doc)} páginas")

        for i, page in enumerate(doc):
            mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            pil_img = Image.open(io.BytesIO(img_data))

            text = ocr_page_image(pil_img)
            pages_text.append(text)
            log.debug(f"Página {i+1}: {len(text)} caracteres via OCR")

        doc.close()
        return True
    except ImportError:
        log.debug("PyMuPDF não disponível, tentando pdf2image...")
        return False
    except Exception as e:
        log.error(f"Erro no OCR com PyMuPDF: {e}")
        return False


def _try_pdf2image_ocr(pdf_path: Path, pages_text: list) -> bool:
    """Tenta OCR usando pdf2image + pytesseract."""
    try:
        from pdf2image import convert_from_path

        log.info("OCR com pdf2image...")
        images = convert_from_path(str(pdf_path), dpi=300)

        for i, pil_img in enumerate(images):
            text = ocr_page_image(pil_img)
            pages_text.append(text)
            log.debug(f"Página {i+1}: {len(text)} caracteres via OCR")

        return True
    except ImportError:
        log.debug("pdf2image não disponível.")
        return False
    except Exception as e:
        log.error(f"Erro no OCR com pdf2image: {e}")
        return False


def is_ocr_available() -> bool:
    return TESSERACT_AVAILABLE
