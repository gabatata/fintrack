# -*- coding: utf-8 -*-
"""
Funcoes utilitarias gerais.
"""
import hashlib
import re
from pathlib import Path
from datetime import datetime, date
from typing import Optional


def sha256_file(filepath) -> str:
    """Calcula hash SHA-256 de um arquivo."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    """Remove acentos, converte para maiusculo e limpa espacos."""
    if not text:
        return ""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in nfkd if not unicodedata.combining(c))
    text = text.upper()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date(raw: str) -> Optional[str]:
    """
    Interpreta datas em varios formatos e retorna ISO 8601 (YYYY-MM-DD).
    Retorna None se nao conseguir.
    """
    if not raw:
        return None
    raw = raw.strip()
    formats = [
        "%d/%m/%Y", "%d/%m/%y",
        "%Y-%m-%d",
        "%d-%m-%Y", "%d-%m-%y",
        "%d.%m.%Y", "%d.%m.%y",
        "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_amount(raw: str) -> Optional[float]:
    """
    Interpreta strings de valor monetario brasileiro e retorna float positivo.
    Ex: "R$ 1.234,56" -> 1234.56
    """
    if not raw:
        return None
    text = re.sub(r"[R$\s]", "", str(raw))
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return abs(float(text))
    except (ValueError, TypeError):
        return None


def save_uploaded_file(uploaded_file, destination_dir: Path) -> Path:
    """Salva arquivo enviado via Streamlit em disco."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    dest = destination_dir / uploaded_file.name
    if dest.exists():
        stem   = dest.stem
        suffix = dest.suffix
        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest   = destination_dir / f"{stem}_{ts}{suffix}"
    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest


def current_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def month_label(iso_date: str) -> str:
    """
    Converte YYYY-MM ou YYYY-MM-DD para 'Mar/2026'.
    Aceita qualquer string que comece com YYYY-MM.
    """
    _months = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
               "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    try:
        parts = str(iso_date).strip().split("-")
        yr = int(parts[0])
        mo = int(parts[1])
        return f"{_months[mo - 1]}/{yr}"
    except Exception:
        return str(iso_date)[:7] if iso_date else ""


# Icones por categoria — usando texto puro para evitar problemas de encoding no Windows
# Formato: emoji como sequencia de escape unicode (100% seguro em qualquer SO)
CATEGORY_ICONS = {
    "Alimentação":   "\U0001F354",   # hamburger
    "Transporte":    "\U0001F697",   # car
    "Assinaturas":   "\U0001F4FA",   # television
    "Saúde":         "\U0001F48A",   # pill
    "Compras":       "\U0001F6CD",   # shopping bags
    "Moradia":       "\U0001F3E0",   # house
    "Comunicação":   "\U0001F4F1",   # mobile phone
    "Educação":      "\U0001F4DA",   # books
    "Lazer":         "\U0001F389",   # party popper
    "Banco/Taxas":   "\U0001F3E6",   # bank
    "Investimentos": "\U0001F4B9",   # chart
    "Outros":        "\U0001F4CC",   # pushpin
}


def get_category_icon(category: str) -> str:
    """Retorna o icone da categoria, preferindo versao do banco se existir."""
    try:
        from database.connection import db_session
        with db_session() as conn:
            row = conn.execute(
                "SELECT value FROM app_config WHERE key=?",
                (f"icon:{category}",)
            ).fetchone()
            if row:
                return row[0]
    except Exception:
        pass
    return CATEGORY_ICONS.get(category, "")


def set_category_icon(category: str, icon: str):
    """Salva icone personalizado de uma categoria no banco."""
    try:
        from database.connection import db_session
        with db_session() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (f"icon:{category}", icon)
            )
    except Exception:
        pass


def get_all_category_icons() -> dict:
    """Retorna dict {categoria: icone} com sobreposicoes do banco."""
    icons = dict(CATEGORY_ICONS)
    try:
        from database.connection import db_session
        with db_session() as conn:
            rows = conn.execute(
                "SELECT key, value FROM app_config WHERE key LIKE 'icon:%'"
            ).fetchall()
            for row in rows:
                cat = row[0][5:]   # Remove 'icon:' prefix
                icons[cat] = row[1]
    except Exception:
        pass
    return icons
