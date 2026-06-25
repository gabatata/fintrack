"""
Parser específico para faturas do Cartão de Crédito Mercado Pago.

Formato das linhas de transação:
    DD/MM DESCRIÇÃO [Parcela X de Y] R$ VALOR
    Ex: 24/06 EC *MRAPRENDABITCOIN Parcela 9 de 12 R$ 100,83
    Ex: 02/02 MP*MELIMAIS R$ 19,90

Particularidades:
- Datas no formato DD/MM sem ano
- Ano inferido a partir da data de vencimento do extrato
- Parcelas de compras antigas podem ter meses de anos anteriores
- "Pagamento da fatura" é crédito, não débito
- Blocos separados por "Cartão Visa [****]"
"""
from __future__ import annotations
import re
from datetime import date
from .base_parser import BaseParser, RawTransaction
from utils.helpers import parse_amount
from utils.logger import get_logger

log = get_logger(__name__)

# Marcadores que identificam extrato do Mercado Pago
# Apenas termos que aparecem no CABECALHO da fatura, nao em lancamentos
MP_MARKERS = [
    "mercado pago", "mercadopago", "mp-card",
    "fatura de fevereiro", "fatura de janeiro", "fatura de marco",
    "fatura de abril", "fatura de maio", "fatura de junho",
    "fatura de julho", "fatura de agosto", "fatura de setembro",
    "fatura de outubro", "fatura de novembro", "fatura de dezembro",
    "ola, gabriel", "essa e sua fatura",
]

# Linha de transação: DD/MM + descrição + opcionalmente parcela + valor
TX_LINE = re.compile(
    r"^(\d{2}/\d{2})\s+(.+?)\s+R\$\s*([\d.,]+)\s*$"
)

# Parcela: "Parcela X de Y"
PARCELA = re.compile(r"Parcela\s+(\d+)\s+de\s+(\d+)", re.IGNORECASE)

# Linhas a ignorar
SKIP_PATTERNS = re.compile(
    r"^(Data\s+Movimenta|Cartão\s+Visa|Total\s+R\$|Gabriel|Vencimento|"
    r"Detalhes\s+de\s+consumo|Movimenta|^\s*$)",
    re.IGNORECASE,
)

# Palavras que indicam crédito/pagamento
CREDIT_KEYWORDS = re.compile(
    r"(pagamento\s+da\s+fatura|estorno|crédito\s+devolvido|reembolso)",
    re.IGNORECASE,
)

MONTHS_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}


class MercadoPagoParser(BaseParser):
    name = "MercadoPago"
    supported_institutions = ["mercado pago", "mp"]

    def can_parse(self, text: str, filename: str = "") -> bool:
        # Only check in first ~500 chars (header) + filename to avoid false positives
        # when Bradesco/Nubank statements contain MP transactions
        header = text[:800].lower()
        fname  = filename.lower()
        return any(m in header or m in fname for m in MP_MARKERS)

    def parse_text(self, pages_text: list[str]) -> list[RawTransaction]:
        full_text = "\n".join(pages_text)

        # Detecta data de vencimento para inferir o ano de referência
        vencimento_year, vencimento_month = self._detect_vencimento(full_text)
        log.info(
            f"MercadoPagoParser: vencimento {vencimento_month:02d}/{vencimento_year}"
        )

        transactions = []
        for page_num, page_text in enumerate(pages_text, 1):
            # Só processa páginas com transações (pág 2 em diante normalmente)
            if "Movimentações na fatura" not in page_text and \
               "Cartão Visa" not in page_text:
                continue
            page_txs = self._parse_page(
                page_text, vencimento_year, vencimento_month, page_num
            )
            transactions.extend(page_txs)

        log.info(f"MercadoPagoParser: {len(transactions)} lançamentos extraídos")
        return transactions

    def _parse_page(
        self,
        text: str,
        ref_year: int,
        ref_month: int,
        page_num: int,
    ) -> list[RawTransaction]:
        transactions = []
        lines = text.splitlines()

        for line in lines:
            line = line.strip()
            if not line or SKIP_PATTERNS.match(line):
                continue

            m = TX_LINE.match(line)
            if not m:
                continue

            date_raw = m.group(1)   # DD/MM
            desc_raw = m.group(2).strip()
            amount_raw = m.group(3)

            # Converte valor
            amount = parse_amount(amount_raw)
            if not amount:
                continue

            # Infere ano da data da transação
            try:
                day, month = map(int, date_raw.split("/"))
            except ValueError:
                continue

            year = self._infer_year(month, ref_year, ref_month)
            tx_date = f"{year}-{month:02d}-{day:02d}"

            # Valida data
            try:
                date(year, month, day)
            except ValueError:
                log.debug(f"Data inválida ignorada: {tx_date}")
                continue

            # Tipo de transação
            is_credit = bool(CREDIT_KEYWORDS.search(desc_raw))
            tx_type = "credit" if is_credit else "debit"

            # Parcelas
            pm = PARCELA.search(desc_raw)
            inst_current = int(pm.group(1)) if pm else None
            inst_total = int(pm.group(2)) if pm else None

            # Limpa "Parcela X de Y" da descrição
            desc_clean = PARCELA.sub("", desc_raw).strip()

            tx = RawTransaction(
                tx_date=tx_date,
                description_raw=desc_clean,
                amount=amount,
                tx_type=tx_type,
                installment_current=inst_current,
                installment_total=inst_total,
                account_label=self.account_label or "Mercado Pago",
                page_number=page_num,
                raw_line=line,
            )
            transactions.append(tx)

        return transactions

    def _detect_vencimento(self, text: str) -> tuple[int, int]:
        """
        Extrai a data de vencimento do extrato para uso como referência de ano.
        Retorna (ano, mês).
        """
        # "Vencimento: 05/03/2026" ou "Vence em ... 05/03/2026"
        m = re.search(r"[Vv]enc[ei]mento[:\s]+(\d{2})/(\d{2})/(\d{4})", text)
        if m:
            return int(m.group(3)), int(m.group(2))

        m = re.search(r"[Vv]ence\s+em\s+(\d{2})/(\d{2})/(\d{4})", text)
        if m:
            return int(m.group(3)), int(m.group(2))

        # Fallback: detecta qualquer ano + mês no texto
        m = re.search(r"(\d{2})/(\d{2})/(20\d{2})", text)
        if m:
            return int(m.group(3)), int(m.group(2))

        today = date.today()
        return today.year, today.month

    def _infer_year(self, tx_month: int, ref_year: int, ref_month: int) -> int:
        """
        Infere o ano de uma transação com base no mês.

        Lógica:
        - Se o mês da transação <= mês de referência: mesmo ano
        - Se o mês da transação > mês de referência: ano anterior
          (compras parceladas de meses passados)

        Exemplo: vencimento 03/2026, transação 24/06 → junho de 2025
        """
        if tx_month <= ref_month:
            return ref_year
        else:
            return ref_year - 1
