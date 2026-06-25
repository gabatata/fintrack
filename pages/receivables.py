# -*- coding: utf-8 -*-
"""
Pagina: A Receber
Lista lancamentos marcados como de terceiros (full ou split),
com status de pago/pendente e totais por pessoa.
"""
import streamlit as st
from services.transaction_service import get_receivables, mark_split_paid, update_transaction
from pages.components import page_header, amount_fmt, format_date_br


def render():
    page_header(
        "A Receber",
        "Lancamentos pagos no seu cartao mas que sao total ou parcialmente de terceiros.",
    )

    rows = get_receivables()

    if not rows:
        st.info("Nenhum lancamento marcado como de terceiro ainda.")
        st.caption(
            "Para marcar, va em Lancamentos, clique no botao '+' na coluna '3ro' "
            "e defina se e 100% de terceiro ou valor dividido."
        )
        return

    # ── Resumo por pessoa ─────────────────────────────────────────────────
    by_person = {}
    for r in rows:
        name = r.get("third_party_name") or r.get("split_with") or "Sem nome"
        if name not in by_person:
            by_person[name] = {"total": 0.0, "count": 0}
        tp = r.get("third_party_type")
        if tp == "full":
            val = r.get("amount") or 0
        else:
            val = r.get("split_amount") or 0
        by_person[name]["total"] += val
        by_person[name]["count"] += 1

    st.markdown("**Resumo por pessoa**")
    summary_cols = st.columns(min(len(by_person), 4))
    for i, (name, info) in enumerate(sorted(by_person.items(), key=lambda x: -x[1]["total"])):
        summary_cols[i % 4].metric(
            label=name,
            value=amount_fmt(info["total"]),
            delta=f"{info['count']} lancamento(s)",
            delta_color="off",
        )

    st.divider()

    # ── Filtros ───────────────────────────────────────────────────────────
    f1, f2 = st.columns([1.5, 1])
    person_filter = f1.selectbox(
        "Filtrar por pessoa",
        ["Todos"] + sorted(by_person.keys()),
    )
    type_filter = f2.selectbox(
        "Tipo",
        ["Todos", "100% terceiro", "Dividido"],
        format_func=lambda x: x,
    )

    filtered = rows
    if person_filter != "Todos":
        filtered = [
            r for r in filtered
            if (r.get("third_party_name") or r.get("split_with") or "Sem nome") == person_filter
        ]
    if type_filter == "100% terceiro":
        filtered = [r for r in filtered if r.get("third_party_type") == "full"]
    elif type_filter == "Dividido":
        filtered = [r for r in filtered if r.get("third_party_type") == "split"]

    if not filtered:
        st.info("Nenhum lancamento com estes filtros.")
        return

    total_filtered = sum(
        (r.get("amount") if r.get("third_party_type") == "full"
         else r.get("split_amount") or 0)
        for r in filtered
    )
    st.markdown(f"**{len(filtered)} lancamentos | Total a receber: {amount_fmt(total_filtered)}**")
    st.divider()

    # ── Cabecalho ─────────────────────────────────────────────────────────
    hdr = st.columns([1.0, 2.5, 1.2, 1.2, 1.2, 1.2, 0.8])
    for col, lbl in zip(hdr, ["Data", "Descricao", "Pessoa", "Tipo", "Total orig.", "A receber", "Pago"]):
        col.markdown(f"**{lbl}**")
    st.divider()

    # ── Linhas ────────────────────────────────────────────────────────────
    for r in filtered:
        tx_id = r["id"]
        tp    = r.get("third_party_type")
        name  = r.get("third_party_name") or r.get("split_with") or "—"
        orig  = r.get("amount") or 0
        recv  = orig if tp == "full" else (r.get("split_amount") or 0)
        paid  = bool(r.get("split_paid"))
        desc  = r.get("merchant") or r.get("description_norm") or r.get("description_raw", "")

        c_date, c_desc, c_name, c_type, c_orig, c_recv, c_paid = \
            st.columns([1.0, 2.5, 1.2, 1.2, 1.2, 1.2, 0.8])

        c_date.markdown(f"`{format_date_br(r.get('tx_date',''))}`")

        # Descricao com parcela se houver
        inst = ""
        if r.get("installment_current") and r.get("installment_total"):
            inst = f" [{r['installment_current']}/{r['installment_total']}]"
        c_desc.markdown(f"{desc[:35]}{inst}")

        c_name.markdown(f"**{name}**")
        c_type.markdown(
            '<span class="ft-chip info">Total</span>' if tp == "full"
            else '<span class="ft-chip mut">Dividido</span>',
            unsafe_allow_html=True,
        )

        c_orig.markdown(f"~~{amount_fmt(orig)}~~" if tp == "full" else amount_fmt(orig))
        c_recv.markdown(f"**{amount_fmt(recv)}**")

        # Toggle pago/pendente
        new_paid = c_paid.checkbox(
            "", value=paid, key=f"paid_{tx_id}",
            label_visibility="collapsed",
        )
        if new_paid != paid:
            mark_split_paid(tx_id, new_paid)
            st.rerun()

    st.divider()

    # Botao marcar todos pagos
    col_a, col_b, _ = st.columns([1.5, 1.5, 4])
    if col_a.button("Marcar todos como pagos", use_container_width=True):
        for r in filtered:
            mark_split_paid(r["id"], True)
        st.rerun()
    if col_b.button("Marcar todos como pendentes", use_container_width=True):
        for r in filtered:
            mark_split_paid(r["id"], False)
        st.rerun()
