"""
Componentes reutilizáveis de UI para as páginas Streamlit.
"""
import streamlit as st
from utils.helpers import CATEGORY_ICONS


def page_header(title: str, subtitle: str = ""):
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)
    st.divider()


def metric_card(label: str, value: str, delta: str = "", color: str = "#1f77b4"):
    st.markdown(
        f"""
        <div style="
            background: {color}18;
            border-left: 4px solid {color};
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 8px;
        ">
            <div style="font-size:0.8rem;color:#888;">{label}</div>
            <div style="font-size:1.5rem;font-weight:700;">{value}</div>
            {'<div style="font-size:0.75rem;color:#888;">' + delta + '</div>' if delta else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def category_badge(category: str) -> str:
    icon = CATEGORY_ICONS.get(category, "📌")
    return f"{icon} {category}"


def review_status_badge(status: str) -> str:
    badges = {
        "pending": "🔴 Pendente",
        "reviewed": "🟢 Revisado",
        "ignored": "⚫ Ignorado",
    }
    return badges.get(status, status)


def amount_fmt(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_date_br(iso_date: str) -> str:
    try:
        from datetime import date
        d = date.fromisoformat(iso_date)
        return d.strftime("%d/%m/%Y")
    except Exception:
        return iso_date


def tx_type_badge(tx_type: str) -> str:
    badges = {"debit": "💳", "credit": "↩️", "reversal": "🔄", "fee": "🏦"}
    return badges.get(tx_type, "")


# ── KPI cards (icone SVG inline + label + valor + subtexto) ───────────────────
_KPI_ICONS = {
    "cash":    '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 10v4M18 10v4"/>',
    "bars":    '<path d="M6 20V10M12 20V4M18 20v-6"/>',
    "layers":  '<path d="M12 3 3 8l9 5 9-5z"/><path d="M3 13l9 5 9-5"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 4v5h-5"/>',
    "clock":   '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
}


def kpi_card(label: str, value: str, icon: str = "cash",
             color: str = "#4C9BE8", sub: str = "") -> str:
    """Retorna o HTML de um card de KPI."""
    svg = (
        '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{_KPI_ICONS.get(icon, "")}</svg>'
    )
    sub_html = f'<div class="ft-kpi-sub">{sub}</div>' if sub else ""
    return (
        '<div class="ft-kpi">'
        f'<div class="ft-kpi-ico" style="background:{color}26;color:{color}">{svg}</div>'
        f'<div class="ft-kpi-lab">{label}</div>'
        f'<div class="ft-kpi-val ft-num">{value}</div>'
        f'{sub_html}'
        '</div>'
    )
