# -*- coding: utf-8 -*-
"""
Servico de deteccao de recorrencia / assinaturas.

Regras:
- Compras PARCELADAS nunca sao recorrentes (sao dividas, nao assinaturas)
- Recorrencia = mesmo merchant, sem parcela, repetindo em meses diferentes
- is_recurring so e marcado quando status = 'confirmed' (nao sugerido)
- Recorrentes confirmados sao projetados INDEFINIDAMENTE (todo mes para sempre)
"""
from __future__ import annotations
from collections import defaultdict
from database.connection import db_session
from utils.logger import get_logger

log = get_logger(__name__)

MIN_OCCURRENCES = 2


def detect_recurring(min_occurrences: int = MIN_OCCURRENCES):
    """
    Analisa transacoes e atualiza recurring_patterns.
    EXCLUI qualquer transacao parcelada (installment_current IS NOT NULL).
    """
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT
                merchant,
                category,
                subcategory,
                COUNT(*) as cnt,
                AVG(amount) as avg_amount,
                MAX(tx_date) as last_seen,
                GROUP_CONCAT(
                    COALESCE(billing_month, strftime('%Y-%m', tx_date)),
                    ','
                ) as months
            FROM transactions
            WHERE merchant != ''
              AND tx_type = 'debit'
              AND review_status != 'ignored'
              AND (installment_current IS NULL OR installment_current = '')
            GROUP BY UPPER(merchant)
            HAVING cnt >= ?
            ORDER BY cnt DESC
            """,
            (min_occurrences,),
        ).fetchall()

        for row in rows:
            merchant  = row["merchant"]
            frequency = _estimate_frequency(row["months"])

            existing = conn.execute(
                "SELECT id, status FROM recurring_patterns WHERE UPPER(merchant) = UPPER(?)",
                (merchant,),
            ).fetchone()

            if existing:
                if existing["status"] != "dismissed":
                    conn.execute(
                        """
                        UPDATE recurring_patterns SET
                            avg_amount = ?, frequency = ?, last_seen = ?,
                            occurrence_count = ?, updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (row["avg_amount"], frequency, row["last_seen"],
                         row["cnt"], existing["id"]),
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO recurring_patterns
                        (merchant, category, subcategory, avg_amount, frequency,
                         last_seen, occurrence_count, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'suggested')
                    """,
                    (merchant, row["category"], row["subcategory"],
                     row["avg_amount"], frequency, row["last_seen"], row["cnt"]),
                )

        # is_recurring = 1 APENAS em transacoes cujo padrao esta CONFIRMADO
        # Parcelas NUNCA recebem is_recurring = 1
        _tag_recurring_transactions(conn)

    log.info("Deteccao de recorrencia concluida.")


def _estimate_frequency(months_str: str) -> str:
    """
    Estima frequencia com base nos meses de cobranca.
    Usa billing_month para nao confundir data da compra com data de cobranca.
    """
    if not months_str:
        return "irregular"
    try:
        months = sorted(set(m for m in months_str.split(",") if m and len(m) == 7))
        if len(months) < 2:
            return "irregular"

        # Converte para numeros de mes (YYYY*12 + MM)
        def to_num(ym):
            yr, mo = map(int, ym.split("-"))
            return yr * 12 + mo

        nums = [to_num(m) for m in months]
        gaps = [nums[i+1] - nums[i] for i in range(len(nums)-1)]
        avg_gap = sum(gaps) / len(gaps)

        if avg_gap <= 1.2:
            return "monthly"
        elif avg_gap <= 3.5:
            return "quarterly"
        elif avg_gap <= 13:
            return "yearly"
        else:
            return "irregular"
    except Exception:
        return "irregular"


def _tag_recurring_transactions(conn):
    """
    Marca is_recurring=1 apenas em transacoes:
    - Cujo merchant esta CONFIRMADO como recorrente
    - Que NAO sao parceladas
    """
    # Remove flag de todos que nao sao confirmados
    conn.execute(
        """
        UPDATE transactions SET is_recurring = 0
        WHERE merchant NOT IN (
            SELECT merchant FROM recurring_patterns WHERE status = 'confirmed'
        )
        OR installment_current IS NOT NULL
        """
    )
    # Marca apenas os confirmados sem parcela
    conn.execute(
        """
        UPDATE transactions SET is_recurring = 1
        WHERE installment_current IS NULL
          AND merchant IN (
            SELECT merchant FROM recurring_patterns WHERE status = 'confirmed'
          )
        """
    )


def get_recurring_patterns() -> list[dict]:
    """Retorna todos os padroes de recorrencia."""
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM recurring_patterns
            ORDER BY
                CASE status WHEN 'confirmed' THEN 0 WHEN 'suggested' THEN 1 ELSE 2 END,
                occurrence_count DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def update_pattern_status(pattern_id: int, status: str):
    """Confirma, rejeita ou restaura um padrao de recorrencia."""
    assert status in ("suggested", "confirmed", "dismissed")
    with db_session() as conn:
        conn.execute(
            "UPDATE recurring_patterns SET status=?, updated_at=datetime('now') WHERE id=?",
            (status, pattern_id),
        )
        _tag_recurring_transactions(conn)


def get_confirmed_recurring() -> list[dict]:
    """Retorna apenas os recorrentes confirmados, para uso na projecao."""
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT merchant, category, subcategory, avg_amount, frequency, last_seen
            FROM recurring_patterns
            WHERE status = 'confirmed'
            ORDER BY merchant
            """
        ).fetchall()
        return [dict(r) for r in rows]


def project_recurring_infinite(billing_month_start: str, months_ahead: int = 24) -> list[dict]:
    """
    Projeta recorrentes confirmados para os proximos N meses a partir de billing_month_start.
    Como sao assinaturas, repetem TODO MES para sempre (sem data de termino).
    Retorna lista de {month: YYYY-MM, total: float, items: [...]}.
    """
    patterns = get_confirmed_recurring()
    if not patterns:
        return []

    # Meses mensais repetem todo mes; anuais so no mes certo
    try:
        yr, mo = map(int, billing_month_start.split("-"))
    except Exception:
        from datetime import date
        today = date.today()
        yr, mo = today.year, today.month

    result = defaultdict(lambda: {"month": "", "total": 0.0, "items": []})

    for i in range(1, months_ahead + 1):
        # Avanca um mes
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1
        key = f"{yr}-{mo:02d}"

        for p in patterns:
            freq = p.get("frequency", "monthly")
            avg  = p.get("avg_amount", 0) or 0
            if avg <= 0:
                continue

            include = False
            if freq == "monthly":
                include = True
            elif freq == "yearly":
                # Inclui apenas no mes de ultima ocorrencia
                last = p.get("last_seen", "")
                if last and len(last) >= 7:
                    last_mo = int(last[5:7])
                    if last_mo == mo:
                        include = True
            elif freq == "quarterly":
                last = p.get("last_seen", "")
                if last and len(last) >= 7:
                    last_mo = int(last[5:7])
                    if (mo - last_mo) % 3 == 0:
                        include = True

            if include:
                result[key]["month"]  = key
                result[key]["total"] += avg
                result[key]["items"].append({
                    "merchant": p["merchant"],
                    "amount":   avg,
                    "category": p.get("category", ""),
                })

    return [v for v in sorted(result.values(), key=lambda x: x["month"]) if v["total"] > 0]
