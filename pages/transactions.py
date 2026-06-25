# -*- coding: utf-8 -*-
"""
Pagina: Lancamentos
Edicao inline por linha.
Ao definir uma nova categoria ou subcategoria, cria regra automatica.
"""
import streamlit as st

from services.transaction_service import (
    get_transactions, update_transaction, delete_transaction,
    bulk_delete_transactions, get_accounts, get_months, bulk_recategorize,
    mark_split_paid, effective_amount,
)
from services.categorization_service import get_categories, add_rule, refresh_rules_cache
from database.connection import db_session
from pages.components import page_header, amount_fmt, format_date_br
from utils.helpers import CATEGORY_ICONS, month_label

KNOWN_CATEGORIES = list(CATEGORY_ICONS.keys())
NEW_OPTION = "+ Digitar nova..."


# ── Helpers de dados ──────────────────────────────────────────────────────────

def _load_subcat_map():
    """Dict {categoria: [subcategorias]} unindo regras + transacoes."""
    with db_session() as conn:
        rows = conn.execute("""
            SELECT category, subcategory FROM category_rules
            WHERE subcategory IS NOT NULL AND subcategory != ''
            UNION
            SELECT category, subcategory FROM transactions
            WHERE subcategory IS NOT NULL AND subcategory != ''
            ORDER BY category, subcategory
        """).fetchall()
    result = {}
    for r in rows:
        cat, sub = r[0], r[1]
        result.setdefault(cat, [])
        if sub not in result[cat]:
            result[cat].append(sub)
    return result


def _all_cats():
    cats = KNOWN_CATEGORIES + get_categories()
    return list(dict.fromkeys(cats))


def _is_mobile():
    """Detecta celular pelo User-Agent (sem dependencia extra)."""
    try:
        ua = (st.context.headers.get("User-Agent") or "").lower()
    except Exception:
        return False
    return any(t in ua for t in
               ("iphone", "android", "ipod", "windows phone", "mobile"))


def _save_and_rule(tx_id, merchant, old_cat, new_cat, new_subcat,
                   new_desc, new_rec, is_new_cat, is_new_subcat):
    """
    Salva alteracoes e, se categoria ou subcategoria for nova,
    cria regra automatica para o merchant.
    """
    update_transaction(
        tx_id,
        description_norm=new_desc,
        merchant=merchant[:40],
        category=new_cat,
        subcategory=new_subcat,
        is_recurring=int(new_rec),
    )

    # Cria regra se categoria ou subcategoria mudou
    kw = (merchant or new_desc or "").strip().upper()
    if kw and (is_new_cat or is_new_subcat or new_cat != old_cat):
        add_rule(
            keyword=kw,
            match_type="contains",
            category=new_cat,
            subcategory=new_subcat,
            priority=8,
        )
        return True   # regra criada
    return False


# ── Render principal ──────────────────────────────────────────────────────────

def render():
    page_header("Lancamentos",
                "Edite categoria, subcategoria e status diretamente na lista.")

    # Cache do mapa de subcategorias
    if "subcat_map" not in st.session_state:
        st.session_state.subcat_map = _load_subcat_map()
    subcat_map = st.session_state.subcat_map

    # ── Filtros ───────────────────────────────────────────────────────────
    with st.expander("Filtros", expanded=True):
        f1, f2, f3, f4 = st.columns(4)
        months = [""] + get_months()
        month = f1.selectbox("Mes", months,
                             format_func=lambda m: "Todos" if not m else month_label(m))
        accounts = [""] + get_accounts()
        account  = f2.selectbox("Conta/Cartao", accounts,
                                format_func=lambda a: "Todas" if not a else a)
        cats = [""] + _all_cats()
        cats = list(dict.fromkeys(cats))
        category = f3.selectbox("Categoria", cats,
                                format_func=lambda c: "Todas" if not c else c)
        review = f4.selectbox(
            "Status revisao",
            ["pending", "", "reviewed", "ignored"],
            format_func=lambda s: {
                "": "Todos", "pending": "Pendente",
                "reviewed": "Revisado", "ignored": "Ignorado",
            }.get(s, s),
        )
        f5, f6, f7, f8 = st.columns([2, 1, 1, 1.2])
        search       = f5.text_input("Buscar descricao / merchant")
        min_val      = f6.number_input("Valor minimo", value=0.0, step=10.0)
        max_val      = f7.number_input("Valor maximo", value=0.0, step=100.0)
        only_install = f8.checkbox("So parceladas")
        st.segmented_control(
            "Visualizacao", ["Auto", "Tabela", "Cards"],
            default=st.session_state.get("tx_view", "Auto"),
            key="tx_view",
            help="Auto = tabela no PC e cards no celular.",
        )

    # ── Botao de re-categorizacao em lote ────────────────────────────────
    rc1, rc2, rc3 = st.columns([2, 2, 4])
    if rc1.button("Recategorizar pendentes", use_container_width=True,
                  help="Re-aplica todas as regras nos lancamentos ainda pendentes"):
        n = bulk_recategorize(only_pending=True, only_uncategorized=False)
        st.success(f"{n} lancamentos recategorizados.")
        st.rerun()
    if rc2.button("Recategorizar todos", use_container_width=True,
                  help="Re-aplica regras em TODOS os lancamentos (inclusive revisados)"):
        n = bulk_recategorize(only_pending=False, only_uncategorized=False)
        st.success(f"{n} lancamentos recategorizados.")
        st.rerun()

    txs = get_transactions(
        month=month or None, account=account or None,
        category=category or None, review_status=review or None,
        search=search or None,
        min_amount=min_val if min_val > 0 else None,
        max_amount=max_val if max_val > 0 else None,
    )
    if only_install:
        txs = [t for t in txs if t.get("installment_current")]

    if not txs:
        st.info("Nenhum lancamento encontrado.")
        return

    total   = sum(t["amount"] for t in txs)
    all_ids = [t["id"] for t in txs]
    _render_bulk_bar(txs, all_ids, total)
    st.divider()

    # Visualizacao: tabela (desktop) ou cards (celular)
    view = st.session_state.get("tx_view", "Auto")
    use_cards = (view == "Cards") or (view == "Auto" and _is_mobile())

    # Paginacao: renderiza em blocos para manter a pagina leve (PC e celular)
    if "tx_show_n" not in st.session_state:
        st.session_state.tx_show_n = 30
    show_n = st.session_state.tx_show_n
    if use_cards:
        for tx in txs[:show_n]:
            _render_card(tx, subcat_map)
    else:
        _render_table_header()
        for tx in txs[:show_n]:
            _render_row(tx, subcat_map)
    if len(txs) > show_n:
        st.caption(f"Mostrando {show_n} de {len(txs)} lancamentos.")
        if st.button(f"Carregar mais ({len(txs) - show_n} restantes)",
                     use_container_width=True, key="load_more_tx"):
            st.session_state.tx_show_n += 30
            st.rerun()


# ── Barra de lote ────────────────────────────────────────────────────────────

def _render_bulk_bar(txs, all_ids, total):
    if "selected_ids" not in st.session_state:
        st.session_state.selected_ids = set()
    selected = st.session_state.selected_ids

    c1, c2, c3, c4, c5 = st.columns([2.5, 1.2, 1.2, 1.6, 1.6])
    lbl = f"  |  {len(selected)} sel." if selected else ""
    c1.markdown(f"**{len(txs)} lancamentos**  |  **{amount_fmt(total)}**{lbl}")

    if c2.button("Selecionar todos", use_container_width=True):
        st.session_state.selected_ids = set(all_ids); st.rerun()
    if c3.button("Desmarcar todos", use_container_width=True):
        st.session_state.selected_ids = set(); st.rerun()

    if selected:
        if c4.button(f"Excluir {len(selected)} sel.", use_container_width=True, type="primary"):
            st.session_state["confirm_del_sel"] = True
        if st.session_state.get("confirm_del_sel"):
            st.warning("Confirma exclusao dos selecionados?")
            a, b, _ = st.columns([1, 1, 5])
            if a.button("Sim", type="primary", key="ok_sel"):
                _bulk_delete(list(selected))
                st.session_state.selected_ids = set()
                st.session_state["confirm_del_sel"] = False
                st.rerun()
            if b.button("Nao", key="no_sel"):
                st.session_state["confirm_del_sel"] = False; st.rerun()
    else:
        c4.button("Excluir selecionados", use_container_width=True, disabled=True)

    if c5.button(f"Excluir todos ({len(txs)})", use_container_width=True):
        st.session_state["confirm_del_all"] = True
    if st.session_state.get("confirm_del_all"):
        st.error(f"Apagara TODOS os {len(txs)} lancamentos!")
        a2, b2, _ = st.columns([1.3, 1, 4])
        if a2.button("Confirmar", type="primary", key="ok_all"):
            _bulk_delete(all_ids)
            st.session_state.selected_ids = set()
            st.session_state["confirm_del_all"] = False
            st.rerun()
        if b2.button("Cancelar", key="no_all"):
            st.session_state["confirm_del_all"] = False; st.rerun()

    # ── Alterar status / atributos em massa ───────────────────────────────
    st.markdown("###### Alterar em massa")
    sc1, sc2, sc3, sc4 = st.columns([1.7, 1.5, 1.5, 1.7])
    new_status = sc1.selectbox(
        "Status em massa",
        ["reviewed", "pending", "ignored"],
        format_func=lambda s: {"reviewed": "Revisado", "pending": "Pendente",
                               "ignored": "Ignorado"}[s],
        key="bulk_status_sel",
        label_visibility="collapsed",
    )
    n_sel = len(selected)
    if sc2.button(f"Status nos {n_sel} sel.", use_container_width=True,
                  disabled=not selected, help="Aplica o status escolhido aos selecionados"):
        _bulk_set_status(list(selected), new_status)
        st.success(f"{n_sel} lancamentos -> status atualizado.")
        st.rerun()
    if sc3.button(f"Status em todos ({len(txs)})", use_container_width=True,
                  help="Aplica o status escolhido a TODA a lista filtrada"):
        _bulk_set_status(all_ids, new_status)
        st.success(f"{len(all_ids)} lancamentos -> status atualizado.")
        st.rerun()
    if sc4.button(f"Recorrente nos {n_sel} sel.", use_container_width=True,
                  disabled=not selected, help="Marca os selecionados como recorrentes"):
        _bulk_set_recurring(list(selected), True)
        st.success(f"{n_sel} marcados como recorrente.")
        st.rerun()


def _bulk_delete(ids):
    bulk_delete_transactions(ids)


def _bulk_set_status(ids, status):
    """Atualiza review_status de varios lancamentos (preserva os demais campos)."""
    if not ids:
        return
    with db_session() as conn:
        conn.execute(
            f"UPDATE transactions SET review_status=?, updated_at=datetime('now') "
            f"WHERE id IN ({','.join('?'*len(ids))})",
            [status, *ids],
        )


def _bulk_set_recurring(ids, value):
    """Marca/desmarca is_recurring de varios lancamentos."""
    if not ids:
        return
    with db_session() as conn:
        conn.execute(
            f"UPDATE transactions SET is_recurring=?, updated_at=datetime('now') "
            f"WHERE id IN ({','.join('?'*len(ids))})",
            [1 if value else 0, *ids],
        )


# ── Linha inline ──────────────────────────────────────────────────────────────

def _third_party_form(tx):
    """Formulario para marcar o lancamento como de terceiro (100% ou dividido)."""
    tx_id   = tx["id"]
    tp_type = tx.get("third_party_type") or ""
    tp_name = tx.get("third_party_name") or tx.get("split_with") or ""
    with st.container(border=True):
        st.markdown(f"**Terceiro — {(tx.get('merchant') or '')[:30]}**")
        tc1, tc2, tc3 = st.columns([1, 1.2, 1])
        new_tp_type = tc1.selectbox(
            "Tipo", ["Nenhum", "full", "split"],
            index={"": 0, "full": 1, "split": 2}.get(tp_type, 0),
            format_func=lambda v: {"Nenhum": "Nenhum", "full": "100% terceiro", "split": "Dividido"}.get(v, v),
            key=f"tp_type_{tx_id}",
        )
        new_tp_name = tc2.text_input("Nome do terceiro", value=tp_name,
                                     key=f"tp_name_{tx_id}", placeholder="Ex: Brenda, Joao")
        if new_tp_type == "split":
            cur_sa = tx.get("split_amount") or 0.0
            new_sa = tc3.number_input("Valor do terceiro (R$)", value=float(cur_sa), min_value=0.0,
                                      max_value=float(tx.get("amount", 0)), step=0.01, key=f"tp_sa_{tx_id}")
        else:
            new_sa = None
        cb_paid, b_save, b_cancel = st.columns([1, 1, 1])
        new_paid = cb_paid.checkbox("Terceiro pagou", value=bool(tx.get("split_paid")), key=f"tp_paid_{tx_id}")
        if b_save.button("Salvar", key=f"tp_save_{tx_id}", type="primary"):
            final_type = new_tp_type if new_tp_type != "Nenhum" else None
            update_transaction(
                tx_id,
                third_party_type=final_type,
                third_party_name=new_tp_name.strip() if final_type == "full" else None,
                split_with=new_tp_name.strip() if final_type == "split" else None,
                split_amount=new_sa if final_type == "split" else None,
                split_paid=1 if new_paid else 0,
            )
            st.session_state[f"edit_3rd_{tx_id}"] = False
            st.rerun()
        if b_cancel.button("Cancelar", key=f"tp_cancel_{tx_id}"):
            st.session_state[f"edit_3rd_{tx_id}"] = False
            st.rerun()


def _tx_fields(tx):
    """Campos derivados de um lancamento, usados por card e por linha de tabela."""
    cur_cat    = tx.get("category", "Outros") or "Outros"
    cur_subcat = tx.get("subcategory", "") or ""
    cur_desc   = tx.get("description_norm", "") or tx.get("description_raw", "")
    status_now = tx.get("review_status", "pending")
    inst_lbl = ""
    if tx.get("installment_current") and tx.get("installment_total"):
        inst_lbl = f"  {tx['installment_current']}/{tx['installment_total']}"
    st_meta = {"pending": ("warn", "Pendente"), "reviewed": ("ok", "Revisado"),
               "ignored": ("mut", "Ignorado")}.get(status_now, ("warn", status_now))
    return {
        "id":         tx["id"],
        "is_rec":     bool(tx.get("is_recurring")),
        "cur_cat":    cur_cat,
        "cur_subcat": cur_subcat,
        "cur_desc":   cur_desc,
        "merchant":   tx.get("merchant", "") or cur_desc,
        "acct":       tx.get("account_label") or tx.get("import_source") or "",
        "status_now": status_now,
        "tp_type":    tx.get("third_party_type") or "",
        "tp_name":    tx.get("third_party_name") or tx.get("split_with") or "",
        "orig":       tx.get("amount", 0),
        "eff":        effective_amount(tx),
        "inst_lbl":   inst_lbl,
        "st_meta":    st_meta,
    }


def _sel_checkbox(container, tx_id):
    is_checked = tx_id in st.session_state.get("selected_ids", set())
    if container.checkbox("Selecionar", value=is_checked, key=f"chk_{tx_id}",
                          label_visibility="collapsed"):
        st.session_state.selected_ids.add(tx_id)
    else:
        st.session_state.selected_ids.discard(tx_id)


def _status_button(container, tx_id, status_now, st_meta):
    if container.button(st_meta[1], key=f"st_{tx_id}", use_container_width=True,
                        type="primary" if status_now == "reviewed" else "secondary"):
        nxt = {"pending": "reviewed", "reviewed": "ignored", "ignored": "pending"}
        update_transaction(tx_id, review_status=nxt.get(status_now, "reviewed"))
        st.rerun()


def _cat_subcat_widgets(c_cat, c_sub, tx_id, cur_cat, cur_subcat, subcat_map, collapsed):
    """Selects de categoria/subcategoria com '+ Digitar nova...'. Devolve as escolhas."""
    lbl = "collapsed" if collapsed else "visible"
    cat_opts = _all_cats() + [NEW_OPTION]
    cat_idx  = cat_opts.index(cur_cat) if cur_cat in cat_opts else 0
    cat_choice = c_cat.selectbox("Categoria", cat_opts, index=cat_idx,
                                 key=f"cat_{tx_id}", label_visibility=lbl)
    is_new_cat = False
    if cat_choice == NEW_OPTION:
        new_cat = c_cat.text_input("Nova categoria", key=f"cat_new_{tx_id}",
                                   placeholder="Nova categoria",
                                   label_visibility="collapsed").strip()
        is_new_cat = bool(new_cat)
    else:
        new_cat = cat_choice

    subcat_list = subcat_map.get(cur_cat, [])
    sub_opts = [""] + subcat_list + [NEW_OPTION]
    sub_idx  = sub_opts.index(cur_subcat) if cur_subcat in sub_opts else 0
    if new_cat != cur_cat:
        subcat_list = subcat_map.get(new_cat, [])
        sub_opts = [""] + subcat_list + [NEW_OPTION]
        sub_idx  = 0
    sub_choice = c_sub.selectbox("Subcategoria", sub_opts,
                                 index=min(sub_idx, len(sub_opts) - 1),
                                 key=f"sub_{tx_id}", label_visibility=lbl)
    is_new_sub = False
    if sub_choice == NEW_OPTION:
        new_subcat = c_sub.text_input("Nova subcategoria", key=f"sub_new_{tx_id}",
                                      placeholder="Nova subcategoria",
                                      label_visibility="collapsed").strip()
        is_new_sub = bool(new_subcat)
    elif sub_choice == "":
        new_subcat = cur_subcat
    else:
        new_subcat = sub_choice
    return cat_choice, new_cat, is_new_cat, sub_choice, new_subcat, is_new_sub


def _maybe_save(tx_id, merchant, cur_cat, cur_subcat, cur_desc, is_rec, subcat_map,
                cat_choice, new_cat, is_new_cat, sub_choice, new_subcat, is_new_sub,
                new_desc, new_rec):
    """Detecta mudancas, salva e cria regra; recarrega se algo mudou."""
    desc_changed    = new_desc.strip() != cur_desc.strip()
    cat_changed     = new_cat and new_cat != cur_cat
    subcat_changed  = new_subcat != cur_subcat
    rec_changed     = new_rec != is_rec
    waiting_new_cat = (cat_choice == NEW_OPTION and not new_cat)
    waiting_new_sub = (sub_choice == NEW_OPTION and not new_subcat and cat_choice != NEW_OPTION)
    if (desc_changed or cat_changed or subcat_changed or rec_changed) \
            and not waiting_new_cat and not waiting_new_sub and new_cat:
        rule_created = _save_and_rule(tx_id, merchant, cur_cat, new_cat, new_subcat,
                                      new_desc or cur_desc, new_rec, is_new_cat, is_new_sub)
        if new_subcat and new_subcat not in subcat_map.get(new_cat, []):
            subcat_map.setdefault(new_cat, []).append(new_subcat)
            st.session_state.subcat_map = subcat_map
        if rule_created:
            st.toast(f"Regra criada: '{(merchant or new_desc)[:30]}' -> {new_cat}"
                     + (f" / {new_subcat}" if new_subcat else ""), icon="✅")
        st.rerun()


def _handle_delete_click(tx_id, status_now):
    if status_now == "pending":
        delete_transaction(tx_id)
        st.session_state.selected_ids.discard(tx_id)
        st.rerun()
    else:
        st.session_state[f"confirm_del_{tx_id}"] = True


def _confirm_delete_block(tx_id):
    if st.session_state.get(f"confirm_del_{tx_id}"):
        st.warning("Excluir lancamento revisado?")
        d1, d2, _ = st.columns([1, 1, 4])
        if d1.button("Sim", key=f"ok_del_{tx_id}", type="primary"):
            delete_transaction(tx_id)
            st.session_state.selected_ids.discard(tx_id)
            st.session_state.pop(f"confirm_del_{tx_id}", None)
            st.rerun()
        if d2.button("Nao", key=f"no_del_{tx_id}"):
            st.session_state.pop(f"confirm_del_{tx_id}", None)
            st.rerun()


def _value_html(f, big=False):
    size = ";font-size:1.05rem" if big else ""
    if f["tp_type"] == "full":
        return f'<s style="color:var(--ft-muted)">{amount_fmt(f["orig"])}</s> <b>R$ 0</b>'
    if f["tp_type"] == "split":
        return (f'<b>{amount_fmt(f["eff"])}</b> '
                f'<s style="color:var(--ft-muted);font-size:.85em">{amount_fmt(f["orig"])}</s>')
    return f'<b style="font-weight:700{size}">{amount_fmt(f["orig"])}</b>'


def _chips_html(f, with_status=True):
    chips = ""
    if with_status:
        chips += f'<span class="ft-chip {f["st_meta"][0]}">{f["st_meta"][1]}</span> '
    if f["is_rec"]:
        chips += '<span class="ft-chip purple">recorrente</span> '
    if f["tp_type"] == "full":
        chips += f'<span class="ft-chip info">100% {f["tp_name"] or "terceiro"}</span> '
    elif f["tp_type"] == "split":
        chips += f'<span class="ft-chip info">dividido {f["tp_name"] or ""}</span> '
    return chips


# ── Card (celular) ──────────────────────────────────────────────────────────

def _render_card(tx, subcat_map):
    """Card de um lancamento (layout vertical, ideal para celular)."""
    f = _tx_fields(tx)
    tx_id = f["id"]

    with st.container(border=True):
        top = st.columns([0.5, 4.5, 2.2])
        _sel_checkbox(top[0], tx_id)

        with top[1]:
            st.markdown(f"**{(f['merchant'] or f['cur_desc'])[:44]}**"
                        + (f"  ·{f['inst_lbl']}" if f["inst_lbl"] else ""))
            meta = format_date_br(tx.get("tx_date", ""))
            if f["acct"]:
                meta += f"  ·  :blue[{f['acct']}]"
            st.caption(meta)
            st.markdown(f'<div style="margin-top:5px">{_chips_html(f)}</div>',
                        unsafe_allow_html=True)

        top[2].markdown(f'<div style="text-align:right">{_value_html(f, big=True)}</div>',
                        unsafe_allow_html=True)

        # Edicao rapida: categoria + subcategoria sempre abertas
        e1, e2 = st.columns(2)
        cat_choice, new_cat, is_new_cat, sub_choice, new_subcat, is_new_sub = \
            _cat_subcat_widgets(e1, e2, tx_id, f["cur_cat"], f["cur_subcat"],
                                subcat_map, collapsed=False)

        # Descricao + recorrencia num expander discreto
        with st.expander("Descricao / recorrencia"):
            display_desc = (f["cur_desc"] + f["inst_lbl"]).strip()
            new_desc_raw = st.text_input("Descricao", value=display_desc, key=f"desc_{tx_id}")
            new_desc = (new_desc_raw.replace(f["inst_lbl"], "").strip()
                        if f["inst_lbl"] else new_desc_raw.strip())
            new_rec  = st.checkbox("Recorrente (assinatura)", value=f["is_rec"], key=f"rec_{tx_id}")

        _maybe_save(tx_id, f["merchant"], f["cur_cat"], f["cur_subcat"], f["cur_desc"],
                    f["is_rec"], subcat_map, cat_choice, new_cat, is_new_cat,
                    sub_choice, new_subcat, is_new_sub, new_desc, new_rec)

        a = st.columns(3)
        _status_button(a[0], tx_id, f["status_now"], f["st_meta"])
        if a[1].button("Terceiro", key=f"3rd_{tx_id}", use_container_width=True,
                       icon=":material/group:"):
            st.session_state[f"edit_3rd_{tx_id}"] = not st.session_state.get(f"edit_3rd_{tx_id}", False)
            st.rerun()
        if a[2].button("Excluir", key=f"del_{tx_id}", use_container_width=True,
                       icon=":material/delete:"):
            _handle_delete_click(tx_id, f["status_now"])

        _confirm_delete_block(tx_id)
        if st.session_state.get(f"edit_3rd_{tx_id}"):
            _third_party_form(tx)


# ── Linha de tabela (desktop) ─────────────────────────────────────────────────

_ROW_COLS = [0.4, 2.6, 1.8, 1.8, 1.0, 1.15, 0.6]


def _render_table_header():
    h = st.columns(_ROW_COLS)
    for col, lab, align in zip(
        h,
        ["", "Lancamento", "Categoria", "Subcategoria", "Valor", "Status", ""],
        ["", "left", "left", "left", "right", "left", ""],
    ):
        if lab:
            col.markdown(
                f"<div style='color:var(--ft-text2);font-size:11px;font-weight:600;"
                f"text-transform:uppercase;letter-spacing:.04em;text-align:{align}'>{lab}</div>",
                unsafe_allow_html=True,
            )
    st.markdown("<hr style='margin:.2rem 0 .4rem;border-color:var(--ft-border)'>",
                unsafe_allow_html=True)


def _render_row(tx, subcat_map):
    """Linha compacta estilo tabela (desktop)."""
    f = _tx_fields(tx)
    tx_id = f["id"]

    cols = st.columns(_ROW_COLS, vertical_alignment="center")
    _sel_checkbox(cols[0], tx_id)

    with cols[1]:
        st.markdown(f"**{(f['merchant'] or f['cur_desc'])[:40]}**"
                    + (f"  ·{f['inst_lbl']}" if f["inst_lbl"] else ""))
        meta = format_date_br(tx.get("tx_date", ""))
        if f["acct"]:
            meta += f"  ·  :blue[{f['acct']}]"
        st.caption(meta)
        chips = _chips_html(f, with_status=False)
        if chips:
            st.markdown(f'<div style="margin-top:2px">{chips}</div>', unsafe_allow_html=True)

    cat_choice, new_cat, is_new_cat, sub_choice, new_subcat, is_new_sub = \
        _cat_subcat_widgets(cols[2], cols[3], tx_id, f["cur_cat"], f["cur_subcat"],
                            subcat_map, collapsed=True)

    cols[4].markdown(f'<div style="text-align:right">{_value_html(f)}</div>',
                     unsafe_allow_html=True)
    _status_button(cols[5], tx_id, f["status_now"], f["st_meta"])

    with cols[6].popover("⋯", use_container_width=True):
        display_desc = (f["cur_desc"] + f["inst_lbl"]).strip()
        new_desc_raw = st.text_input("Descricao", value=display_desc, key=f"desc_{tx_id}")
        new_desc = (new_desc_raw.replace(f["inst_lbl"], "").strip()
                    if f["inst_lbl"] else new_desc_raw.strip())
        new_rec  = st.checkbox("Recorrente (assinatura)", value=f["is_rec"], key=f"rec_{tx_id}")
        st.divider()
        if st.button("Terceiro", key=f"3rd_{tx_id}", use_container_width=True,
                     icon=":material/group:"):
            st.session_state[f"edit_3rd_{tx_id}"] = not st.session_state.get(f"edit_3rd_{tx_id}", False)
            st.rerun()
        if st.button("Excluir", key=f"del_{tx_id}", use_container_width=True,
                     icon=":material/delete:"):
            _handle_delete_click(tx_id, f["status_now"])

    _maybe_save(tx_id, f["merchant"], f["cur_cat"], f["cur_subcat"], f["cur_desc"],
                f["is_rec"], subcat_map, cat_choice, new_cat, is_new_cat,
                sub_choice, new_subcat, is_new_sub, new_desc, new_rec)

    _confirm_delete_block(tx_id)
    if st.session_state.get(f"edit_3rd_{tx_id}"):
        _third_party_form(tx)
    st.markdown("<hr style='margin:.25rem 0;border-color:var(--ft-border);opacity:.5'>",
                unsafe_allow_html=True)
