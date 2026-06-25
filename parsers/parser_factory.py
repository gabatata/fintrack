"""
Fábrica de parsers.
Seleciona automaticamente o parser mais adequado para cada PDF.
Ordem de prioridade: específico > genérico.
"""
from __future__ import annotations
from pathlib import Path
from .base_parser import BaseParser, RawTransaction
from .generic_parser import GenericParser
from .nubank_parser import NubankParser
from .mercadopago_parser import MercadoPagoParser
from .bradesco_parser import BradescoParser
from utils.logger import get_logger

log = get_logger(__name__)

# Registrar parsers específicos aqui (ordem = prioridade)
SPECIFIC_PARSERS: list[type[BaseParser]] = [
    MercadoPagoParser,
    BradescoParser,
    NubankParser,
    # ItauParser,      # a implementar no futuro
    # BradescoParse,   # a implementar no futuro
    # BrasilParser,    # a implementar no futuro
    # CaixaParser,     # a implementar no futuro
    # SantanderParser, # a implementar no futuro
]


def get_parser(pages_text: list[str], filename: str = "", account_label: str = "") -> BaseParser:
    """
    Analisa o texto do PDF e retorna o parser mais adequado.
    Testa cada parser específico; se nenhum se encaixar, usa o genérico.
    """
    sample_text = "\n".join(pages_text[:3])  # Primeiras 3 páginas para detecção

    for ParserClass in SPECIFIC_PARSERS:
        parser = ParserClass(account_label=account_label)
        if parser.can_parse(sample_text, filename):
            log.info(f"Parser selecionado: {parser.name}")
            return parser

    log.info("Nenhum parser específico encontrado — usando GenericParser")
    return GenericParser(account_label=account_label)


def parse_pdf(
    pdf_path: Path,
    pages_text: list[str],
    account_label: str = "",
) -> list[RawTransaction]:
    """
    Ponto de entrada principal do pipeline de parsing.
    Seleciona o parser e extrai os lançamentos.
    """
    parser = get_parser(pages_text, pdf_path.name, account_label)
    transactions = parser.parse_text(pages_text)
    return transactions
