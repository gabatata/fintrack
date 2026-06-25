# -*- coding: utf-8 -*-
"""
Parser Bradesco / Bradescard.

Suporta:
  1. Fatura mensal (PDF impresso)
  2. Extrato em aberto (Aplicativo Bradesco Cartoes)

Separa transacoes por TITULAR do cartao (Gabriel vs Brenda).
O account_label fica "{base} - {primeiro_nome}", ex: "Bradesco Visa - Gabriel".
"""
from __future__ import annotations
import re
from datetime import date
from parsers.base_parser import BaseParser, RawTransaction
from utils.helpers import parse_amount
from utils.logger import get_logger

log = get_logger(__name__)

BRADESCO_MARKERS = [
    "bradescard", "bradesco", "amazon mastercard",
    "banco bradescard", "visa infinite", "aplicativo bradesco",
]

DATE_START   = re.compile(r"^(\d{2}/\d{2})\s+(.+)$")
AMOUNT_FIRST = re.compile(r"\b(\d{1,3}(?:\.\d{3})*,\d{2})(-)?(?=\s|$|[^0-9,])")
PARCELA_PAREN = re.compile(r"\((\d{1,2})/(\d{1,2})\)")

CITY_NOISE = re.compile(
    r"\s+(SAO\s+PAULO|RECIFE|BRASILIA|EXTREMA|Sao\s+Paulo|Recife|ITABAIANA|"
    r"BARUERI|MARINGA|JOAO\s+PESSOA|FLORIANOPOLIS|FLORIANOPOL|ITAJAI|Uppsala|"
    r"SALVADOR|Boa\s+Vista|GLORIA\s+DO\s+GOI|Rio\s+de\s+Janeir|PORTO\s+ALEGRE|"
    r"Barueri|So\s+Paulo|GASPAR|REGISTRO|EXPORTACAO|Campo\s+do\s+Meio|"
    r"PORTO\s+FERREIR|SERRA|BRA|3\s+PE@|4\s+PE@)\s*$",
    re.IGNORECASE,
)

SKIP_LINE = re.compile(
    r"^(Data\s+Hist|Nacionais|Lancamentos|Lançamentos|Total\s+para|"
    r"Total\s+da\s+fatura|Resumo|Saldo\s+anterior|Creditos|Pagamentos|"
    r"Compras\s+R|Saque\s+R|Limites|Taxas\s+mensais|Parcelamento|Rotativo|"
    r"Crediario|Pagamento\s+de|Novo\s+teto|Credito\s+Rotativo|Valor\s+original|"
    r"Juros\s+e\s+encar|%\s+sobre|Os\s+juros|Programa|Pontos|Saldo\s+de|"
    r"Para\s+consultar|Central\s+de|SAC\s*:|Defici|Ouvidoria|Baixe\s+o|"
    r"Fatura\s+Mensal|Pagina|1FP005|054011|Moeda|Cotacao|Cotação|"
    r"Situacao\s+do\s+Extrato|Aplicativo|XXXX\.XXXX|Pagamento\s+total|"
    r"Parcelamento\s+de\s+Fatura|Pagamento\s+minimo|Melhor\s+opcao|"
    r"Sem\s+juros|Fique\s+atento|FALTA\s+DE\s+PAGAMENTO|Debito\s+automatico|"
    r"Cuide\s+do|Insira\s+a|Com\s+o\s+Bradesco|Total\s+parcelados|"
    r"Total\s+para\s+as\s+proximas)",
    re.IGNORECASE,
)

CREDIT_KW = re.compile(
    r"(pagto\.\s*por|pagamento\s+recebido|estorno|credito\s+dev|reembolso|saldo\s+anterior)",
    re.IGNORECASE,
)

# Detecta linha de secao de titular - fatura
# Ex: "GABRIEL DE SOUZA SANTOS Cartão 4066 XXXX XXXX 3680"
HOLDER_FATURA = re.compile(
    r"^([A-Z][A-Z\s]+?)\s+Cart(?:ão|ao)\s+\d{4}",
    re.IGNORECASE,
)
# Detecta linha de secao de titular - extrato
# Ex: "GABRIEL S SANTOS - VISA INFINITE XXXX.XXXX.XXXX.3680"
# Ex: "BRENDA CARVALHO - VISA INFINITE XXXX.XXXX.XXXX.7177"
HOLDER_EXTRATO = re.compile(
    r"^([A-Z][A-Z\s]+?)\s+-\s+VISA\s+INFINITE\s+XXXX",
    re.IGNORECASE,
)


def _first_name(full_name: str) -> str:
    """Extrai o primeiro nome de um nome completo."""
    parts = full_name.strip().split()
    return parts[0].capitalize() if parts else full_name


class BradescoParser(BaseParser):
    name = "Bradesco"
    supported_institutions = ["bradesco", "bradescard", "amazon mastercard", "visa infinite"]

    def can_parse(self, text: str, filename: str = "") -> bool:
        # Check header (first 600 chars) + filename
        header   = text[:600].lower()
        fname    = filename.lower()
        combined = header + " " + fname
        return any(m in combined for m in BRADESCO_MARKERS)

    def parse_text(self, pages_text: list[str]) -> list[RawTransaction]:
        full_text = "\n".join(pages_text)
        venc_yr, venc_mo = self._detect_vencimento(full_text)
        is_extrato = "EM ABERTO" in full_text or "Aplicativo Bradesco" in full_text
        log.info(f"BradescoParser: vencimento {venc_mo:02d}/{venc_yr} | extrato={is_extrato}")

        transactions = []
        carry_holder = ""   # titular carregado entre paginas
        for page_num, page_text in enumerate(pages_text, 1):
            tx_lines = [l for l in page_text.splitlines()
                        if re.match(r"^\d{2}/\d{2}\s", l.strip())]
            if not tx_lines:
                continue
            if is_extrato:
                txs, carry_holder = self._parse_extrato_page(
                    page_text, venc_yr, venc_mo, page_num, carry_holder)
            else:
                txs, carry_holder = self._parse_fatura_page(
                    page_text, venc_yr, venc_mo, page_num, carry_holder)
            transactions.extend(txs)

        log.info(f"BradescoParser: {len(transactions)} lancamentos extraidos")
        return transactions

    # ── Fatura impressa ───────────────────────────────────────────────────

    def _parse_fatura_page(self, text, ref_yr, ref_mo, page_num, current_holder=""):
        txs = []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            # Detecta mudanca de titular
            hm = HOLDER_FATURA.match(line)
            if hm:
                current_holder = _first_name(hm.group(1))
                log.debug(f"Titular fatura: {current_holder}")
                continue

            if SKIP_LINE.match(line):
                continue

            m = DATE_START.match(line)
            if not m:
                continue

            date_raw, rest = m.group(1), m.group(2)

            # Compra internacional traz varios numeros na linha:
            #   <valor moeda estrangeira> <valor> <cotacao> <valor em R$>
            # O valor cobrado e o ULTIMO (R$); na compra normal, o primeiro.
            is_foreign = bool(re.search(r"US\$|\bUSD\b|\bEUR\b|\bGBP\b", rest, re.I))
            matches = list(AMOUNT_FIRST.finditer(rest))
            if not matches:
                continue
            am = matches[-1] if is_foreign else matches[0]

            amount = parse_amount(am.group(1))
            if not amount:
                continue
            is_neg = bool(am.group(2))

            desc_raw = rest[:am.start()].strip()
            if is_foreign:
                # remove o trecho da conversao (a partir de "USD"/"US$") da descricao
                desc_raw = re.split(r"\s*(?:US\$|USD|EUR|GBP)\b", desc_raw,
                                    maxsplit=1, flags=re.I)[0].strip()
            desc_raw = CITY_NOISE.sub("", desc_raw).strip()
            desc_raw = re.sub(r"\s+BRA\s*$", "", desc_raw).strip()

            pm = PARCELA_PAREN.search(desc_raw)
            if not pm:
                pm = re.search(r"(\d{1,2})/(\d{2})(?=\s|$)", desc_raw)
            inst_cur = int(pm.group(1)) if pm else None
            inst_tot = int(pm.group(2)) if pm else None

            desc_clean = PARCELA_PAREN.sub("", desc_raw)
            if pm and not PARCELA_PAREN.search(desc_raw):
                desc_clean = re.sub(r"\s*\d{1,2}/\d{2}\s*", " ", desc_clean)
            desc_clean = desc_clean.strip()

            # account_label = base + titular
            label = self._make_label(current_holder)
            tx = self._make_tx(date_raw, desc_clean, amount, is_neg,
                               inst_cur, inst_tot, ref_yr, ref_mo, page_num, line, label)
            if tx:
                txs.append(tx)
        return txs, current_holder

    # ── Extrato em aberto ─────────────────────────────────────────────────

    def _parse_extrato_page(self, text, ref_yr, ref_mo, page_num, current_holder=""):
        txs = []
        raw = [l.strip() for l in text.splitlines()]
        consumed = set()   # linhas ja usadas como continuacao de descricao

        def _is_orphan(idx):
            """Linha que pode ser fragmento de descricao (sem data, sem ser cabecalho)."""
            if idx < 0 or idx >= len(raw) or idx in consumed:
                return False
            s = raw[idx]
            if not s or DATE_START.match(s) or SKIP_LINE.match(s) \
                    or HOLDER_EXTRATO.match(s) or "SALDO ANTERIOR" in s.upper():
                return False
            return True

        for i, line in enumerate(raw):
            if i in consumed or not line:
                continue

            # Detecta secao de titular no extrato
            hm = HOLDER_EXTRATO.match(line)
            if hm:
                current_holder = _first_name(hm.group(1))
                log.debug(f"Titular extrato: {current_holder}")
                continue

            if SKIP_LINE.match(line):
                continue
            if "SALDO ANTERIOR" in line.upper():
                continue

            m = DATE_START.match(line)
            if not m:
                continue

            date_raw, rest = m.group(1), m.group(2)

            neg_match = re.search(r"-([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})\s*$", rest)
            if neg_match:
                amount  = parse_amount(neg_match.group(1))
                is_neg  = True
                rest_desc = rest[:neg_match.start()].strip()
            else:
                pos_match = re.search(r"([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})\s*$", rest)
                if not pos_match:
                    continue
                amount    = parse_amount(pos_match.group(1))
                is_neg    = False
                rest_desc = rest[:pos_match.start()].strip()

            if not amount:
                continue

            # Descricao quebrada em linhas vizinhas (layout do extrato Bradesco):
            #   'UBER *ONE MEMBERSHIP'   <- linha anterior (orfa)
            #   '28/05 106,20'           <- esta linha: data + valor, descricao vazia
            #   'UBER' ou '19/21'        <- proxima linha: continuacao / nº da parcela
            if len(rest_desc) < 2:
                parts = []
                if _is_orphan(i - 1):
                    parts.append(raw[i - 1]); consumed.add(i - 1)
                if _is_orphan(i + 1):
                    parts.append(raw[i + 1]); consumed.add(i + 1)
                rest_desc = " ".join(parts).strip()

            # Parcela "X/Y" no fim da descricao (aceita total de 1 ou 2 digitos)
            pm = re.search(r"\b(\d{1,2})/(\d{1,2})\s*$", rest_desc)
            inst_cur   = int(pm.group(1)) if pm else None
            inst_tot   = int(pm.group(2)) if pm else None
            desc_clean = re.sub(r"\s*\d{1,2}/\d{1,2}\s*$", "", rest_desc).strip() if pm else rest_desc.strip()

            label = self._make_label(current_holder)
            tx = self._make_tx(date_raw, desc_clean, amount, is_neg,
                               inst_cur, inst_tot, ref_yr, ref_mo, page_num, line, label)
            if tx:
                txs.append(tx)
        return txs, current_holder

    # ── Helpers ───────────────────────────────────────────────────────────

    def _make_label(self, holder: str) -> str:
        """
        Monta o account_label com o titular.
        Ex: account_label="Bradesco Visa", holder="Gabriel" -> "Bradesco Visa - Gabriel"
        Ex: holder="" -> usa account_label puro
        """
        base = self.account_label or "Bradesco"
        if holder:
            return f"{base} - {holder}"
        return base

    def _make_tx(self, date_raw, desc_clean, amount, is_neg,
                 inst_cur, inst_tot, ref_yr, ref_mo, page_num, raw_line, label):
        if not desc_clean or len(desc_clean) < 2:
            return None
        try:
            day, mo = map(int, date_raw.split("/"))
        except ValueError:
            return None
        yr = self._infer_year(mo, ref_yr, ref_mo)
        try:
            date(yr, mo, day)
        except ValueError:
            return None

        is_credit = is_neg or bool(CREDIT_KW.search(desc_clean))
        return RawTransaction(
            tx_date=f"{yr}-{mo:02d}-{day:02d}",
            description_raw=desc_clean,
            amount=amount,
            tx_type="credit" if is_credit else "debit",
            installment_current=inst_cur,
            installment_total=inst_tot,
            account_label=label,
            page_number=page_num,
            raw_line=raw_line,
        )

    def _detect_vencimento(self, text):
        # Primeira data apos keyword Vencimento (qualquer formato de layout)
        for kw in ["Vencimento", "vencimento"]:
            idx = text.find(kw)
            if idx >= 0:
                import re as _re
                window = text[idx:idx+200]
                m = _re.search(r"(\d{2})/(\d{2})/(20\d{2})", window)
                if m:
                    return int(m.group(3)), int(m.group(2))
        # Extrato em aberto: usa o proximo mes apos a data do extrato
        import re as _re
        dm = _re.search(r"Data:\s*(\d{2})/(\d{2})/(\d{4})", text)
        if dm:
            yr, mo = int(dm.group(3)), int(dm.group(2))
            mo += 1
            if mo > 12:
                mo, yr = 1, yr + 1
            return yr, mo
        today = date.today()
        mo = today.month + 1 if today.month < 12 else 1
        yr = today.year if today.month < 12 else today.year + 1
        return yr, mo

    def _infer_year(self, tx_month, ref_yr, ref_mo):
        return ref_yr if tx_month <= ref_mo else ref_yr - 1
