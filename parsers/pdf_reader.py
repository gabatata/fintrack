"""
Extração de texto de PDFs usando pdfplumber como engine principal.
Tenta extração direta primeiro; sinaliza se OCR é necessário.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from utils.logger import get_logger
from ocr.quality_checker import needs_ocr, text_quality_score

log = get_logger(__name__)


def extract_text_from_pdf(pdf_path: Path) -> tuple[list[str], bool]:
    """
    Tenta extrair texto diretamente do PDF.
    Retorna (lista_de_textos_por_página, ocr_necessário).
    """
    pages_text = []
    ocr_needed = False

    # Tenta pdfplumber primeiro (melhor para PDFs com estrutura)
    if _try_pdfplumber(pdf_path, pages_text):
        pass
    # Fallback: pypdf
    elif _try_pypdf(pdf_path, pages_text):
        pass
    else:
        log.warning("Nenhuma biblioteca de PDF conseguiu extrair texto.")
        ocr_needed = True
        return pages_text, ocr_needed

    # Verifica qualidade do texto extraído
    if needs_ocr(pages_text):
        log.info("Qualidade do texto insuficiente — OCR necessário.")
        ocr_needed = True
    else:
        log.info(f"Texto extraído com sucesso: {len(pages_text)} páginas, OCR não necessário.")

    return pages_text, ocr_needed


def _try_pdfplumber(pdf_path: Path, pages_text: list) -> bool:
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages_text.append(text)
        log.debug(f"pdfplumber: {len(pages_text)} páginas extraídas.")
        return True
    except ImportError:
        log.debug("pdfplumber não disponível.")
        return False
    except Exception as e:
        log.error(f"Erro no pdfplumber: {e}")
        return False


def _try_pypdf(pdf_path: Path, pages_text: list) -> bool:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            text = page.extract_text() or ""
            pages_text.append(text)
        log.debug(f"pypdf: {len(pages_text)} páginas extraídas.")
        return True
    except ImportError:
        log.debug("pypdf não disponível.")
        return False
    except Exception as e:
        log.error(f"Erro no pypdf: {e}")
        return False


def extract_tables_from_pdf(pdf_path: Path) -> list[list[list[str]]]:
    """
    Tenta extrair tabelas usando pdfplumber (útil para extratos tabulados).
    Retorna lista de tabelas (lista de linhas, cada linha é lista de células).
    """
    tables = []
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)
        log.debug(f"pdfplumber tabelas: {len(tables)} tabelas encontradas.")
    except Exception as e:
        log.debug(f"Extração de tabelas falhou: {e}")
    return tables
