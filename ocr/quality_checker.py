"""
Verifica a qualidade do texto extraído diretamente de um PDF.
Decide se o OCR é necessário ou não.
"""
import re
from utils.logger import get_logger

log = get_logger(__name__)

# Mínimo de caracteres legíveis por página para considerar sem OCR
MIN_CHARS_PER_PAGE = 50
# Mínimo de densidade de texto legível (letras+dígitos / total)
MIN_READABLE_RATIO = 0.6


def text_quality_score(text: str) -> float:
    """
    Retorna um score 0.0–1.0 indicando a qualidade do texto.
    Score alto = texto legível; baixo = precisa de OCR.
    """
    if not text or len(text.strip()) < 10:
        return 0.0

    total = len(text)
    readable = len(re.findall(r"[a-zA-Z0-9À-ú]", text))
    ratio = readable / total if total > 0 else 0.0
    return ratio


def needs_ocr(pages_text: list[str]) -> bool:
    """
    Recebe lista de textos (um por página) e decide se OCR é necessário.
    Retorna True se a maioria das páginas tiver texto insuficiente.
    """
    if not pages_text:
        return True

    needs = 0
    for text in pages_text:
        score = text_quality_score(text)
        char_count = len(text.strip())
        if score < MIN_READABLE_RATIO or char_count < MIN_CHARS_PER_PAGE:
            needs += 1
            log.debug(f"Página com baixa qualidade: score={score:.2f}, chars={char_count}")

    ratio = needs / len(pages_text)
    log.info(f"Páginas que precisam de OCR: {needs}/{len(pages_text)} ({ratio:.0%})")
    return ratio > 0.4  # Se +40% das páginas forem ruins, usa OCR
