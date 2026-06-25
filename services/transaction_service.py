"""
Repositório de transações — todas as operações de banco para a tabela transactions.
"""
from __future__ import annotations
from database.connection import db_session
from utils.logger import get_logger

log = get_logger(__name__)


def save_transactions(transactions: list[dict], import_id: int | None = None) -> int:
    """
    Insere lista de transações no banco.
    Retorna número de registros inseridos.
    """
    inserted = 0
    with db_session() as conn:
        for tx in transactions:
            # Pula duplicatas explícitas
            if tx.get("duplicate_of"):
                log.debug(f"Pulando duplicata: {tx.get('description_raw')}")
                continue
            conn.execute(
                """
                INSERT INTO transactions (
                    import_id, tx_date, billing_month, description_raw, description_norm,
                    merchant, amount, tx_type, installment_current,
                    installment_total, account_label, category, subcategory,
                    is_recurring, review_status, source, notes
                ) VALUES (
                    :import_id, :tx_date, :billing_month, :description_raw, :description_norm,
                    :merchant, :amount, :tx_type, :installment_current,
                    :installment_total, :account_label, :category, :subcategory,
                    :is_recurring, :review_status, :source, :notes
                )
                """,
                {
                    "import_id": import_id,
                    "tx_date": tx.get("tx_date", ""),
                    "billing_month": tx.get("billing_month") or (tx.get("tx_date") or "")[:7],
                    "description_raw": tx.get("description_raw", ""),
                    "description_norm": tx.get("description_norm", ""),
                    "merchant": tx.get("merchant", ""),
                    "amount": tx.get("amount", 0),
                    "tx_type": tx.get("tx_type", "debit"),
                    "installment_current": tx.get("installment_current"),
                    "installment_total": tx.get("installment_total"),
                    "account_label": tx.get("account_label", ""),
                    "category": tx.get("category", "Outros"),
                    "subcategory": tx.get("subcategory", ""),
                    "is_recurring": int(tx.get("is_recurring", 0)),
                    "review_status": tx.get("review_status", "pending"),
                    "source": tx.get("source", "pdf"),
                    "notes": tx.get("notes", ""),
                },
            )
            inserted += 1
    log.info(f"Transações salvas: {inserted}")
    return inserted


def get_transactions(
    month: str | None = None,
    account: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    review_status: str | None = None,
    is_recurring: bool | None = None,
    source: str | None = None,
    search: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    limit: int = 2000,
) -> list[dict]:
    """Consulta transações com filtros opcionais."""
    filters = ["t.tx_type != 'credit'"]  # padrão: só débitos
    params: list = []

    if month:
        # Usa billing_month se disponível, senão cai para tx_date
        filters.append("COALESCE(t.billing_month, strftime('%Y-%m', t.tx_date)) = ?")
        params.append(month)
    if account:
        filters.append("t.account_label = ?")
        params.append(account)
    if category:
        filters.append("t.category = ?")
        params.append(category)
    if subcategory:
        filters.append("t.subcategory = ?")
        params.append(subcategory)
    if review_status:
        filters.append("t.review_status = ?")
        params.append(review_status)
    if is_recurring is not None:
        filters.append("t.is_recurring = ?")
        params.append(int(is_recurring))
    if source:
        filters.append("t.source = ?")
        params.append(source)
    if search:
        filters.append("(t.description_raw LIKE ? OR t.description_norm LIKE ? OR t.merchant LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    if min_amount is not None:
        filters.append("t.amount >= ?")
        params.append(min_amount)
    if max_amount is not None:
        filters.append("t.amount <= ?")
        params.append(max_amount)

    where = " AND ".join(filters)
    query = f"""
        SELECT t.*, i.source_name as import_source
        FROM transactions t
        LEFT JOIN imports i ON t.import_id = i.id
        WHERE {where}
        ORDER BY t.tx_date DESC, t.id DESC
        LIMIT ?
    """
    params.append(limit)

    with db_session() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def update_transaction(tx_id: int, **fields):
    """Atualiza campos de uma transacao."""
    allowed = {
        "tx_date", "description_raw", "description_norm", "merchant",
        "amount", "tx_type", "category", "subcategory",
        "is_recurring", "review_status", "notes", "account_label",
        "installment_current", "installment_total",
        "third_party_type", "third_party_name", "split_with",
        "split_amount", "split_paid",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_parts = [f"{k} = ?" for k in updates]
    bind_vals = list(updates.values())
    bind_vals.append(tx_id)   # apenas uma vez, para o WHERE
    with db_session() as conn:
        conn.execute(
            f"UPDATE transactions SET {', '.join(set_parts)}, updated_at = datetime('now') WHERE id = ?",
            bind_vals,
        )


def delete_transaction(tx_id: int):
    """Exclui um lancamento e registra a lapide (impede que volte na reimportacao)."""
    from services.exclusion_service import tombstone_transaction
    row = get_transaction_by_id(tx_id)
    if row:
        tombstone_transaction(row)
    with db_session() as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))


def bulk_delete_transactions(ids: list[int]):
    """Exclui varios lancamentos, registrando a lapide de cada um."""
    from services.exclusion_service import tombstone_transaction
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with db_session() as conn:
        rows = [dict(r) for r in conn.execute(
            f"SELECT * FROM transactions WHERE id IN ({placeholders})", ids
        ).fetchall()]
    for r in rows:
        tombstone_transaction(r)
    with db_session() as conn:
        conn.execute(f"DELETE FROM transactions WHERE id IN ({placeholders})", ids)


def get_transaction_by_id(tx_id: int) -> dict | None:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        return dict(row) if row else None


def get_monthly_summary() -> list[dict]:
    """Retorna total gasto por mês."""
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT
                COALESCE(billing_month, strftime('%Y-%m', tx_date)) as month,
                SUM(amount) as total,
                COUNT(*) as count
            FROM transactions
            WHERE tx_type = 'debit' AND review_status != 'ignored'
            GROUP BY month
            ORDER BY month
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_category_summary(month: str | None = None) -> list[dict]:
    """Retorna total por categoria."""
    params = []
    where = "tx_type = 'debit' AND review_status != 'ignored'"
    if month:
        # Coerente com get_monthly_summary / dashboard: usa billing_month quando existe
        where += " AND COALESCE(billing_month, strftime('%Y-%m', tx_date)) = ?"
        params.append(month)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT category, SUM(amount) as total, COUNT(*) as count
            FROM transactions
            WHERE {where}
            GROUP BY category
            ORDER BY total DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

def get_pending_review_count() -> int:
    # Conta so o que e revisavel na lista (creditos/pagamentos nao aparecem la).
    with db_session() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM transactions "
            "WHERE review_status = 'pending' AND tx_type != 'credit'"
        ).fetchone()[0]


def get_accounts() -> list[str]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT DISTINCT account_label FROM transactions WHERE account_label != '' ORDER BY account_label"
        ).fetchall()
        return [r[0] for r in rows]


def get_months() -> list[str]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT COALESCE(billing_month, strftime('%Y-%m', tx_date)) as month
            FROM transactions ORDER BY month DESC
            """
        ).fetchall()
        return [r[0] for r in rows]


def bulk_recategorize(only_pending: bool = True, only_uncategorized: bool = False) -> int:
    """
    Re-aplica todas as regras de categorizacao nos lancamentos.
    Retorna o numero de lancamentos atualizados.

    only_pending: se True, so atualiza lancamentos com review_status='pending'
    only_uncategorized: se True, so atualiza lancamentos com categoria 'Outros'
    """
    from services.categorization_service import categorize

    filters = []
    if only_pending:
        filters.append("review_status = 'pending'")
    if only_uncategorized:
        filters.append("category = 'Outros'")

    where = " AND ".join(filters) if filters else "1=1"

    updated = 0
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT id, description_norm, description_raw, merchant
            FROM transactions
            WHERE {where}
            ORDER BY id
            """
        ).fetchall()

        for row in rows:
            desc_norm = row["description_norm"] or ""
            desc_raw  = row["description_raw"] or ""
            # Usa merchant como contexto adicional
            search_text = row["merchant"] or desc_norm or desc_raw

            cat, subcat = categorize(search_text, desc_raw)

            # So atualiza se mudou de 'Outros'
            current = conn.execute(
                "SELECT category FROM transactions WHERE id=?", (row["id"],)
            ).fetchone()["category"]

            if cat != "Outros" or current == "Outros":
                conn.execute(
                    "UPDATE transactions SET category=?, subcategory=? WHERE id=?",
                    (cat, subcat, row["id"]),
                )
                if cat != current:
                    updated += 1

    return updated


def get_receivables() -> list[dict]:
    """
    Retorna lancamentos que tem valor a receber de terceiros:
    - third_party_type='full': valor total a receber
    - third_party_type='split': valor split_amount a receber
    Filtra apenas os nao pagos (split_paid=0).
    """
    with db_session() as conn:
        rows = conn.execute("""
            SELECT id, tx_date, billing_month, description_norm, description_raw,
                   merchant, amount, split_amount, third_party_type,
                   third_party_name, split_with, split_paid,
                   category, account_label, installment_current, installment_total
            FROM transactions
            WHERE (third_party_type = 'full' OR third_party_type = 'split')
              AND (split_paid = 0 OR split_paid IS NULL)
              AND tx_type = 'debit'
            ORDER BY tx_date DESC
        """).fetchall()
    return [dict(r) for r in rows]


def mark_split_paid(tx_id: int, paid: bool):
    """Marca ou desmarca um lancamento como pago pelo terceiro."""
    with db_session() as conn:
        conn.execute(
            "UPDATE transactions SET split_paid=?, updated_at=datetime('now') WHERE id=?",
            (1 if paid else 0, tx_id)
        )


def effective_amount(tx: dict) -> float:
    """
    Valor efetivo do lancamento para o dono do cartao:
    - full:  0 (100% de terceiro)
    - split: amount - split_amount (o que e do dono)
    - None:  amount (normal)
    """
    tp = tx.get("third_party_type")
    if tp == "full":
        return 0.0
    if tp == "split":
        sa = tx.get("split_amount") or 0
        return max(0.0, (tx.get("amount") or 0) - sa)
    return tx.get("amount") or 0.0
