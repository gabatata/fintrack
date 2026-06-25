# -*- coding: utf-8 -*-
"""
FinTrack - Gestao Financeira Pessoal
Aplicacao Streamlit para uso pessoal (acesso via rede privada Tailscale).
"""
import streamlit as st
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Nuvem (Streamlit Cloud): copia os secrets do Supabase para variaveis de
# ambiente ANTES de inicializar o banco (que baixa o DB da nuvem se configurado).
# Sem secrets (uso local), nada acontece e o app usa o banco local.
try:
    _sb = st.secrets.get("supabase")
    if _sb:
        os.environ.setdefault("FINTRACK_SUPABASE_URL", _sb["url"])
        os.environ.setdefault("FINTRACK_SUPABASE_KEY", _sb["key"])
        if _sb.get("bucket"):
            os.environ.setdefault("FINTRACK_SUPABASE_BUCKET", _sb["bucket"])
        if _sb.get("db_object"):
            os.environ.setdefault("FINTRACK_DB_OBJECT", _sb["db_object"])
except Exception:
    pass

from database import init_database
init_database()

from pages import (
    dashboard, import_pdf, transactions, recurring,
    manual_expense, category_rules, import_history, receivables, excluded,
)

st.set_page_config(
    page_title="FinTrack",
    page_icon="\U0001F4B0",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root{
  --ft-bg:#0F172A; --ft-sidebar:#111827; --ft-surface:#182235; --ft-surface2:#1E293B;
  --ft-border:#263244;
  --ft-text:#F8FAFC; --ft-text2:#94A3B8; --ft-muted:#64748B;
  --ft-accent:#3B82F6; --ft-green:#22C55E; --ft-red:#EF4444; --ft-yellow:#FACC15; --ft-purple:#8B5CF6;
  --ft-radius:16px; --ft-radius-sm:12px;
  --ft-shadow:0 1px 3px rgba(0,0,0,.35), 0 1px 2px rgba(0,0,0,.22);
}

/* Base / tipografia */
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"]{
  font-family:'Inter', system-ui, sans-serif;
}
[data-testid="stAppViewContainer"]{ background:var(--ft-bg); }
.ft-num, [data-testid="stMetricValue"]{ font-variant-numeric:tabular-nums; letter-spacing:-.01em; }
h1{ font-weight:700; letter-spacing:-.025em; }
h2,h3{ font-weight:600; letter-spacing:-.02em; }

/* Esconde o chrome do Streamlit + barra de ferramentas dos graficos */
#MainMenu{ visibility:hidden; }
/* Oculta SO o clutter da toolbar (deploy/menu) -- mantem a toolbar para o botao de expandir a sidebar */
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], [data-testid="stDecoration"], footer{ display:none !important; }
header[data-testid="stHeader"]{ background:transparent; }
.modebar{ display:none !important; }

.block-container{ padding:2.2rem 2rem 3rem; max-width:100%; }

/* st.metric -> card de KPI */
[data-testid="stMetric"]{
  background:var(--ft-surface); border:1px solid var(--ft-border);
  border-radius:var(--ft-radius); padding:16px 18px; box-shadow:var(--ft-shadow);
}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] *{
  color:var(--ft-text2); font-size:12.5px; font-weight:500;
  white-space:normal; overflow:visible; text-overflow:clip;
}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] *{
  font-size:1.2rem !important; font-weight:700 !important; color:var(--ft-text) !important;
  white-space:normal !important; overflow:visible !important; text-overflow:clip !important;
}

/* Sidebar (mais estreita + itens alinhados a esquerda) */
[data-testid="stSidebar"]{ background:var(--ft-sidebar); border-right:1px solid var(--ft-border); }
[data-testid="stSidebar"][aria-expanded="true"]{ width:212px !important; min-width:212px !important; max-width:212px !important; }
/* Botao de recolher/reabrir a sidebar SEMPRE visivel (Streamlit o esconde ate o hover) */
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapsedControl"] button,
[data-testid="stExpandSidebarButton"], [data-testid="stExpandSidebarButton"] button,
[data-testid="collapsedControl"], [data-testid="collapsedControl"] button{
  visibility:visible !important; opacity:1 !important; color:var(--ft-text) !important;
}
/* Botao de REABRIR (sidebar recolhida): fundo/borda para ficar bem visivel */
[data-testid="stExpandSidebarButton"] button, [data-testid="stSidebarCollapsedControl"] button,
[data-testid="collapsedControl"] button{
  background:var(--ft-surface) !important; border:1px solid var(--ft-border) !important;
  border-radius:9px !important;
}
[data-testid="stExpandSidebarButton"] svg, [data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarCollapsedControl"] svg, [data-testid="collapsedControl"] svg{
  color:var(--ft-text) !important; fill:var(--ft-text) !important;
}
[data-testid="stSidebar"] .stButton > button{
  width:100%; justify-content:flex-start !important; text-align:left !important;
  background:transparent !important; border:none !important; color:var(--ft-text2) !important;
  font-weight:500; padding:9px 12px; border-radius:10px; transition:all .12s ease;
}
[data-testid="stSidebar"] .stButton > button > div,
[data-testid="stSidebar"] .stButton > button p{ justify-content:flex-start !important; text-align:left !important; width:100%; }
[data-testid="stSidebar"] .stButton > button:hover{ background:rgba(148,163,184,.08) !important; color:var(--ft-text) !important; }
[data-testid="stSidebar"] .stButton > button[kind="primary"]{
  background:rgba(59,130,246,.16) !important; color:#93C5FD !important; box-shadow:inset 3px 0 0 var(--ft-accent);
}

/* Marca */
.ft-brand{ display:flex; align-items:center; gap:11px; padding:6px 6px 8px; }
.ft-logo{ width:36px; height:36px; border-radius:11px; background:var(--ft-accent);
  display:grid; place-items:center; color:#0B1220; box-shadow:0 2px 10px rgba(59,130,246,.4); }
.ft-brand b{ font-size:19px; font-weight:700; letter-spacing:-.02em; color:var(--ft-text); }

/* Divisores e utilitarios */
hr{ border-color:var(--ft-border) !important; margin:.9rem 0; }
.ft-card{ background:var(--ft-surface); border:1px solid var(--ft-border);
  border-radius:var(--ft-radius); padding:18px 20px; margin-bottom:14px; box-shadow:var(--ft-shadow); }
.ft-chip{ font-size:11px; font-weight:600; padding:3px 9px; border-radius:8px; }

/* KPI cards customizados (grid responsivo) */
.ft-kpis{ display:grid; grid-template-columns:repeat(auto-fit, minmax(190px,1fr)); gap:14px; margin-bottom:6px; }
.ft-kpi{ background:var(--ft-surface); border:1px solid var(--ft-border);
  border-radius:var(--ft-radius); padding:16px 18px; position:relative; box-shadow:var(--ft-shadow); transition:border-color .15s ease; }
.ft-kpi:hover{ border-color:#33415A; }
.ft-kpi-ico{ position:absolute; top:15px; right:15px; width:32px; height:32px;
  border-radius:10px; display:grid; place-items:center; }
.ft-kpi-lab{ color:var(--ft-text2); font-size:12.5px; font-weight:500; margin-bottom:9px; padding-right:38px; white-space:nowrap; }
.ft-kpi-val{ font-size:22px; font-weight:700; letter-spacing:-.02em; color:var(--ft-text); white-space:nowrap; }
.ft-kpi-sub{ color:var(--ft-muted); font-size:12px; margin-top:7px; white-space:nowrap; }

/* Graficos e tabelas como cards */
[data-testid="stPlotlyChart"]{
  background:var(--ft-surface); border:1px solid var(--ft-border); border-radius:var(--ft-radius);
  padding:0 14px; box-shadow:var(--ft-shadow); margin-bottom:6px; overflow:visible;
}
[data-testid="stDataFrame"]{
  background:var(--ft-surface); border:1px solid var(--ft-border); border-radius:var(--ft-radius);
  overflow:hidden; box-shadow:var(--ft-shadow);
}
[data-testid="stTable"]{ border:1px solid var(--ft-border); border-radius:var(--ft-radius); overflow:hidden; }
/* Container com borda (st.container(border=True)) -> card */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div [data-testid="stVerticalBlock"]){ box-shadow:var(--ft-shadow); }
div[data-testid="stVerticalBlockBorderWrapper"]{ border-radius:var(--ft-radius) !important; }

/* Inputs, selects e date */
div[data-baseweb="select"] > div{ background:var(--ft-surface2) !important; border-color:var(--ft-border) !important; border-radius:10px !important; }
.stTextInput input, .stNumberInput input, .stDateInput input{
  background:var(--ft-surface2) !important; border-radius:10px !important; border-color:var(--ft-border) !important; color:var(--ft-text) !important;
}
/* Botoes do conteudo principal */
[data-testid="stAppViewContainer"] .stButton > button{
  border-radius:10px; border:1px solid var(--ft-border); font-weight:500; transition:all .12s ease;
}
[data-testid="stAppViewContainer"] .stButton > button:hover{ border-color:var(--ft-accent); color:#93C5FD; }
[data-testid="stAppViewContainer"] .stButton > button[kind="primary"]{
  background:var(--ft-accent); border-color:var(--ft-accent); color:#0B1220;
}
[data-testid="stAppViewContainer"] .stButton > button[kind="primary"]:hover{ filter:brightness(1.08); color:#0B1220; }
/* Expander (filtros) */
[data-testid="stExpander"]{ border:1px solid var(--ft-border) !important; border-radius:var(--ft-radius) !important;
  background:var(--ft-surface) !important; box-shadow:var(--ft-shadow); }
[data-testid="stExpander"] summary{ font-weight:500; }
/* Segmented control */
[data-testid="stSegmentedControl"] button{ border-radius:9px; }
/* Chips de status */
.ft-chip.ok{   background:rgba(34,197,94,.16);   color:#4ADE80; }
.ft-chip.warn{ background:rgba(250,204,21,.16);  color:#FACC15; }
.ft-chip.info{ background:rgba(59,130,246,.16);  color:#60A5FA; }
.ft-chip.bad{  background:rgba(239,68,68,.16);   color:#F87171; }
.ft-chip.mut{  background:var(--ft-surface2);    color:var(--ft-text2); }
.ft-chip.purple{ background:rgba(139,92,246,.18); color:#A78BFA; }

/* Responsivo - celular */
@media (max-width:640px){
  .block-container{ padding-left:1rem !important; padding-right:1rem !important; padding-top:1.2rem !important; }
  h1{ font-size:1.4rem !important; }
  .ft-kpis{ grid-template-columns:repeat(2, 1fr) !important; }
}
</style>
""", unsafe_allow_html=True)

# ── Navegacao ─────────────────────────────────────────────────────────────────
PAGES = [
    "Dashboard",
    "Importar PDF",
    "Lancamentos",
    "Recorrentes",
    "Despesa Manual",
    "Regras de Categorizacao",
    "Historico de Importacoes",
    "A Receber",
    "Excluidos",
]

PAGE_ICONS = {
    "Dashboard":                ":material/grid_view:",
    "Importar PDF":             ":material/upload_file:",
    "Lancamentos":              ":material/receipt_long:",
    "Recorrentes":              ":material/autorenew:",
    "Despesa Manual":           ":material/add_card:",
    "Regras de Categorizacao":  ":material/rule:",
    "Historico de Importacoes": ":material/history:",
    "A Receber":                ":material/call_received:",
    "Excluidos":                ":material/block:",
}

if "current_page" not in st.session_state:
    st.session_state.current_page = "Dashboard"


def _go_to(page_name: str):
    st.session_state.current_page = page_name


with st.sidebar:
    # Cabecalho com marca
    st.markdown(
        "<div class='ft-brand'>"
        "<div class='ft-logo'><svg width='20' height='20' viewBox='0 0 24 24' fill='none' "
        "stroke='#062138' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
        "<path d='M19 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0 0 4h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7'/>"
        "<circle cx='16' cy='13' r='1.5' fill='#062138' stroke='none'/></svg></div>"
        "<b>FinTrack</b></div>",
        unsafe_allow_html=True,
    )
    st.caption("Gestao Financeira Pessoal")
    st.divider()

    from services.transaction_service import get_pending_review_count
    pending = get_pending_review_count()

    for p in PAGES:
        label = p
        if p == "Lancamentos" and pending > 0:
            label = f"{p}  ({pending})"

        is_active = st.session_state.current_page == p
        btn_type  = "primary" if is_active else "secondary"

        if st.button(label, key=f"nav_{p}", icon=PAGE_ICONS.get(p),
                     use_container_width=True, type=btn_type):
            _go_to(p)
            st.rerun()

    st.divider()
    st.caption("v1.0 - FinTrack")

# ── Roteamento ────────────────────────────────────────────────────────────────
page = st.session_state.current_page

if page == "Dashboard":
    dashboard.render()
elif page == "Importar PDF":
    import_pdf.render()
elif page == "Lancamentos":
    transactions.render()
elif page == "Recorrentes":
    recurring.render()
elif page == "Despesa Manual":
    manual_expense.render()
elif page == "Regras de Categorizacao":
    category_rules.render()
elif page == "Historico de Importacoes":
    import_history.render()
elif page == "A Receber":
    receivables.render()
elif page == "Excluidos":
    excluded.render()
