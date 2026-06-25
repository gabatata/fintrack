"""
Parser genérico para extratos de cartão.
Usa heurísticas e regex para identificar lançamentos em qualquer layout.
Funciona como fallback quando não há parser específico.
"""
from __future__ import annotations
import re
from typing import Optional
from .base_parser import BaseParser, RawTransaction
from utils.helpers import parse_date, parse_amount, normalize_text
from utils.logger import get_logger

log = get_logger(__name__)

# Padrões regex para datas brasileiras
DATE_PATTERNS = [
    r"\b(\d{2}/\d{2}/\d{4})\b",
    r"\b(\d{2}/\d{2}/\d{2})\b",
    r"\b(\d{2}-\d{2}-\d{4})\b",
    r"\b(\d{4}-\d{2}-\d{2})\b",
]

# Padrões para valores monetários
AMOUNT_PATTERNS = [
    r"R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?)",
    r"\b([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})\b",
    r"\b([0-9]+\.[0-9]{2})\b",
]

# Padrões de parcela (ex: "3/12", "03 de 12")
INSTALLMENT_PATTERN = re.compile(
    r"(?:parc(?:ela)?\.?\s*)?(\d{1,2})[/\s](?:de\s)?(\d{1,2})",
    re.IGNORECASE
)

# Indicadores de crédito/estorno
CREDIT_KEYWORDS = re.compile(
    r"\b(pagamento|estorno|crédito|credito|reembolso|devolução|cashback)\b",
    re.IGNORECASE
)


class GenericParser(BaseParser):
    """
    Parser genérico baseado em regex.
    Extrai lançamentos analisando linha a linha o texto do PDF.
    """
    name = "Generic"

    def can_parse(self, text: str, filename: str = "") -> bool:
        # Parser genérico sempre tenta
        return True

    def parse_text(self, pages_text: list[str]) -> list[RawTransaction]:
        transactions = []
        for page_num, text in enumerate(pages_text, 1):
            lines = text.splitlines()
            page_txs = self._parse_lines(lines, page_num)
            transactions.extend(page_txs)
            log.debug(f"Página {page_num}: {len(page_txs)} lançamentos encontrados")

        log.info(f"GenericParser: {len(transactions)} lançamentos extraídos")
        return transactions

    def _parse_lines(self, lines: list[str], page_num: int) -> list[RawTransaction]:
        """
        Analisa linhas da página tentando encontrar padrão:
        DATA  DESCRIÇÃO  VALOR
        """
        transactions = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or len(line) < 8:
                i += 1
                continue

            # Pula linhas que parecem cabeçalhos de tabela
            if self._is_header_line(line):
                i += 1
                continue

            tx = self._try_parse_line(line, page_num)
            if tx is None:
                # Tenta combinar com próxima linha (descrição pode estar na linha seguinte)
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not self._is_header_line(next_line):
                        combined = line + " " + next_line
                        tx = self._try_parse_line(combined, page_num)
                        if tx:
                            i += 1  # Pula a próxima linha

            if tx:
                tx.account_label = tx.account_label or self.account_label
                transactions.append(tx)
            i += 1

        return transactions

    # Palavras que indicam linha de cabeçalho de tabela
    _HEADER_WORDS = re.compile(
        r"^(data|date|descrição|description|estabelecimento|valor|amount|lancamento|historico)\b",
        re.IGNORECASE,
    )

    def _is_header_line(self, line: str) -> bool:
        """Retorna True se a linha parece ser um cabeçalho de tabela."""
        return bool(self._HEADER_WORDS.match(line.strip()))

    def _try_parse_line(self, line: str, page_num: int) -> Optional[RawTransaction]:
        """
        Tenta extrair um lançamento de uma linha de texto.
        Retorna None se não conseguir.
        """
        # Extrai data
        date_str = self._extract_date(line)
        if not date_str:
            return None

        # Extrai valor
        amount, amount_raw = self._extract_amount(line)
        if amount is None:
            return None

        # Extrai descrição (tudo que não é data e não é valor)
        description = self._extract_description(line, date_str, amount_raw)
        if not description or len(description) < 3:
            return None

        # Verifica tipo (débito ou crédito)
        tx_type = "credit" if CREDIT_KEYWORDS.search(description) else "debit"

        # Extrai parcela se houver
        inst_current, inst_total = self._extract_installment(description)

        return RawTransaction(
            tx_date=date_str,
            description_raw=description.strip(),
            amount=amount,
            tx_type=tx_type,
            installment_current=inst_current,
            installment_total=inst_total,
            page_number=page_num,
            raw_line=line,
        )

    def _extract_date(self, line: str) -> Optional[str]:
        for pattern in DATE_PATTERNS:
            m = re.search(pattern, line)
            if m:
                from utils.helpers import parse_date
                parsed = parse_date(m.group(1))
                if parsed:
                    return parsed
        return None

    def _extract_amount(self, line: str) -> tuple[Optional[float], str]:
        """Retorna (valor_float, string_original_do_valor)."""
        for pattern in AMOUNT_PATTERNS:
            m = re.search(pattern, line)
            if m:
                raw = m.group(0)
                val = parse_amount(raw)
                if val and val > 0:
                    return val, raw
        return None, ""

    def _extract_description(self, line: str, date_raw: str, amount_raw: str) -> str:
        """Remove data e valor da linha; o restante é a descrição."""
        text = line
        # Remove data
        for pat in DATE_PATTERNS:
            text = re.sub(pat, "", text, count=1)
        # Remove valor
        if amount_raw:
            text = text.replace(amount_raw, "", 1)
        # Remove "R$" solto
        text = re.sub(r"R\$", "", text)
        # Limpa espaços e caracteres residuais
        text = re.sub(r"\s+", " ", text).strip(" -|./,:")
        return text

    def _extract_installment(self, text: str) -> tuple[Optional[int], Optional[int]]:
        m = INSTALLMENT_PATTERN.search(text)
        if m:
            try:
                return int(m.group(1)), int(m.group(2))
            except (ValueError, IndexError):
                pass
        return None, None
