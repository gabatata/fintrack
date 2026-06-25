"""
Serviço de categorização de lançamentos.
Usa regras de palavra-chave cadastradas no banco de dados.
"""
from __future__ import annotations
import re
from database.connection import db_session
from utils.logger import get_logger

log = get_logger(__name__)

# Cache das regras para evitar query a cada categorização
_rules_cache: list[dict] | None = None


def _load_rules() -> list[dict]:
    """Carrega regras do banco (com cache em memória)."""
    global _rules_cache
    if _rules_cache is None:
        refresh_rules_cache()
    return _rules_cache or []


def refresh_rules_cache():
    """Invalida e recarrega o cache de regras."""
    global _rules_cache
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT keyword, match_type, category, subcategory, priority
            FROM category_rules
            WHERE active = 1
            ORDER BY priority DESC
            """
        ).fetchall()
        _rules_cache = [dict(r) for r in rows]
    log.debug(f"Cache de categorias recarregado: {len(_rules_cache)} regras")


def categorize(description_norm: str, description_raw: str = "") -> tuple[str, str]:
    """
    Categoriza um lançamento com base nas regras cadastradas.
    Retorna (category, subcategory).
    """
    text = (description_norm or description_raw or "").upper()

    for rule in _load_rules():
        keyword = rule["keyword"].upper()
        match_type = rule["match_type"]

        matched = False
        if match_type == "contains":
            matched = keyword in text
        elif match_type == "startswith":
            matched = text.startswith(keyword)
        elif match_type == "exact":
            matched = text == keyword
        elif match_type == "regex":
            try:
                matched = bool(re.search(keyword, text, re.IGNORECASE))
            except re.error:
                pass

        if matched:
            return rule["category"], rule.get("subcategory") or ""

    return "Outros", ""


def categorize_batch(transactions: list[dict]) -> list[dict]:
    """
    Categoriza uma lista de dicts de transações.
    Adiciona 'category' e 'subcategory' a cada um.
    """
    for tx in transactions:
        norm = tx.get("description_norm", "")
        raw = tx.get("description_raw", "")
        cat, subcat = categorize(norm, raw)
        tx["category"] = cat
        tx["subcategory"] = subcat
    return transactions


def add_rule(keyword: str, match_type: str, category: str,
             subcategory: str = "", priority: int = 5) -> int:
    """Adiciona uma nova regra de categorização ao banco."""
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO category_rules (keyword, match_type, category, subcategory, priority)
            VALUES (?, ?, ?, ?, ?)
            """,
            (keyword.strip(), match_type, category, subcategory, priority),
        )
        rule_id = cur.lastrowid
    refresh_rules_cache()
    return rule_id


def update_rule(rule_id: int, **kwargs):
    """Atualiza campos de uma regra existente."""
    allowed = {"keyword", "match_type", "category", "subcategory", "priority", "active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [rule_id]
    with db_session() as conn:
        conn.execute(f"UPDATE category_rules SET {set_clause} WHERE id = ?", values)
    refresh_rules_cache()


def delete_rule(rule_id: int):
    """Remove uma regra."""
    with db_session() as conn:
        conn.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
    refresh_rules_cache()


def get_all_rules() -> list[dict]:
    """Retorna todas as regras de categorização."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM category_rules ORDER BY priority DESC, keyword"
        ).fetchall()
        return [dict(r) for r in rows]


def get_categories() -> list[str]:
    """Retorna lista de categorias únicas existentes."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM category_rules ORDER BY category"
        ).fetchall()
        return [r[0] for r in rows]
