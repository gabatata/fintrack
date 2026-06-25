"""
Pré-processamento de imagem para melhorar a qualidade do OCR.
Usa OpenCV quando disponível, com fallback para Pillow.
"""
from __future__ import annotations
from typing import Any
from utils.logger import get_logger

log = get_logger(__name__)

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    log.warning("OpenCV não disponível. Pré-processamento básico será usado.")

try:
    from PIL import Image, ImageEnhance, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def preprocess_image(image: Any) -> Any:
    """
    Aplica pipeline de pré-processamento na imagem para melhorar OCR.
    Aceita PIL.Image ou numpy array.
    Retorna PIL.Image pronto para o tesseract.
    """
    if CV2_AVAILABLE:
        return _preprocess_cv2(image)
    elif PIL_AVAILABLE:
        return _preprocess_pil(image)
    return image


def _preprocess_cv2(pil_image):
    """Pipeline completo com OpenCV."""
    import numpy as np
    from PIL import Image

    # Converte PIL -> numpy
    img = np.array(pil_image.convert("RGB"))
    img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # 1) Melhora contraste com CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img = clahe.apply(img)

    # 2) Remove ruído
    img = cv2.fastNlMeansDenoising(img, h=10)

    # 3) Binarização adaptativa (lida bem com variações de iluminação)
    img = cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10
    )

    # 4) Dilatação leve para reconectar letras fragmentadas
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
    img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)

    # Converte de volta para PIL
    return Image.fromarray(img)


def _preprocess_pil(pil_image):
    """Pipeline básico com Pillow, sem OpenCV."""
    from PIL import Image, ImageEnhance, ImageFilter

    img = pil_image.convert("L")  # Escala de cinza

    # Aumenta contraste
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)

    # Nitidez
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(2.0)

    return img


def pdf_page_to_image(page, dpi: int = 300):
    """
    Converte uma página de pdfplumber para imagem PIL.
    Usa pdf2image/fitz se disponível.
    """
    try:
        import fitz  # PyMuPDF
        # page aqui seria um objeto fitz.Page
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        from PIL import Image
        return Image.frombytes("L", [pix.width, pix.height], pix.samples)
    except Exception:
        pass

    try:
        # Fallback: tenta via pdfplumber/pypdf com pdf2image
        from pdf2image import convert_from_path
        return None  # Será tratado no engine
    except Exception:
        pass

    return None
