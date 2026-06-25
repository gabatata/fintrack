# -*- coding: utf-8 -*-
"""
Pagina: Excluidos

Dois mecanismos de bloqueio permanente:
1. Lancamentos excluidos (lapides): tudo que voce exclui vai pra ca e nao
   volta em reimportacoes -- inclusive as demais parcelas da mesma compra.
2. Bloqueio por nome: palavras-chave que nunca devem aparecer.
"""
import streamlit as st

from services.exclusion_service import (
    get_excluded, remove_excluded, clear_excluded,
    get_blocked_keywords, add_blocked_keyword, remove_blocked_keyword,
)
from pages.components import page_header, amount_fmt, format_date_br


def render():
    page_header("Excluidos",
                "Lancamentos que voce excluiu nao voltam em reimportacoes. "
                "Tambem da pra bloquear lancamentos por nome.")

    tab_tomb, tab_kw = st.tabs(["Lancamentos excluidos", "Bloqueio por nome"])

    with tab_tomb:
        _render_tombstones()

    with tab_kw:
        _render_keywords()


# ── Lapides ─────────────────────────────────────────────────────────────────

def _render_tombstones():
    rows = get_excluded()
    if not rows:
        st.info("Nenhum lancamento excluido ainda. Tudo que voce excluir em "
                "Lancamentos aparece aqui e fica bloqueado contra reimportacao.")
        return

    st.caption(f"{len(rows)} compra(s) bloqueada(s). "
               "Restaurar libera a volta em proximas importacoes "
               "(nao recria o lancamento agora).")

    cclear, _ = st.columns([1.4, 4])
    if cclear.button("Limpar todos", use_container_width=True,
                     help="Remove todas as lapides (todos poderao voltar a ser importados)"):
        st.session_state["confirm_clear_excluded"] = True
    if st.session_state.get("confirm_clear_excluded"):
        st.warning("Remover TODAS as lapides? Lancamentos excluidos poderao voltar.")
        a, b, _ = st.columns([1, 1, 5])
        if a.button("Sim, limpar", type="primary", key="ok_clear_exc"):
            clear_excluded()
            st.session_state["confirm_clear_excluded"] = False
            st.rerun()
        if b.button("Cancelar", key="no_clear_exc"):
            st.session_state["confirm_clear_excluded"] = False
            st.rerun()

    st.divider()

    # Cabecalho
    h = st.columns([3, 1.4, 1, 1.2, 1.3, 1.1])
    for col, lab in zip(h, ["Lancamento", "Data", "Parc.", "Valor parc.",
                            "Valor total", ""]):
        if lab:
            col.markdown(f"<div style='color:var(--ft-text2);font-size:11px;"
                         f"font-weight:600;text-transform:uppercase;"
                         f"letter-spacing:.04em'>{lab}</div>", unsafe_allow_html=True)
    st.markdown("<hr style='margin:.2rem 0 .4rem;border-color:var(--ft-border)'>",
                unsafe_allow_html=True)

    for r in rows:
        c = st.columns([3, 1.4, 1, 1.2, 1.3, 1.1], vertical_alignment="center")
        name = r.get("merchant") or r.get("description_norm") or "(sem nome)"
        acct = r.get("account_label") or ""
        c[0].markdown(f"**{name[:40]}**"
                      + (f"  ·  :blue[{acct}]" if acct else ""))
        c[1].caption(format_date_br(r.get("tx_date", "")))
        it = r.get("installment_total")
        c[2].caption(f"{it}x" if it else "-")
        c[3].caption(amount_fmt(r.get("amount") or 0))
        c[4].caption(amount_fmt(r.get("total_amount") or 0))
        if c[5].button("Restaurar", key=f"restore_{r['id']}",
                       use_container_width=True,
                       help="Libera a volta em proximas importacoes"):
            remove_excluded(r["id"])
            st.rerun()
        st.markdown("<hr style='margin:.25rem 0;border-color:var(--ft-border);"
                    "opacity:.5'>", unsafe_allow_html=True)


# ── Bloqueio por nome ─────────────────────────────────────────────────────────

def _render_keywords():
    st.caption("Lancamentos cujo nome contem (ou e exatamente) a palavra-chave "
               "nunca serao importados. Ao adicionar, os existentes que batem "
               "tambem sao removidos.")

    with st.form("add_blocked_kw", clear_on_submit=True):
        f1, f2 = st.columns([3, 1.4])
        kw = f1.text_input("Palavra-chave / nome a bloquear",
                           placeholder="Ex: WELLHUB ISABELE")
        mt = f2.selectbox("Tipo", ["contains", "exact"],
                          format_func=lambda v: {"contains": "Contem",
                                                 "exact": "Exato"}[v])
        note = st.text_input("Observacao (opcional)",
                             placeholder="Ex: assinatura da Isabele")
        submitted = st.form_submit_button("Adicionar bloqueio", type="primary",
                                          use_container_width=True,
                                          icon=":material/block:")
    if submitted:
        if not kw.strip():
            st.error("Informe a palavra-chave.")
        else:
            removed = add_blocked_keyword(kw, mt, note)
            msg = f"Bloqueio '{kw.strip().upper()}' adicionado."
            if removed:
                msg += f" {removed} lancamento(s) existente(s) removido(s)."
            st.success(msg)
            st.rerun()

    st.divider()

    kws = get_blocked_keywords()
    if not kws:
        st.info("Nenhum bloqueio por nome cadastrado.")
        return

    for k in kws:
        c = st.columns([2.5, 1, 3, 1.1], vertical_alignment="center")
        c[0].markdown(f"**{k['keyword']}**")
        c[1].caption("Contem" if k["match_type"] == "contains" else "Exato")
        c[2].caption(k.get("note") or "")
        if c[3].button("Remover", key=f"del_kw_{k['id']}",
                       use_container_width=True):
            remove_blocked_keyword(k["id"])
            st.rerun()
        st.markdown("<hr style='margin:.25rem 0;border-color:var(--ft-border);"
                    "opacity:.5'>", unsafe_allow_html=True)
