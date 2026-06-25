"""
Serviço de importação de PDFs.
Orquestra o pipeline completo:
PDF → extração de texto → OCR se necessário → parsing → normalização
→ categorização → deduplicação → gravação no banco
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Generator

from database.connection import db_session
from parsers.pdf_reader import extract_text_from_pdf
from parsers.parser_factory import parse_pdf
from ocr.ocr_engine import ocr_pdf_file
from services.normalization_service import normalize_description
from services.categorization_service import categorize
from services.deduplication_service import find_duplicates, check_import_duplicate
from services.recurrence_service import detect_recurring
from services.transaction_service import save_transactions
from utils.helpers import sha256_file, current_iso
from utils.logger import get_logger
from datetime import date as _date

log = get_logger(__name__)


def _detect_fatura_month(pages_text: list[str]) -> str | None:
    """
    Detecta o mes de vencimento da fatura (YYYY-MM).
    Estrategia robusta: busca a primeira data DD/MM/YYYY dentro de 200 chars
    apos a palavra 'Vencimento'. Funciona independente de quebra de linha.
    """
    import re as _re
    text = "\n".join(pages_text[:3])
    for kw in ["Vencimento", "vencimento", "Vence em"]:
        idx = text.find(kw)
        if idx >= 0:
            window = text[idx:idx+200]
            m = _re.search(r"(\d{2})/(\d{2})/(20\d{2})", window)
            if m:
                venc_mo = int(m.group(2))
                venc_yr = int(m.group(3))
                return f"{venc_yr}-{venc_mo:02d}"
    return None

def _infer_fatura_month(enriched: list[dict]) -> str | None:
    """
    Fallback quando o 'Vencimento' nao esta impresso (ex: extrato em aberto):
    a fatura fecha agora e VENCE no mes seguinte ao ultimo lancamento.
    Ex: ultimo gasto em junho -> vencimento (e billing_month) em julho.
    """
    meses = [d["_tx_month"] for d in enriched if d.get("_tx_month")]
    if not meses:
        return None
    ult = max(meses)            # 'YYYY-MM'
    yr, mo = int(ult[:4]), int(ult[5:7])
    mo += 1
    if mo > 12:
        mo, yr = 1, yr + 1
    return f"{yr}-{mo:02d}"


def _log_step(conn, import_id: int, step: str, message: str, level: str = "info"):
    conn.execute(
        "INSERT INTO processing_logs (import_id, level, step, message) VALUES (?, ?, ?, ?)",
        (import_id, level, step, message),
    )


def import_pdf(
    pdf_path: Path,
    account_label: str = "",
    source_name: str = "",
    force_ocr: bool = False,
) -> Generator[dict, None, dict]:
    """
    Pipeline completo de importação.
    Yields dicts com progresso: {"step": str, "msg": str, "pct": int}
    Retorna (via StopIteration value) dict com resultado final.
    """
    result = {
        "import_id": None,
        "total_found": 0,
        "total_saved": 0,
        "duplicates": 0,
        "blocked": 0,
        "ocr_used": False,
        "status": "error",
        "error": None,
        "preview": [],
    }

    try:
        # ── PASSO 1: Verificar duplicidade do arquivo ──────────────────────
        yield {"step": "hash", "msg": "Verificando arquivo...", "pct": 5}
        file_hash = sha256_file(pdf_path)
        if check_import_duplicate(file_hash):
            result["error"] = "Este arquivo já foi importado anteriormente."
            result["status"] = "duplicate"
            return result

        # ── PASSO 2: Registrar importação no banco ─────────────────────────
        yield {"step": "register", "msg": "Registrando importação...", "pct": 10}
        with db_session() as conn:
            cur = conn.execute(
                """
                INSERT INTO imports (filename, filepath, file_hash, source_name,
                    account_label, import_date, status)
                VALUES (?, ?, ?, ?, ?, ?, 'processing')
                """,
                (pdf_path.name, str(pdf_path), file_hash,
                 source_name, account_label, current_iso()),
            )
            import_id = cur.lastrowid
            result["import_id"] = import_id
            _log_step(conn, import_id, "register", f"Arquivo: {pdf_path.name}")

        # ── PASSO 3: Extração de texto ─────────────────────────────────────
        yield {"step": "extract", "msg": "Extraindo texto do PDF...", "pct": 20}
        pages_text, ocr_needed = extract_text_from_pdf(pdf_path)

        with db_session() as conn:
            _log_step(conn, import_id, "extract",
                      f"{len(pages_text)} páginas extraídas, OCR necessário: {ocr_needed}")

        # ── PASSO 4: OCR se necessário ─────────────────────────────────────
        if ocr_needed or force_ocr:
            yield {"step": "ocr", "msg": "Aplicando OCR nas páginas...", "pct": 35}
            try:
                ocr_pages = ocr_pdf_file(pdf_path)
                if ocr_pages:
                    # Mescla: usa OCR onde o texto direto era insuficiente
                    for i, (direct, ocr_text) in enumerate(
                        zip(pages_text, ocr_pages + [""] * len(pages_text))
                    ):
                        if len(direct.strip()) < 80:
                            pages_text[i] = ocr_text
                    result["ocr_used"] = True
                    with db_session() as conn:
                        _log_step(conn, import_id, "ocr", "OCR aplicado com sucesso")
            except RuntimeError as e:
                with db_session() as conn:
                    _log_step(conn, import_id, "ocr", str(e), "warning")
                yield {"step": "ocr", "msg": f"⚠️ OCR não disponível: {e}", "pct": 35}

        # ── PASSO 5: Parsing ───────────────────────────────────────────────
        yield {"step": "parse", "msg": "Identificando lançamentos...", "pct": 50}
        raw_txs = parse_pdf(pdf_path, pages_text, account_label)

        with db_session() as conn:
            _log_step(conn, import_id, "parse", f"{len(raw_txs)} lançamentos encontrados")

        if not raw_txs:
            with db_session() as conn:
                conn.execute(
                    "UPDATE imports SET status='done', total_found=0 WHERE id=?",
                    (import_id,),
                )
                _log_step(conn, import_id, "parse",
                          "Nenhum lançamento encontrado — verifique o formato do PDF", "warning")
            result["status"] = "done"
            result["total_found"] = 0
            return result

        # ── PASSO 6: Normalização e categorização ─────────────────────────
        yield {"step": "normalize", "msg": "Normalizando descrições...", "pct": 65}
        # Detecta mês de referência da fatura para billing_month
        fatura_month = _detect_fatura_month(pages_text)
        if fatura_month:
            log.info(f"Mês da fatura detectado: {fatura_month}")

        enriched = []
        for tx in raw_txs:
            d = tx.to_dict()
            d["description_norm"], d["merchant"] = normalize_description(d["description_raw"])
            d["category"], d["subcategory"] = categorize(d["description_norm"], d["description_raw"])
            d["source"] = "pdf"
            d["review_status"] = "pending"
            d["_tx_month"] = (d.get("tx_date") or "")[:7]
            enriched.append(d)

        # Fallback do mes da fatura: se "Vencimento" nao foi encontrado (ex: extrato
        # em aberto), infere pelo mes dominante dos lancamentos avulsos (o ciclo
        # atual). Sem isso, parcelas caem no mes da COMPRA original e vazam para
        # meses passados.
        if not fatura_month:
            fatura_month = _infer_fatura_month(enriched)
            if fatura_month:
                log.info(f"Mês da fatura inferido (sem vencimento): {fatura_month}")

        # billing_month: num extrato de cartao, TUDO (avulsos e parcelas) e cobrado
        # no mes da fatura -- entao todos recebem o mes da fatura detectado/inferido.
        # As parcelas que faltam sao projetadas pra frente no dashboard.
        # (Fallback para o mes da propria transacao so se a fatura nao for determinada.)
        for d in enriched:
            d["billing_month"] = fatura_month or d["_tx_month"]
            d.pop("_tx_month", None)

        # ── PASSO 7: Deduplicação ──────────────────────────────────────────
        yield {"step": "dedup", "msg": "Verificando duplicatas...", "pct": 75}
        enriched = find_duplicates(enriched, import_id)
        duplicates = sum(1 for t in enriched if t.get("duplicate_of"))
        result["duplicates"] = duplicates

        with db_session() as conn:
            _log_step(conn, import_id, "dedup", f"{duplicates} duplicatas detectadas")

        # ── PASSO 7.5: Exclusoes permanentes (lapides + bloqueio por nome) ──
        from services.exclusion_service import apply_exclusions
        enriched, blocked_list = apply_exclusions(enriched)
        result["blocked"] = len(blocked_list)
        if blocked_list:
            with db_session() as conn:
                _log_step(conn, import_id, "exclude",
                          f"{len(blocked_list)} lancamentos bloqueados "
                          f"(excluidos anteriormente / bloqueio por nome)")

        result["total_found"] = len(raw_txs)
        result["preview"] = enriched  # Para preview antes de confirmar (ja sem bloqueados)

        # ── PASSO 8: Salvar ────────────────────────────────────────────────
        yield {"step": "save", "msg": "Salvando lançamentos...", "pct": 88}
        saved = save_transactions(enriched, import_id)
        result["total_saved"] = saved

        # ── PASSO 9: Atualizar import e detectar recorrência ───────────────
        with db_session() as conn:
            conn.execute(
                """
                UPDATE imports SET
                    status='done', total_found=?, ocr_used=?
                WHERE id=?
                """,
                (len(raw_txs), int(result["ocr_used"]), import_id),
            )
            _log_step(conn, import_id, "done",
                      f"Importação concluída: {saved} lançamentos salvos")

        yield {"step": "recurrence", "msg": "Detectando recorrências...", "pct": 95}
        try:
            detect_recurring()
        except Exception as e:
            log.warning(f"Detecção de recorrência falhou: {e}")

        result["status"] = "done"
        yield {"step": "done", "msg": "✅ Importação concluída!", "pct": 100}

    except Exception as e:
        log.exception(f"Erro na importação: {e}")
        result["error"] = str(e)
        result["status"] = "error"
        if result.get("import_id"):
            with db_session() as conn:
                conn.execute(
                    "UPDATE imports SET status='error', error_msg=? WHERE id=?",
                    (str(e), result["import_id"]),
                )
                _log_step(conn, result["import_id"], "error", str(e), "error")

    return result


def get_imports() -> list[dict]:
    """Lista importacoes com agregados: valor total e mes de referencia (fatura)."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM imports ORDER BY import_date DESC"
        ).fetchall()
        imports = [dict(r) for r in rows]
        for imp in imports:
            agg = conn.execute(
                """
                SELECT COALESCE(SUM(CASE WHEN tx_type != 'credit' THEN amount ELSE 0 END), 0) AS total,
                       COUNT(*) AS n
                FROM transactions WHERE import_id = ?
                """,
                (imp["id"],),
            ).fetchone()
            imp["total_amount"] = agg["total"] or 0.0
            imp["tx_count"] = agg["n"] or 0
            # Mes de referencia = billing_month mais frequente dos lancamentos
            ref = conn.execute(
                """
                SELECT billing_month FROM transactions
                WHERE import_id = ? AND billing_month IS NOT NULL AND billing_month != ''
                GROUP BY billing_month
                ORDER BY COUNT(*) DESC, billing_month DESC
                LIMIT 1
                """,
                (imp["id"],),
            ).fetchone()
            imp["ref_month"] = ref["billing_month"] if ref else None
    return imports


def get_import_logs(import_id: int) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM processing_logs WHERE import_id=? ORDER BY created_at",
            (import_id,),
        ).fetchall()
        return [dict(r) for r in rows]
