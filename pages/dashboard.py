# -*- coding: utf-8 -*-
"""
Dashboard FinTrack.
- Filtros globais (periodo, cartao, categoria) afetam TODOS os graficos
- Graficos clicaveis: clicar em uma barra/slice filtra os demais
- Projecao de parcelas por cartao correta (sem duplicar)
- Pareto inclui valores projetados no modo periodo amplo
- Datas antigas nao aparecem (usa billing_month obrigatorio na tabela de cartoes)
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from collections import defaultdict

from services.transaction_service import get_pending_review_count, get_accounts
from services.recurrence_service import get_recurring_patterns
from database.connection import db_session
from pages.components import page_header, amount_fmt, kpi_card
from utils.helpers import CATEGORY_ICONS, month_label, get_all_category_icons


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de periodo
# ─────────────────────────────────────────────────────────────────────────────

def _add_months(yr, mo, n):
    total = (yr - 1) * 12 + (mo - 1) + n
    return total // 12 + 1, total % 12 + 1


def _months_range(start: str, end: str) -> list[str]:
    result = []
    try:
        yr, mo = map(int, start.split("-"))
        eyr, emo = map(int, end.split("-"))
    except Exception:
        return [start]
    while (yr * 12 + mo) <= (eyr * 12 + emo):
        result.append(f"{yr}-{mo:02d}")
        mo += 1
        if mo > 12:
            mo, yr = 1, yr + 1
    return result


def _all_billing_months() -> list[str]:
    """Meses com billing_month real no banco (sem fallback por tx_date)."""
    with db_session() as conn:
        rows = conn.execute("""
            SELECT DISTINCT billing_month FROM transactions
            WHERE tx_type='debit' AND billing_month IS NOT NULL AND billing_month != ''
            ORDER BY billing_month
        """).fetchall()
    return [r[0] for r in rows if r[0]]


def _last_projection_month() -> str:
    """Calcula o ultimo mes de projecao das parcelas em aberto."""
    with db_session() as conn:
        rows = conn.execute("""
            SELECT billing_month, installment_current, installment_total
            FROM transactions
            WHERE installment_current IS NOT NULL AND tx_type='debit'
              AND billing_month IS NOT NULL
        """).fetchall()
    if not rows:
        today = date.today()
        return f"{today.year}-{today.month:02d}"
    last_month = ""
    for r in rows:
        remaining = (r["installment_total"] or 0) - (r["installment_current"] or 0)
        if remaining > 0 and r["billing_month"]:
            try:
                yr, mo = map(int, r["billing_month"].split("-"))
                pyr, pmo = _add_months(yr, mo, remaining)
                proj_mo = f"{pyr}-{pmo:02d}"
                if proj_mo > last_month:
                    last_month = proj_mo
            except Exception:
                pass
    return last_month or date.today().strftime("%Y-%m")


# ─────────────────────────────────────────────────────────────────────────────
# Dados filtrados
# ─────────────────────────────────────────────────────────────────────────────

def _query_transactions(date_from: str, date_to: str,
                         accounts: list, cats: list) -> list[dict]:
    """Transacoes reais no periodo, usando billing_month obrigatorio."""
    with db_session() as conn:
        params = [date_from, date_to]
        q = """
            SELECT * FROM transactions
            WHERE tx_type='debit' AND review_status!='ignored'
              AND billing_month IS NOT NULL
              AND billing_month >= ? AND billing_month <= ?
              AND (third_party_type IS NULL OR third_party_type != 'full')
        """
        if accounts:
            q += f" AND account_label IN ({','.join('?'*len(accounts))})"
            params.extend(accounts)
        if cats:
            q += f" AND category IN ({','.join('?'*len(cats))})"
            params.extend(cats)
        q += " ORDER BY billing_month DESC, tx_date DESC"
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def _monthly_summary(date_from: str, date_to: str,
                      accounts: list, cats: list) -> list[dict]:
    with db_session() as conn:
        params = [date_from, date_to]
        q = """
            SELECT billing_month as month,
                   SUM(CASE WHEN third_party_type='split' THEN amount - COALESCE(split_amount,0)
                            ELSE amount END) as total
            FROM transactions
            WHERE tx_type='debit' AND review_status!='ignored'
              AND billing_month IS NOT NULL
              AND (third_party_type IS NULL OR third_party_type != 'full')
              AND billing_month >= ? AND billing_month <= ?
        """
        if accounts:
            q += f" AND account_label IN ({','.join('?'*len(accounts))})"
            params.extend(accounts)
        if cats:
            q += f" AND category IN ({','.join('?'*len(cats))})"
            params.extend(cats)
        q += " GROUP BY billing_month ORDER BY billing_month"
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def _category_summary(date_from: str, date_to: str,
                       accounts: list, cats: list) -> list[dict]:
    with db_session() as conn:
        params = [date_from, date_to]
        q = """
            SELECT category,
                   SUM(CASE WHEN third_party_type='split' THEN amount - COALESCE(split_amount,0)
                            ELSE amount END) as total
            FROM transactions
            WHERE tx_type='debit' AND review_status!='ignored'
              AND billing_month IS NOT NULL
              AND (third_party_type IS NULL OR third_party_type != 'full')
              AND billing_month >= ? AND billing_month <= ?
        """
        if accounts:
            q += f" AND account_label IN ({','.join('?'*len(accounts))})"
            params.extend(accounts)
        if cats:
            q += f" AND category IN ({','.join('?'*len(cats))})"
            params.extend(cats)
        q += " GROUP BY category ORDER BY total DESC"
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def _subcategory_summary(date_from: str, date_to: str,
                          accounts: list, cats: list) -> list[dict]:
    with db_session() as conn:
        params = [date_from, date_to]
        q = """
            SELECT subcategory,
                   SUM(CASE WHEN third_party_type='split' THEN amount - COALESCE(split_amount,0)
                            ELSE amount END) as total
            FROM transactions
            WHERE tx_type='debit' AND review_status!='ignored'
              AND billing_month IS NOT NULL
              AND (third_party_type IS NULL OR third_party_type != 'full')
              AND subcategory IS NOT NULL AND subcategory != '' AND subcategory != 'None'
              AND billing_month >= ? AND billing_month <= ?
        """
        if accounts:
            q += f" AND account_label IN ({','.join('?'*len(accounts))})"
            params.extend(accounts)
        if cats:
            q += f" AND category IN ({','.join('?'*len(cats))})"
            params.extend(cats)
        q += " GROUP BY subcategory ORDER BY total DESC"
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def _get_installments(accounts: list) -> list[dict]:
    """Retorna parcelas em aberto para projecao."""
    with db_session() as conn:
        params = []
        q = """
            SELECT account_label, billing_month, amount,
                   installment_current, installment_total, merchant, category
            FROM transactions
            WHERE installment_current IS NOT NULL AND tx_type='debit'
              AND billing_month IS NOT NULL
              AND installment_current < installment_total
        """
        if accounts:
            q += f" AND account_label IN ({','.join('?'*len(accounts))})"
            params.extend(accounts)
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def _project_installments(date_from: str, date_to: str,
                           accounts: list, cats: list = None):
    """
    Projeta parcelas mes a mes POR CARTAO, com filtro opcional de categoria.
    Retorna dict: {(account_label, month_str): total}
    Tambem: {month_str: {category: total}} para pareto.
    """
    rows = _get_installments(accounts)
    _today = date.today().strftime("%Y-%m")  # projeta SO meses futuros (nao enche meses passados)

    # Dedup: para cada grupo de compra parcelada, pega a parcela mais recente
    groups = {}
    for r in rows:
        key = f"{r['merchant']}|{r['account_label']}|{r['installment_total']}|{round(r['amount'],0)}"
        if key not in groups or r['installment_current'] > groups[key]['max_seen']:
            groups[key] = {**r, 'max_seen': r['installment_current']}

    by_card_month   = defaultdict(float)   # (acc, month) -> total
    by_month_cat    = defaultdict(lambda: defaultdict(float))  # month -> cat -> total

    for g in groups.values():
        remaining = g['installment_total'] - g['max_seen']
        if remaining <= 0:
            continue
        # Filter by category if specified
        if cats and g.get('category') not in cats:
            continue
        try:
            yr, mo = map(int, g['billing_month'].split('-'))
        except Exception:
            continue
        for i in range(1, remaining + 1):
            pyr, pmo = _add_months(yr, mo, i)
            key = f"{pyr}-{pmo:02d}"
            if key > _today and date_from <= key <= date_to:
                by_card_month[(g['account_label'], key)] += g['amount']
                by_month_cat[key][g.get('category') or 'Outros'] += g['amount']

    return by_card_month, by_month_cat


def _build_card_table(date_from: str, date_to: str, accounts: list, cats: list = None):
    """Tabela cartao x mes com filtro de categoria. Projecao por cartao sem duplicar."""
    with db_session() as conn:
        params = [date_from, date_to]
        q = """
            SELECT account_label, billing_month,
                   SUM(CASE WHEN third_party_type='split' THEN amount - COALESCE(split_amount,0)
                            ELSE amount END) as total
            FROM transactions
            WHERE tx_type='debit' AND review_status!='ignored'
              AND billing_month IS NOT NULL
              AND (third_party_type IS NULL OR third_party_type != 'full')
              AND billing_month >= ? AND billing_month <= ?
              AND account_label IS NOT NULL AND account_label != ''
        """
        if accounts:
            q += f" AND account_label IN ({','.join('?'*len(accounts))})"
            params.extend(accounts)
        if cats:
            q += f" AND category IN ({','.join('?'*len(cats))})"
            params.extend(cats)
        q += " GROUP BY account_label, billing_month ORDER BY account_label, billing_month"
        rows = conn.execute(q, params).fetchall()

    real = defaultdict(float)
    all_accounts = set()
    all_months   = set()
    for r in rows:
        real[(r['account_label'], r['billing_month'])] += r['total']
        all_accounts.add(r['account_label'])
        all_months.add(r['billing_month'])

    proj_by_card, _ = _project_installments(date_from, date_to, accounts, cats)

    for (acc, mo) in proj_by_card:
        all_accounts.add(acc)
        all_months.add(mo)

    if not all_accounts:
        return pd.DataFrame()

    today_str    = date.today().strftime("%Y-%m")
    months_order = sorted(all_months)

    data = {}
    for acc in sorted(all_accounts):
        row = {}
        for mo in months_order:
            val  = real.get((acc, mo), 0)
            # Only add THIS card's projection, not all cards
            val += proj_by_card.get((acc, mo), 0)
            row[mo] = round(val, 2)
        data[acc] = row

    df = pd.DataFrame(data).T
    df.index.name = "Cartao / Conta"
    renamed = {mo: (month_label(mo) + ("*" if mo > today_str else "")) for mo in months_order}
    df = df.rename(columns=renamed)
    df["Total"] = df.sum(axis=1)
    df.loc["TOTAL"] = df.sum()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Pareto com projecoes incluidas
# ─────────────────────────────────────────────────────────────────────────────

def _category_with_projection(date_from: str, date_to: str,
                               accounts: list, cats: list) -> list[dict]:
    """Categoria somando real + projecao de parcelas (com filtro de categoria aplicado em ambos)."""
    real = {r['category']: r['total'] for r in
            _category_summary(date_from, date_to, accounts, cats)}

    # Projecao filtrada pela mesma lista de categorias
    _, by_month_cat = _project_installments(date_from, date_to, accounts, cats if cats else None)
    proj_cat = defaultdict(float)
    for mo_cats in by_month_cat.values():
        for cat, val in mo_cats.items():
            proj_cat[cat] += val

    combined = defaultdict(float)
    for cat, v in real.items():
        combined[cat] += v
    for cat, v in proj_cat.items():
        combined[cat] += v

    result = [{"category": c, "total": round(v, 2)} for c, v in combined.items() if v > 0]
    return sorted(result, key=lambda x: -x["total"])


# ─────────────────────────────────────────────────────────────────────────────
# Grafico de Pareto clicavel
# ─────────────────────────────────────────────────────────────────────────────

def _embed_scrollable_fig(fig, min_w: int, height: int) -> None:
    """
    Renderiza a figura preenchendo TODA a largura no desktop e rolando na
    lateral no celular. Em vez de fixar a largura (que deixa um vazio a direita
    em telas largas), o Plotly fica responsivo dentro de um wrapper com
    `min-width`: no desktop o wrapper estica ate o container (grafico preenche);
    no celular o `min-width` forca a rolagem horizontal. Requer internet (CDN).
    """
    fig.update_layout(autosize=True,
                      paper_bgcolor="#182235", plot_bgcolor="#182235",
                      font=dict(color="#F8FAFC"))
    inner = fig.to_html(include_plotlyjs="cdn", full_html=False,
                        default_width="100%", default_height="100%",
                        config={"displayModeBar": False, "responsive": True})
    components.html(
        "<style>html,body{margin:0;background:#182235;overflow-y:hidden}"
        "::-webkit-scrollbar{height:9px}"
        "::-webkit-scrollbar-thumb{background:#33415A;border-radius:9px}</style>"
        '<div style="overflow-x:auto;overflow-y:hidden;background:#182235;">'
        f'<div style="min-width:{min_w}px;height:{height}px;">{inner}</div></div>',
        height=height + 32,
    )


def _pareto_chart(title: str, df_in: pd.DataFrame, name_col: str,
                  value_col: str, click_key: str) -> str | None:
    """
    Retorna o nome do item clicado (ou None).
    O clique atualiza o filtro de categoria via session_state.
    """
    if df_in.empty:
        st.info(f"Sem dados para {title}.")
        return None

    # Mostra todos os itens; cada barra tem largura fixa e o card rola na horizontal
    df = df_in.sort_values(value_col, ascending=False).reset_index(drop=True)
    total = df[value_col].sum()
    if total <= 0:
        return None

    df["pct"]     = df[value_col] / total * 100
    df["pct_acc"] = df["pct"].cumsum()
    df["xlabel"]  = df.apply(
        lambda r: f"{str(r[name_col])[:16]}<br><sub>{r['pct']:.1f}%</sub>", axis=1
    )

    # Destaca o item selecionado como filtro
    clicked_cat = st.session_state.get("click_cat", "")
    bar_colors = []
    for nm in df[name_col]:
        if clicked_cat and nm == clicked_cat:
            bar_colors.append("#FFD700")   # gold = selecionado
        else:
            bar_colors.append("#3B82F6")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["xlabel"], y=df[value_col],
        name="Valor (R$)",
        marker_color=bar_colors,
        text=df[value_col].map(amount_fmt),
        textposition="outside",
        textfont=dict(size=11, color="#ffffff"),
        width=0.7, yaxis="y",
        customdata=df[name_col],
    ))
    fig.add_trace(go.Scatter(
        x=df["xlabel"], y=df["pct_acc"],
        name="% Acumulado",
        mode="lines+markers+text",
        line=dict(color="#FACC15", width=2),
        marker=dict(size=6, color="#FACC15"),
        text=df["pct_acc"].map(lambda x: f"{x:.0f}%"),
        textposition="top center",
        textfont=dict(size=12, color="#FACC15"),
        yaxis="y2",
    ))
    fig.add_hline(y=80, line_dash="dash", line_color="rgba(255,255,255,0.3)", yref="y2")
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=14)),
        # Rotulos na vertical + automargin: nao se sobrepoem em nenhuma largura (PC e celular)
        xaxis=dict(tickangle=-90, tickfont=dict(size=11), gridcolor="rgba(255,255,255,0.06)", automargin=True),
        yaxis=dict(title="Valor (R$)", showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   range=[0, df[value_col].max() * 1.30]),
        yaxis2=dict(title="", overlaying="y", side="right",
                    range=[0, 115], showgrid=False, ticksuffix="%", tickfont=dict(size=10)),
        showlegend=False,
        margin=dict(l=52, r=44, t=70, b=30),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=480, bargap=0.2,
    )

    # Largura minima por barra: legivel no celular (rola lateral) e preenche no PC.
    # Embarcado porque o st.plotly_chart encolhe o grafico ao container.
    # Trade-off: sem clique-para-filtrar aqui (use o card de filtros). Requer internet.
    n = len(df)
    bar_px  = 84
    min_w   = max(680, n * bar_px)
    chart_h = int(fig.layout.height or 480)
    _embed_scrollable_fig(fig, min_w, chart_h)
    return None



def _nature_summary(date_from: str, date_to: str,
                    accounts: list, cats: list) -> dict:
    """
    Retorna totais por natureza (necessario/cortavel/sem_classificacao)
    para o periodo, incluindo projecoes de parcelas.
    """
    with db_session() as conn:
        params = [date_from, date_to]
        q = """
            SELECT cr.nature,
                   SUM(CASE WHEN t.third_party_type='split'
                            THEN t.amount - COALESCE(t.split_amount,0)
                            ELSE t.amount END) as total
            FROM transactions t
            LEFT JOIN (
                SELECT category, nature FROM category_rules
                GROUP BY category
            ) cr ON cr.category = t.category
            WHERE t.tx_type='debit' AND t.review_status!='ignored'
              AND t.billing_month IS NOT NULL
              AND (t.third_party_type IS NULL OR t.third_party_type != 'full')
              AND t.billing_month >= ? AND t.billing_month <= ?
        """
        if accounts:
            q += f" AND t.account_label IN ({','.join('?'*len(accounts))})"
            params.extend(accounts)
        if cats:
            q += f" AND t.category IN ({','.join('?'*len(cats))})"
            params.extend(cats)
        q += " GROUP BY cr.nature"
        rows = conn.execute(q, params).fetchall()

    result = {"necessario": 0.0, "cortavel": 0.0, "sem_classificacao": 0.0}
    for r in rows:
        nat = r["nature"] or "sem_classificacao"
        result[nat] = round(r["total"] or 0, 2)

    # Add installment projections by nature
    _, by_month_cat = _project_installments(date_from, date_to, accounts,
                                             cats if cats else None)
    with db_session() as conn:
        nat_map = {r["category"]: r["nature"] for r in conn.execute(
            "SELECT category, nature FROM category_rules GROUP BY category"
        ).fetchall()}

    for mo_cats in by_month_cat.values():
        for cat, val in mo_cats.items():
            nat = nat_map.get(cat) or "sem_classificacao"
            result[nat] = result.get(nat, 0.0) + val

    return result


def _monthly_by_nature(date_from: str, date_to: str,
                        accounts: list, cats: list) -> pd.DataFrame:
    """
    Retorna DataFrame com colunas: month, necessario, cortavel
    para o grafico de media movel.
    """
    with db_session() as conn:
        params = [date_from, date_to]
        q = """
            SELECT t.billing_month as month,
                   cr.nature,
                   SUM(CASE WHEN t.third_party_type='split'
                            THEN t.amount - COALESCE(t.split_amount,0)
                            ELSE t.amount END) as total
            FROM transactions t
            LEFT JOIN (
                SELECT category, nature FROM category_rules GROUP BY category
            ) cr ON cr.category = t.category
            WHERE t.tx_type='debit' AND t.review_status!='ignored'
              AND t.billing_month IS NOT NULL
              AND (t.third_party_type IS NULL OR t.third_party_type != 'full')
              AND t.billing_month >= ? AND t.billing_month <= ?
        """
        if accounts:
            q += f" AND t.account_label IN ({','.join('?'*len(accounts))})"
            params.extend(accounts)
        if cats:
            q += f" AND t.category IN ({','.join('?'*len(cats))})"
            params.extend(cats)
        q += " GROUP BY t.billing_month, cr.nature ORDER BY t.billing_month"
        rows = conn.execute(q, params).fetchall()

    if not rows:
        return pd.DataFrame()

    from collections import defaultdict
    monthly = defaultdict(lambda: {"necessario": 0.0, "cortavel": 0.0})
    for r in rows:
        nat = r["nature"] or "cortavel"
        monthly[r["month"]][nat] += r["total"] or 0

    df = pd.DataFrame([
        {"month": mo, **vals} for mo, vals in sorted(monthly.items())
    ])
    df["total"] = df["necessario"] + df["cortavel"]
    df["month_label"] = df["month"].apply(month_label)
    return df


def _subcategory_with_projection(date_from: str, date_to: str,
                                  accounts: list, cats: list) -> list[dict]:
    """Subcategoria somando real + projecao de parcelas (igual ao de categoria)."""
    real = {}
    for r in _subcategory_summary(date_from, date_to, accounts, cats):
        real[r['subcategory']] = r['total']

    # Projeta parcelas com subcategoria
    with db_session() as conn:
        params = []
        q = """
            SELECT merchant, subcategory, amount,
                   installment_current, installment_total,
                   billing_month, account_label
            FROM transactions
            WHERE installment_current IS NOT NULL AND tx_type='debit'
              AND billing_month IS NOT NULL
              AND installment_current < installment_total
              AND subcategory IS NOT NULL AND subcategory != '' AND subcategory != 'None'
        """
        if accounts:
            q += f" AND account_label IN ({','.join('?'*len(accounts))})"
            params.extend(accounts)
        if cats:
            q += f" AND category IN ({','.join('?'*len(cats))})"
            params.extend(cats)
        rows = conn.execute(q, params).fetchall()

    # Dedup by group
    groups = {}
    for r in rows:
        key = f"{r['merchant']}|{r['account_label']}|{r['installment_total']}|{round(r['amount'],0)}"
        if key not in groups or r['installment_current'] > groups[key]['max_seen']:
            groups[key] = {**dict(r), 'max_seen': r['installment_current']}

    proj = defaultdict(float)
    _today = date.today().strftime("%Y-%m")  # projeta SO meses futuros
    for g in groups.values():
        remaining = g['installment_total'] - g['max_seen']
        if remaining <= 0:
            continue
        try:
            yr, mo = map(int, g['billing_month'].split('-'))
        except Exception:
            continue
        for i in range(1, remaining + 1):
            pyr, pmo = _add_months(yr, mo, i)
            key = f"{pyr}-{pmo:02d}"
            if key > _today and date_from <= key <= date_to:
                proj[g['subcategory']] += g['amount']

    combined = defaultdict(float)
    for sub, v in real.items():
        combined[sub] += v
    for sub, v in proj.items():
        combined[sub] += v

    result = [{"subcategory": s, "total": round(v, 2)}
              for s, v in combined.items() if v > 0]
    return sorted(result, key=lambda x: -x["total"])


def _merchant_summary(date_from: str, date_to: str,
                       accounts: list, cats: list) -> list[dict]:
    """
    Agrupa por merchant somando real + projecao de parcelas.
    Normaliza o nome do merchant para agrupar variantes (99Food, 99food, etc).
    """
    with db_session() as conn:
        params = [date_from, date_to]
        q = """
            SELECT UPPER(TRIM(merchant)) as merch,
                   SUM(CASE WHEN third_party_type='split'
                            THEN amount - COALESCE(split_amount,0)
                            ELSE amount END) as total
            FROM transactions
            WHERE tx_type='debit' AND review_status!='ignored'
              AND billing_month IS NOT NULL
              AND (third_party_type IS NULL OR third_party_type != 'full')
              AND merchant IS NOT NULL AND merchant != ''
              AND billing_month >= ? AND billing_month <= ?
        """
        if accounts:
            q += f" AND account_label IN ({','.join('?'*len(accounts))})"
            params.extend(accounts)
        if cats:
            q += f" AND category IN ({','.join('?'*len(cats))})"
            params.extend(cats)
        q += " GROUP BY UPPER(TRIM(merchant)) ORDER BY total DESC"
        rows = conn.execute(q, params).fetchall()

    real = {r["merch"]: r["total"] for r in rows if r["merch"]}

    # Add installment projections per merchant
    with db_session() as conn:
        params2 = []
        q2 = """
            SELECT UPPER(TRIM(merchant)) as merch, amount,
                   installment_current, installment_total,
                   billing_month, account_label
            FROM transactions
            WHERE installment_current IS NOT NULL AND tx_type='debit'
              AND billing_month IS NOT NULL
              AND installment_current < installment_total
        """
        if accounts:
            q2 += f" AND account_label IN ({','.join('?'*len(accounts))})"
            params2.extend(accounts)
        if cats:
            q2 += f" AND category IN ({','.join('?'*len(cats))})"
            params2.extend(cats)
        rows2 = conn.execute(q2, params2).fetchall()

    groups = {}
    for r in rows2:
        key = f"{r['merch']}|{r['account_label']}|{r['installment_total']}|{round(r['amount'],0)}"
        if key not in groups or r['installment_current'] > groups[key]['max_seen']:
            groups[key] = {**dict(r), 'max_seen': r['installment_current']}

    proj = defaultdict(float)
    _today = date.today().strftime("%Y-%m")  # projeta SO meses futuros
    for g in groups.values():
        remaining = g['installment_total'] - g['max_seen']
        if remaining <= 0:
            continue
        try:
            yr, mo = map(int, g['billing_month'].split('-'))
        except Exception:
            continue
        for i in range(1, remaining + 1):
            pyr, pmo = _add_months(yr, mo, i)
            key = f"{pyr}-{pmo:02d}"
            if key > _today and date_from <= key <= date_to:
                proj[g['merch']] += g['amount']

    combined = defaultdict(float)
    for m, v in real.items():
        combined[m] += v
    for m, v in proj.items():
        combined[m] += v

    result = [{"merchant": m, "total": round(v, 2)}
              for m, v in combined.items() if v > 0]
    return sorted(result, key=lambda x: -x["total"])

# ─────────────────────────────────────────────────────────────────────────────
# Pagina principal
# ─────────────────────────────────────────────────────────────────────────────

def render():
    page_header("Dashboard", "Visao geral das suas financas")

    # Inicializa session_state para cliques
    if "click_cat" not in st.session_state:
        st.session_state.click_cat = ""
    if "click_month" not in st.session_state:
        st.session_state.click_month = ""

    all_billing  = _all_billing_months()
    all_accounts = get_accounts()
    all_icons    = get_all_category_icons()

    with db_session() as conn:
        cat_rows = conn.execute(
            "SELECT DISTINCT category FROM transactions WHERE tx_type='debit' ORDER BY category"
        ).fetchall()
    all_cats_db = [r[0] for r in cat_rows if r[0]]

    today_str    = date.today().strftime("%Y-%m")
    last_proj    = _last_projection_month()
    all_proj_mos = _months_range(today_str, last_proj)
    all_mos_opts = sorted(set(all_billing + all_proj_mos))

    # ── Filtros (card) ──────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**Filtros**")
        row1 = st.columns([1, 1, 1, 1])

        # Periodo De/Ate - janela padrao LEGIVEL: ~13 meses ate ~6 meses a frente.
        # (evita um grafico com 30 barras ilegiveis; o usuario pode ampliar no filtro)
        _to_y, _to_m = _add_months(*map(int, today_str.split("-")), 6)
        _desired_to = f"{_to_y}-{_to_m:02d}"
        _to_cands = [m for m in all_mos_opts if m <= _desired_to]
        _default_to = _to_cands[-1] if _to_cands else all_mos_opts[-1]
        _fr_y, _fr_m = _add_months(*map(int, _default_to.split("-")), -13)
        _desired_from = f"{_fr_y}-{_fr_m:02d}"
        _first_real = all_billing[0] if all_billing else today_str
        _cand_from = max(_first_real, _desired_from)
        _from_cands = [m for m in all_mos_opts if m >= _cand_from]
        _default_from = _from_cands[0] if _from_cands else all_mos_opts[0]
        default_from_idx = all_mos_opts.index(_default_from)
        default_to_idx   = all_mos_opts.index(_default_to)

        period_from = row1[0].selectbox(
            "Periodo de", all_mos_opts, index=default_from_idx,
            format_func=month_label, key="pf",
        )
        period_to = row1[1].selectbox(
            "Ate", all_mos_opts, index=default_to_idx,
            format_func=month_label, key="pt",
        )

        # Mes especifico
        month_opts = ["Todos"] + all_billing
        click_mo   = st.session_state.click_month
        click_idx  = month_opts.index(click_mo) if click_mo in month_opts else 0
        month_sel  = row1[2].selectbox(
            "Mes especifico", month_opts, index=click_idx,
            format_func=lambda m: "Todos" if m == "Todos" else month_label(m),
            key="ms",
        )
        if month_sel != "Todos":
            period_from = month_sel
            period_to   = month_sel

        # Cartao
        acc_all = row1[3].checkbox("Todos os cartoes", value=True, key="aa")
        if not acc_all:
            sel_acc = st.multiselect("Cartoes", all_accounts,
                                      default=all_accounts, key="sa")
        else:
            sel_acc = []

        # Categoria - pode vir do clique no pareto
        row2 = st.columns([2, 1])
        cat_all = row2[1].checkbox("Todas as categorias", value=not bool(st.session_state.click_cat), key="ca")
        if not cat_all:
            click_c = st.session_state.click_cat
            default_cats = [click_c] if click_c and click_c in all_cats_db else all_cats_db
            sel_cat = row2[0].multiselect(
                "Categorias", all_cats_db, default=default_cats,
                format_func=lambda c: f"{all_icons.get(c,'')} {c}", key="sc",
            )
        else:
            sel_cat = []
            st.session_state.click_cat = ""

        # Botao limpar filtros de clique
        if st.session_state.click_cat or st.session_state.click_month:
            if row2[0].button("Limpar filtros de clique", key="clr"):
                st.session_state.click_cat   = ""
                st.session_state.click_month = ""
                st.rerun()

    st.write("")

    # ── Busca ─────────────────────────────────────────────────────────────
    txs     = _query_transactions(period_from, period_to, sel_acc, sel_cat)
    monthly = _monthly_summary(period_from, period_to, sel_acc, sel_cat)

    total_period      = sum(t["amount"] for t in txs)
    installment_total = sum(t["amount"] for t in txs if t.get("installment_current"))
    recurring_total   = sum(t["amount"] for t in txs if t.get("is_recurring"))
    pending_count     = get_pending_review_count()
    months_count      = len({t["billing_month"] for t in txs if t.get("billing_month")}) or 1
    avg_monthly       = total_period / months_count

    # ── KPIs ──────────────────────────────────────────────────────────────
    n_parc = sum(1 for t in txs if t.get("installment_current"))
    n_rec  = sum(1 for t in txs if t.get("is_recurring"))
    _kpis = (
        kpi_card("Total no periodo", amount_fmt(total_period), "cash", "#3B82F6", f"{len(txs)} lancamentos")
        + kpi_card("Media mensal", amount_fmt(avg_monthly), "bars", "#8B5CF6", f"{months_count} meses")
        + kpi_card("Parcelas", amount_fmt(installment_total), "layers", "#FACC15", f"{n_parc} ativas")
        + kpi_card("Recorrentes", amount_fmt(recurring_total), "refresh", "#22C55E", f"{n_rec} lancamentos")
        + kpi_card("Pendentes", str(pending_count), "clock", "#EF4444", "a revisar")
    )
    st.markdown(f'<div class="ft-kpis">{_kpis}</div>', unsafe_allow_html=True)

    st.divider()

    # ── Grafico mensal clicavel ───────────────────────────────────────────
    st.markdown("**Gasto por Fatura**")
    if monthly:
        df_m = pd.DataFrame(monthly)
        df_m["month_label"] = df_m["month"].apply(month_label)

        proj_by_card, _ = _project_installments(period_from, period_to, sel_acc,
                                                     sel_cat if sel_cat else None)
        proj_by_month   = defaultdict(float)
        for (acc, mo), v in proj_by_card.items():
            proj_by_month[mo] += v

        real_months = set(df_m["month"])
        proj_rows   = [
            {"month": mo, "total": val, "month_label": month_label(mo) + "*"}
            for mo, val in sorted(proj_by_month.items()) if mo not in real_months
        ]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_m["month_label"], y=df_m["total"],
            name="Realizado", marker_color="#3B82F6",
            text=df_m["total"].map(amount_fmt),
            textposition="outside",
            textfont=dict(size=13, color="#ffffff"),
            width=0.6, customdata=df_m["month"],
        ))
        if proj_rows:
            df_p = pd.DataFrame(proj_rows)
            fig.add_trace(go.Bar(
                x=df_p["month_label"], y=df_p["total"],
                name="Projecao", marker_color="#FACC15",
                text=df_p["total"].map(amount_fmt),
                textposition="outside",
                textfont=dict(size=13, color="#ffffff"),
                width=0.6, customdata=df_p["month"],
            ))

        max_val = max(
            df_m["total"].max() if not df_m.empty else 0,
            max((r["total"] for r in proj_rows), default=0),
        ) * 1.28

        n_months = len(df_m) + len(proj_rows)
        scroll_monthly = n_months > 8

        fig.update_layout(
            xaxis=dict(tickangle=-30, tickfont=dict(size=13)),
            yaxis=dict(title="Total (R$)", range=[0, max_val],
                       showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
            legend=dict(orientation="h", y=-0.2),
            margin=dict(l=10, r=10, t=44, b=72),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=420, barmode="group", bargap=0.25,
            title=dict(
                text=("<sup>Arraste o grafico para o lado para ver todos os meses</sup>"
                      if scroll_monthly
                      else "<sup>Clique em uma barra para filtrar o mes</sup>"),
                font=dict(size=12)),
        )

        if scroll_monthly:
            # Muitos meses: min-width por barra -> preenche no PC e rola lateral no celular.
            # Trade-off: sem clique-para-filtrar aqui (use o card de filtros). Requer internet.
            bar_px  = 96
            min_w   = max(680, n_months * bar_px)
            chart_h = int(fig.layout.height or 420)
            _embed_scrollable_fig(fig, min_w, chart_h)
        else:
            ev = st.plotly_chart(fig, width="stretch", on_select="rerun", key="chart_monthly")
            if ev and ev.selection and ev.selection.points:
                pt = ev.selection.points[0]
                mo = pt.get("customdata")
                if mo and mo != st.session_state.click_month:
                    st.session_state.click_month = str(mo)
                    st.rerun()
    else:
        st.info("Sem dados no periodo selecionado.")

    # ── Tabela por cartao ─────────────────────────────────────────────────
    st.divider()
    st.markdown("**Gasto Mensal por Cartao**")
    st.caption("Meses com * sao projecoes. Projecao calculada por cartao separadamente.")

    df_card = _build_card_table(period_from, period_to, sel_acc,
                                sel_cat if sel_cat else None)
    if not df_card.empty:
        def _fmt(v):
            if isinstance(v, (int, float)):
                return "-" if v == 0 else "R$ " + f"{v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
            return v
        st.dataframe(df_card.map(_fmt), use_container_width=True)
    else:
        st.info("Sem dados de cartao no periodo.")

    # ── Pareto (inclui projecoes quando nao e mes unico) ─────────────────
    is_single_month = (period_from == period_to)
    if is_single_month:
        cat_data = _category_summary(period_from, period_to, sel_acc, sel_cat)
        sub_data = _subcategory_summary(period_from, period_to, sel_acc, sel_cat)
    else:
        cat_data = _category_with_projection(period_from, period_to, sel_acc, sel_cat)
        sub_data = _subcategory_summary(period_from, period_to, sel_acc, sel_cat)

    if cat_data:
        st.divider()
        st.markdown("**Analise de Pareto**")
        note = "Inclui valores projetados de parcelas." if not is_single_month else ""
        st.caption(f"Arraste o gráfico para o lado para ver todos os itens. {note}")

        df_cat = pd.DataFrame(cat_data)
        df_cat = df_cat[df_cat["total"] > 0]

        clicked = _pareto_chart("Pareto por Categoria", df_cat, "category", "total", "pareto_cat")
        if clicked and clicked != st.session_state.click_cat:
            st.session_state.click_cat = clicked
            st.rerun()

        # Subcategoria com projecoes
        sub_data_proj = (_subcategory_with_projection(period_from, period_to, sel_acc, sel_cat)
                         if not is_single_month
                         else sub_data)
        if sub_data_proj:
            df_sub = pd.DataFrame(sub_data_proj)
            df_sub = df_sub[df_sub["total"] > 0]
            _pareto_chart("Pareto por Subcategoria", df_sub, "subcategory", "total", "pareto_sub")

        # Merchant / item
        merch_data = _merchant_summary(period_from, period_to, sel_acc, sel_cat)
        if merch_data:
            df_merch = pd.DataFrame(merch_data[:30])  # top 30
            df_merch = df_merch[df_merch["total"] > 0]
            _pareto_chart("Pareto por Estabelecimento", df_merch, "merchant", "total", "pareto_merch")

    # ── Media Movel ───────────────────────────────────────────────────────
    df_nat = _monthly_by_nature(period_from, period_to, sel_acc, sel_cat)
    if len(df_nat) >= 2:
        st.divider()
        st.markdown("**Evolucao e Tendencia**")

        mm_window = st.radio(
            "Janela da media movel",
            [3, 6], index=0,
            format_func=lambda x: f"{x} meses",
            horizontal=True,
        )

        df_nat["mm"] = df_nat["total"].rolling(window=mm_window, min_periods=1).mean()

        fig_mm = go.Figure()
        fig_mm.add_trace(go.Bar(
            x=df_nat["month_label"], y=df_nat["total"],
            name="Gasto Real", marker_color="rgba(59,130,246,0.5)",
            yaxis="y",
        ))
        fig_mm.add_trace(go.Scatter(
            x=df_nat["month_label"], y=df_nat["mm"],
            name=f"Tendencia ({mm_window}m)",
            mode="lines+markers",
            line=dict(color="#FACC15", width=3),
            marker=dict(size=7),
        ))
        fig_mm.update_layout(
            xaxis=dict(tickangle=-30, tickfont=dict(size=13)),
            yaxis=dict(title="Total (R$)", showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
            legend=dict(orientation="h", y=-0.2),
            margin=dict(l=10, r=10, t=44, b=72),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=360, barmode="group",
        )
        st.plotly_chart(fig_mm, width="stretch")

    # ── Necessarios vs Cortaveis ──────────────────────────────────────────
    nat_data = _nature_summary(period_from, period_to, sel_acc, sel_cat)
    nec   = nat_data.get("necessario", 0)
    cort  = nat_data.get("cortavel", 0)
    total_nat = nec + cort or 1

    if nec + cort > 0:
        st.divider()
        col_donut, col_table = st.columns([1, 1.2])

        with col_donut:
            st.markdown("**Necessarios vs Cortaveis**")
            fig_donut = go.Figure(go.Pie(
                labels=["Necessarios", "Cortaveis"],
                values=[nec, cort],
                hole=0.55,
                marker_colors=["#3B82F6", "#FACC15"],
                textinfo="percent+label",
                textfont=dict(size=14),
            ))
            fig_donut.update_layout(
                showlegend=False,
                margin=dict(l=0, r=0, t=20, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                height=250,
                annotations=[dict(
                    text=f"<b>{amount_fmt(nec+cort)}</b>",
                    x=0.5, y=0.5, font_size=14,
                    showarrow=False
                )],
            )
            st.plotly_chart(fig_donut, use_container_width=True)

        with col_table:
            st.markdown("**Detalhe por categoria**")
            if cat_data:
                with db_session() as conn:
                    nat_map = {r["category"]: r["nature"] for r in conn.execute(
                        "SELECT category, nature FROM category_rules GROUP BY category"
                    ).fetchall()}
                rows_nec  = [(c["category"], c["total"]) for c in cat_data
                              if nat_map.get(c["category"]) == "necessario"]
                rows_cort = [(c["category"], c["total"]) for c in cat_data
                              if nat_map.get(c["category"]) != "necessario"]
                all_icons = get_all_category_icons()

                if rows_nec:
                    st.caption(f"✅ **Necessarios** — {amount_fmt(nec)} ({nec/total_nat*100:.0f}%)")
                    for cat, val in rows_nec[:6]:
                        icon = all_icons.get(cat, "")
                        c1, c2 = st.columns([3, 1])
                        c1.write(f"{icon} {cat}")
                        c2.write(amount_fmt(val))
                if rows_cort:
                    st.caption(f"✂️ **Cortaveis** — {amount_fmt(cort)} ({cort/total_nat*100:.0f}%)")
                    for cat, val in rows_cort[:6]:
                        icon = all_icons.get(cat, "")
                        c1, c2 = st.columns([3, 1])
                        c1.write(f"{icon} {cat}")
                        c2.write(amount_fmt(val))

    # ── Top categorias ────────────────────────────────────────────────────
    if cat_data:
        st.divider()
        st.markdown("**Top Categorias**")
        total_cats = sum(c["total"] for c in cat_data) or 1
        for row in cat_data[:10]:
            icon = all_icons.get(row["category"], "")
            pct  = row["total"] / total_cats * 100
            cols = st.columns([0.05, 0.25, 0.4, 0.15, 0.15])
            cols[0].write(icon)
            cols[1].write(row["category"])
            cols[2].progress(int(pct))
            cols[3].write(f"{pct:.1f}%")
            cols[4].write(amount_fmt(row["total"]))

    # ── Assinaturas confirmadas ───────────────────────────────────────────
    confirmed = [p for p in get_recurring_patterns() if p["status"] == "confirmed"]
    if confirmed:
        st.divider()
        st.markdown("**Assinaturas Confirmadas**")
        df_rec = pd.DataFrame(confirmed)[
            ["merchant", "avg_amount", "frequency", "last_seen", "category"]
        ]
        df_rec.columns = ["Servico", "Valor Medio", "Frequencia", "Ultima vez", "Categoria"]
        df_rec["Valor Medio"] = df_rec["Valor Medio"].apply(amount_fmt)
        st.dataframe(df_rec, use_container_width=True, hide_index=True)
