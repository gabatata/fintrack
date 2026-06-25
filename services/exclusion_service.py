# -*- coding: utf-8 -*-
"""
Servico de exclusoes permanentes.

Dois mecanismos:

1. Lapides (tombstones): todo lancamento excluido gera uma "lapide" que impede
   o mesmo lancamento -- e as demais parcelas da MESMA compra -- de voltar em
   reimportacoes. A chave (fingerprint) ignora o numero da parcela atual
   (1/3, 2/3, 3/3 produzem a mesma chave) e bate por:
       nome + data da compra + total de parcelas + valor da parcela + valor total

2. Bloqueio por nome: palavras-chave que nunca devem aparecer
   (ex: "wellhub isabele"). Bloqueia na importacao e remove os existentes
   que ja batem.
"""
from __future__ import annotations
import hashlib
from database.connection import db_session
from utils.logger import get_logger

log = get_logger(__name__)


# ── Fingerprint (lapides) ───────────────────────────────────────────────────

def _name_of(merchant: str | None, description_norm: str | None) -> str:
    return (merchant or description_norm or "").strip().upper()


def excluded_fingerprint(merchant, description_norm, tx_date,
                         installment_total, parcela_amount, total_amount) -> str:
    """
    Chave que identifica uma COMPRA, ignorando o numero da parcela atual.
    Ex: ABC 1/3 e ABC 2/3 produzem a mesma fingerprint.
    """
    name = _name_of(merchant, description_norm)
    it = int(installment_total or 1)
    raw = (f"{name}|{tx_date or ''}|{it}"
           f"|{round(parcela_amount or 0, 2)}|{round(total_amount or 0, 2)}")
    return hashlib.md5(raw.encode()).hexdigest()


def _fingerprint_of_row(row: dict) -> str:
    it = row.get("installment_total") or 1
    parcela = row.get("amount") or 0
    total = round(parcela * it, 2)
    return excluded_fingerprint(row.get("merchant"), row.get("description_norm"),
                                row.get("tx_date"), it, parcela, total)


# ── Lapides ─────────────────────────────────────────────────────────────────

def tombstone_transaction(row: dict) -> None:
    """Registra a lapide de um lancamento (idempotente pela fingerprint)."""
    if not row:
        return
    it = row.get("installment_total") or 1
    parcela = row.get("amount") or 0
    total = round(parcela * it, 2)
    fp = _fingerprint_of_row(row)
    with db_session() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO excluded_transactions
                (fingerprint, merchant, description_norm, tx_date, amount,
                 total_amount, installment_total, account_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (fp, row.get("merchant"), row.get("description_norm"),
             row.get("tx_date"), parcela, total,
             row.get("installment_total"), row.get("account_label")),
        )


def get_excluded() -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM excluded_transactions ORDER BY excluded_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def remove_excluded(excluded_id: int) -> None:
    """Remove a lapide -> o lancamento pode voltar em proximas importacoes."""
    with db_session() as conn:
        conn.execute("DELETE FROM excluded_transactions WHERE id=?", (excluded_id,))


def clear_excluded() -> None:
    with db_session() as conn:
        conn.execute("DELETE FROM excluded_transactions")


# ── Bloqueio por nome ───────────────────────────────────────────────────────

def get_blocked_keywords() -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM blocked_keywords ORDER BY keyword"
        ).fetchall()
        return [dict(r) for r in rows]


def add_blocked_keyword(keyword: str, match_type: str = "contains",
                        note: str = "") -> int:
    """
    Adiciona uma palavra-chave de bloqueio e ja remove os lancamentos
    existentes que batem. Retorna quantos existentes foram removidos.
    """
    kw = (keyword or "").strip().upper()
    if not kw:
        return 0
    with db_session() as conn:
        conn.execute(
            "INSERT INTO blocked_keywords (keyword, match_type, note) VALUES (?, ?, ?)",
            (kw, match_type, (note or "").strip()),
        )
    return purge_existing_by_keyword(kw, match_type)


def remove_blocked_keyword(kw_id: int) -> None:
    with db_session() as conn:
        conn.execute("DELETE FROM blocked_keywords WHERE id=?", (kw_id,))


def _text_matches(text: str | None, keyword: str, match_type: str) -> bool:
    t = (text or "").upper()
    k = (keyword or "").upper()
    if not k:
        return False
    if match_type == "exact":
        return t.strip() == k
    return k in t


def purge_existing_by_keyword(keyword: str, match_type: str) -> int:
    """Remove lancamentos ja gravados que batem com a palavra-chave."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, description_raw, description_norm, merchant FROM transactions"
        ).fetchall()
        ids = [r["id"] for r in rows
               if _text_matches(r["description_raw"], keyword, match_type)
               or _text_matches(r["description_norm"], keyword, match_type)
               or _text_matches(r["merchant"], keyword, match_type)]
        for i in ids:
            conn.execute("DELETE FROM transactions WHERE id=?", (i,))
    if ids:
        log.info(f"Bloqueio '{keyword}': {len(ids)} lancamentos existentes removidos")
    return len(ids)


# ── Aplicacao na importacao ─────────────────────────────────────────────────

def apply_exclusions(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Separa os candidatos em (mantidos, bloqueados).
    Bloqueia se a fingerprint esta nas lapides OU se bate em alguma palavra-chave.
    Marca os bloqueados com tx['excluded_reason'].
    """
    with db_session() as conn:
        fps = {r["fingerprint"] for r in
               conn.execute("SELECT fingerprint FROM excluded_transactions").fetchall()}
        kws = [dict(r) for r in
               conn.execute("SELECT keyword, match_type FROM blocked_keywords").fetchall()]

    kept, blocked = [], []
    for tx in candidates:
        reason = None
        if _fingerprint_of_row(tx) in fps:
            reason = "Excluido anteriormente"
        else:
            for kw in kws:
                if (_text_matches(tx.get("description_raw"), kw["keyword"], kw["match_type"])
                        or _text_matches(tx.get("description_norm"), kw["keyword"], kw["match_type"])
                        or _text_matches(tx.get("merchant"), kw["keyword"], kw["match_type"])):
                    reason = f"Bloqueio: {kw['keyword']}"
                    break
        if reason:
            tx["excluded_reason"] = reason
            blocked.append(tx)
        else:
            kept.append(tx)

    if blocked:
        log.info(f"Exclusoes: {len(blocked)} lancamentos bloqueados na importacao")
    return kept, blocked
