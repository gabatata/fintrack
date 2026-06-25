"""
Página: Recorrentes / Assinaturas
Gerencia padrões de recorrência detectados automaticamente.
"""
import streamlit as st
import pandas as pd

from services.recurrence_service import (
    get_recurring_patterns, update_pattern_status, detect_recurring,
)
from pages.components import page_header, amount_fmt
from utils.helpers import CATEGORY_ICONS

FREQ_PT = {
    "monthly": "Mensal",
    "weekly": "Semanal",
    "yearly": "Anual",
    "quarterly": "Trimestral",
    "irregular": "Irregular",
}

# (cor da borda, classe do chip, rotulo)
STATUS_META = {
    "confirmed": ("#34D399", "ok",   "Confirmado"),
    "suggested": ("#FBBF24", "warn", "Sugerido"),
    "dismissed": ("#69728A", "mut",  "Descartado"),
}


def render():
    page_header("Recorrentes / Assinaturas", "Gerencie seus gastos recorrentes e assinaturas.")

    col_refresh, _ = st.columns([1.8, 3.2])
    if col_refresh.button("Re-detectar recorrências", icon=":material/refresh:", use_container_width=True):
        with st.spinner("Analisando padrões..."):
            detect_recurring()
        st.success("Detecção concluída!")
        st.rerun()

    patterns = get_recurring_patterns()
    if not patterns:
        st.info("Nenhum padrão recorrente detectado ainda. Importe mais extratos para análise.")
        return

    # ── Filtro por status ─────────────────────────────────────────────────
    status_filter = st.segmented_control(
        "Filtrar por status",
        options=["Todos", "Sugeridos", "Confirmados", "Descartados"],
        default="Todos",
    )
    status_map = {
        "Todos": None,
        "Sugeridos": "suggested",
        "Confirmados": "confirmed",
        "Descartados": "dismissed",
    }
    filter_status = status_map.get(status_filter)

    filtered = [p for p in patterns
                if not filter_status or p["status"] == filter_status]

    # ── Resumo ────────────────────────────────────────────────────────────
    confirmed = [p for p in patterns if p["status"] == "confirmed"]
    suggested = [p for p in patterns if p["status"] == "suggested"]
    total_confirmed_monthly = sum(
        p["avg_amount"] for p in confirmed if p.get("frequency") == "monthly"
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Confirmadas", len(confirmed))
    c2.metric("Sugeridas (revisar)", len(suggested))
    c3.metric("Total mensal confirmado", amount_fmt(total_confirmed_monthly))

    st.divider()

    # ── Lista de padrões ──────────────────────────────────────────────────
    for p in filtered:
        _render_pattern_card(p)


def _render_pattern_card(p: dict):
    status = p.get("status", "suggested")
    color, chip_cls, status_lbl = STATUS_META.get(status, ("#69728A", "mut", status))
    icon = CATEGORY_ICONS.get(p.get("category", ""), "")
    freq = FREQ_PT.get(p.get("frequency", "irregular"), "Irregular")
    sub  = f" · {p['subcategory']}" if p.get("subcategory") else ""

    with st.container():
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;
                background:var(--ft-surface);border:1px solid var(--ft-border);
                border-left:3px solid {color};border-radius:10px;
                padding:10px 14px;margin-bottom:6px;">
              <span style="font-weight:600;font-size:1rem">{icon} {p['merchant']}</span>
              <span class="ft-chip {chip_cls}">{status_lbl}</span>
              <span style="color:var(--ft-text2);font-size:0.85rem">{p.get('category','')}{sub}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1, 2])
        col1.caption(f"Valor médio: **{amount_fmt(p.get('avg_amount', 0))}**")
        col2.caption(freq)
        col3.caption(f"Ocorrências: **{p.get('occurrence_count', 0)}**")
        col4.caption(f"Última: {p.get('last_seen', '')[:7]}")

        # Botões de ação (icones nativos)
        pid = p["id"]
        btn_col1, btn_col2, btn_col3 = col5.columns(3)

        if status != "confirmed":
            if btn_col1.button("", icon=":material/check:", key=f"conf_{pid}", help="Confirmar"):
                update_pattern_status(pid, "confirmed")
                st.rerun()

        if status != "dismissed":
            if btn_col2.button("", icon=":material/close:", key=f"dis_{pid}", help="Descartar"):
                update_pattern_status(pid, "dismissed")
                st.rerun()

        if status == "dismissed":
            if btn_col3.button("", icon=":material/undo:", key=f"res_{pid}", help="Restaurar"):
                update_pattern_status(pid, "suggested")
                st.rerun()

        st.divider()
