"""
Parser específico para extratos do Nubank.
O Nubank exporta PDFs com estrutura relativamente consistente.
"""
from __future__ import annotations
import re
from .base_parser import BaseParser, RawTransaction
from utils.helpers import parse_date, parse_amount
from utils.logger import get_logger

log = get_logger(__name__)

# Nubank costuma ter "Nubank" no PDF ou nome do arquivo
NUBANK_MARKERS = ["nubank", "nu pagamentos", "nu bank"]

# Padrão típico do Nubank: "12 JAN 2024 Nome do Estabelecimento 123,45"
# Ou:                        "12/01/2024 Nome do Estabelecimento R$ 123,45"
NUBANK_LINE = re.compile(
    r"^(\d{2}\s+\w{3}(?:\s+\d{4})?|\d{2}/\d{2}/\d{4})\s+(.+?)\s+([\d.,]+)$",
    re.IGNORECASE
)

MONTHS_PT = {
    "jan": "01", "fev": "02", "mar": "03", "abr": "04",
    "mai": "05", "jun": "06", "jul": "07", "ago": "08",
    "set": "09", "out": "10", "nov": "11", "dez": "12",
}


class NubankParser(BaseParser):
    name = "Nubank"
    supported_institutions = ["nubank", "nu pagamentos"]

    def can_parse(self, text: str, filename: str = "") -> bool:
        combined = (text + " " + filename).lower()
        return any(marker in combined for marker in NUBANK_MARKERS)

    def parse_text(self, pages_text: list[str]) -> list[RawTransaction]:
        full_text = "\n".join(pages_text)
        lines = full_text.splitlines()
        transactions = []

        # Detecta o ano de referência do extrato
        year = self._detect_year(full_text)

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            tx = self._parse_nubank_line(line, year, i + 1)
            if tx:
                tx.account_label = tx.account_label or self.account_label or "Nubank"
                transactions.append(tx)

        log.info(f"NubankParser: {len(transactions)} lançamentos extraídos")
        return transactions

    def _parse_nubank_line(self, line: str, year: int, page_num: int):
        """Interpreta uma linha no formato do Nubank."""
        m = NUBANK_LINE.match(line)
        if not m:
            return None

        date_raw, desc, amount_raw = m.group(1), m.group(2), m.group(3)
        date_str = self._parse_nubank_date(date_raw, year)
        if not date_str:
            return None

        amount = parse_amount(amount_raw)
        if not amount:
            return None

        # Detecta crédito/pagamento
        tx_type = "credit" if re.search(
            r"pagamento|estorno|crédito", desc, re.IGNORECASE
        ) else "debit"

        return RawTransaction(
            tx_date=date_str,
            description_raw=desc.strip(),
            amount=amount,
            tx_type=tx_type,
            page_number=page_num,
            raw_line=line,
        )

    def _parse_nubank_date(self, raw: str, year: int) -> str | None:
        """Interpreta datas como '12 JAN' ou '12/01/2024'."""
        raw = raw.strip()
        # Formato DD/MM/YYYY
        parsed = parse_date(raw)
        if parsed:
            return parsed

        # Formato "DD MMM" ou "DD MMM YYYY"
        m = re.match(r"(\d{2})\s+(\w{3})(?:\s+(\d{4}))?", raw, re.IGNORECASE)
        if m:
            day = m.group(1)
            month = MONTHS_PT.get(m.group(2).lower())
            yr = m.group(3) or str(year)
            if month:
                return f"{yr}-{month}-{day}"
        return None

    def _detect_year(self, text: str) -> int:
        """Tenta detectar o ano de referência do extrato."""
        m = re.search(r"\b(20\d{2})\b", text)
        if m:
            return int(m.group(1))
        from datetime import datetime
        return datetime.now().year
