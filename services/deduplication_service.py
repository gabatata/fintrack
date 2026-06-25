# -*- coding: utf-8 -*-
"""
Servico de deduplicacao de lancamentos.

Regra correta:
- Mesmo lancamento em imports DIFERENTES (ex: extrato aberto + fatura fechada)
  -> manter apenas 1 (o mais recente, do import atual)
- Mesmo lancamento no MESMO import (ex: dois 99Food no mesmo dia, mesmo valor)
  -> manter ambos (sao compras distintas)

Um lancamento e considerado "mesmo" se tem:
  tx_date + amount + description_norm + account_label identicos
  E pertence a um import DIFERENTE do atual.
"""
from __future__ import annotations
import hashlib
from database.connection import db_session
from utils.logger import get_logger

log = get_logger(__name__)


def transaction_fingerprint(tx_date: str, amount: float,
                              description_norm: str,
                              account_label: str = "") -> str:
    """Fingerprint por conteudo (sem import_id)."""
    raw = f"{tx_date}|{round(amount, 2)}|{description_norm[:40].upper()}|{account_label}"
    return hashlib.md5(raw.encode()).hexdigest()


def find_duplicates(candidates: list[dict], import_id: int | None = None) -> list[dict]:
    """
    Verifica quais transacoes da lista ja existem no banco vindo de OUTRO import.

    - Se o lancamento identico esta no MESMO import_id -> NAO e duplicata
      (permite dois iguais na mesma fatura)
    - Se o lancamento identico esta em OUTRO import_id -> e duplicata
      (evita somar extrato aberto + fatura fechada)

    Parametros
    ----------
    candidates : lista de dicts representando as transacoes a importar
    import_id  : id do import atual (para excluir da busca)
    """
    with db_session() as conn:
        for tx in candidates:
            fp = transaction_fingerprint(
                tx.get("tx_date", ""),
                tx.get("amount", 0),
                tx.get("description_norm", tx.get("description_raw", "")),
                tx.get("account_label", ""),
            )
            tx["_fingerprint"] = fp

            # Busca lancamento equivalente em UM IMPORT DIFERENTE do atual.
            # Compara por DATA + VALOR + CARTAO + PARCELA, ignorando o texto do
            # nome -- porque o mesmo lancamento aparece com descricao diferente
            # entre formatos (extrato em aberto vs fatura fechada). A parcela no
            # criterio evita unir parcelas distintas (ex: 5/21 vs 6/21).
            existing = conn.execute(
                """
                SELECT id FROM transactions
                WHERE tx_date = ?
                  AND ABS(amount - ?) < 0.01
                  AND account_label = ?
                  AND COALESCE(installment_current, -1) = COALESCE(?, -1)
                  AND COALESCE(installment_total,   -1) = COALESCE(?, -1)
                  AND (
                    ? IS NULL
                    OR import_id != ?
                  )
                LIMIT 1
                """,
                (
                    tx.get("tx_date", ""),
                    tx.get("amount", 0),
                    tx.get("account_label", ""),
                    tx.get("installment_current"),
                    tx.get("installment_total"),
                    import_id,
                    import_id,
                ),
            ).fetchone()

            tx["duplicate_of"] = existing["id"] if existing else None

    n_dups = sum(1 for t in candidates if t.get("duplicate_of"))
    if n_dups:
        log.info(f"Deduplicacao: {n_dups}/{len(candidates)} duplicatas detectadas "
                 f"(de imports anteriores)")
    return candidates


def check_import_duplicate(file_hash: str) -> bool:
    """Verifica se um arquivo com este hash ja foi importado."""
    with db_session() as conn:
        row = conn.execute(
            "SELECT id FROM imports WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return row is not None
