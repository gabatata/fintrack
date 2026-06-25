"""
Parser base abstrato. Todos os parsers específicos herdam desta classe.
Define o contrato de parse e estrutura do lançamento.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class RawTransaction:
    """Representa um lançamento bruto extraído do PDF/OCR, antes de normalização."""
    tx_date: str                        # ISO 8601 ou string bruta
    description_raw: str               # descrição original
    amount: float                       # valor (sempre positivo)
    tx_type: str = "debit"             # debit | credit | reversal | fee
    installment_current: Optional[int] = None
    installment_total: Optional[int] = None
    account_label: Optional[str] = None
    page_number: Optional[int] = None  # para debug
    raw_line: Optional[str] = None     # linha original do PDF

    def to_dict(self) -> dict:
        return {
            "tx_date": self.tx_date,
            "description_raw": self.description_raw,
            "amount": self.amount,
            "tx_type": self.tx_type,
            "installment_current": self.installment_current,
            "installment_total": self.installment_total,
            "account_label": self.account_label,
        }


class BaseParser(ABC):
    """
    Parser base. Implementa lógica comum de extração e define
    interface que parsers específicos devem implementar.
    """
    name: str = "Generic"
    supported_institutions: list[str] = []

    def __init__(self, account_label: str = ""):
        self.account_label = account_label

    @abstractmethod
    def can_parse(self, text: str, filename: str = "") -> bool:
        """Retorna True se este parser consegue lidar com o PDF."""
        ...

    @abstractmethod
    def parse_text(self, pages_text: list[str]) -> list[RawTransaction]:
        """
        Recebe lista de textos (uma por página) e retorna lista de lançamentos.
        """
        ...

    def parse_file(self, pdf_path: Path) -> list[RawTransaction]:
        """
        Método conveniente: extrai texto e chama parse_text.
        Subclasses podem sobrescrever para lógica especial.
        """
        from parsers.pdf_reader import extract_text_from_pdf
        pages_text, _ = extract_text_from_pdf(pdf_path)
        return self.parse_text(pages_text)
