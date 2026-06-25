# -*- coding: utf-8 -*-
"""
Pagina: Regras e Categorias
Gestao de categorias e regras de categorizacao automatica.
"""
import streamlit as st
import pandas as pd

from services.categorization_service import (
    get_all_rules, add_rule, update_rule, delete_rule, refresh_rules_cache,
)
from services.transaction_service import bulk_recategorize
from database.connection import db_session
from pages.components import page_header
from utils.helpers import CATEGORY_ICONS

MATCH_LABELS = {
    "contains": "Contem",
    "startswith": "Comeca com",
    "exact": "Exato",
    "regex": "Regex",
}


def _all_categories():
    """Returns deduplicated sorted list of all categories."""
    with db_session() as conn:
        rule_cats = [r[0] for r in conn.execute(
            "SELECT DISTINCT category FROM category_rules ORDER BY category"
        ).fetchall()]
        tx_cats = [r[0] for r in conn.execute(
            "SELECT DISTINCT category FROM transactions WHERE category IS NOT NULL ORDER BY category"
        ).fetchall()]
    all_cats = list(dict.fromkeys(rule_cats + tx_cats))  # preserves order, deduplicates
    return sorted(set(all_cats))


def _all_subcategories():
    """Subcategorias ja cadastradas (regras + transacoes)."""
    with db_session() as conn:
        a = [r[0] for r in conn.execute(
            "SELECT DISTINCT subcategory FROM category_rules "
            "WHERE subcategory IS NOT NULL AND subcategory != '' ORDER BY subcategory"
        ).fetchall()]
        b = [r[0] for r in conn.execute(
            "SELECT DISTINCT subcategory FROM transactions "
            "WHERE subcategory IS NOT NULL AND subcategory != '' ORDER BY subcategory"
        ).fetchall()]
    return sorted(set(a + b))


def render():
    page_header("Regras e Categorias",
                "Gerencie categorias e palavras-chave para classificacao automatica.")

    tab_cats, tab_rules = st.tabs(["Categorias", "Regras de Palavra-chave"])

    with tab_cats:
        _tab_categories()

    with tab_rules:
        _tab_rules()


# ─── Aba Categorias ───────────────────────────────────────────────────────────

def _tab_categories():
    from utils.helpers import get_all_category_icons, set_category_icon

    cats = _all_categories()
    all_icons = get_all_category_icons()

    col_list, col_form = st.columns([1, 2])

    with col_list:
        st.markdown("**Categorias existentes**")
        st.caption("Clique em uma categoria para editar o emoji ou nome.")
        if cats:
            for c in cats:
                icon = all_icons.get(c, "")
                label = f"{icon}  {c}" if icon else c
                if st.button(label, key=f"edit_cat_{c}", use_container_width=True):
                    # Toggle: clique abre/fecha o editor desta categoria
                    current = st.session_state.get("editing_cat")
                    st.session_state["editing_cat"] = None if current == c else c
                    st.rerun()
        else:
            st.info("Nenhuma categoria ainda.")

    with col_form:
        # Editor inline da categoria selecionada
        editing = st.session_state.get("editing_cat")
        if editing and editing in cats:
            cur_icon = all_icons.get(editing, "")
            st.markdown(f"**Editando: {cur_icon} {editing}**")
            # Get current nature
            with db_session() as _conn:
                _nat_row = _conn.execute(
                    "SELECT nature FROM category_rules WHERE category=? LIMIT 1",
                    (editing,)
                ).fetchone()
            cur_nature = (_nat_row[0] if _nat_row and _nat_row[0] else "cortavel")

            with st.form(f"edit_cat_form_{editing}", clear_on_submit=False):
                new_icon = st.text_input(
                    "Emoji / icone",
                    value=cur_icon,
                    help="Cole um emoji diretamente aqui, ex: 🐾"
                )
                new_name_edit = st.text_input(
                    "Novo nome (deixe em branco para manter)",
                    value="",
                    placeholder=editing,
                )
                new_nature = st.radio(
                    "Natureza do gasto",
                    options=["necessario", "cortavel"],
                    index=0 if cur_nature == "necessario" else 1,
                    format_func=lambda v: "✅ Necessário (alimentação, saúde, moradia...)" if v == "necessario"
                                         else "✂️ Cortável (lazer, compras, assinaturas...)",
                    horizontal=True,
                )
                c_save, c_cancel = st.columns(2)
                btn_save   = c_save.form_submit_button("Salvar", type="primary")
                btn_cancel = c_cancel.form_submit_button("Cancelar")

            if btn_save:
                # Salva icone
                if new_icon.strip() != cur_icon:
                    set_category_icon(editing, new_icon.strip())
                # Salva natureza
                with db_session() as _conn:
                    _conn.execute(
                        "UPDATE category_rules SET nature=? WHERE category=?",
                        (new_nature, editing)
                    )

                # Renomeia se informou novo nome
                new_name_clean = new_name_edit.strip()
                if new_name_clean and new_name_clean != editing:
                    with db_session() as conn:
                        conn.execute(
                            "UPDATE category_rules SET category=? WHERE category=?",
                            (new_name_clean, editing)
                        )
                        conn.execute(
                            "UPDATE transactions SET category=? WHERE category=?",
                            (new_name_clean, editing)
                        )
                        conn.execute(
                            "INSERT OR REPLACE INTO app_config (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                            (f"icon:{new_name_clean}", new_icon.strip() or cur_icon)
                        )
                        conn.execute(
                            "DELETE FROM app_config WHERE key=?",
                            (f"icon:{editing}",)
                        )
                    refresh_rules_cache()
                    st.success(f"'{editing}' renomeada para '{new_name_clean}'")
                else:
                    st.success(f"Icone de '{editing}' atualizado.")

                st.session_state["editing_cat"] = None
                st.rerun()

            if btn_cancel:
                st.session_state["editing_cat"] = None
                st.rerun()

            st.divider()

        # Criar nova categoria
        st.markdown("**Criar nova categoria**")
        st.caption("Uma categoria precisa ter ao menos uma palavra-chave inicial.")
        with st.form("new_cat_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            new_cat_name = c1.text_input("Nome da categoria", placeholder="Ex: Pets")
            new_cat_icon = c2.text_input("Icone (emoji)", placeholder="Ex: 🐾")
            kw_inicial   = st.text_input("Palavra-chave inicial", placeholder="Ex: PETSHOP")
            subcat       = st.text_input("Subcategoria (opcional)")
            btn_create   = st.form_submit_button("Criar categoria", type="primary")

        if btn_create:
            if not new_cat_name.strip() or not kw_inicial.strip():
                st.error("Informe o nome da categoria e ao menos uma palavra-chave.")
            else:
                add_rule(
                    keyword=kw_inicial.strip().upper(),
                    match_type="contains",
                    category=new_cat_name.strip(),
                    subcategory=subcat.strip(),
                    priority=5,
                )
                if new_cat_icon.strip():
                    set_category_icon(new_cat_name.strip(), new_cat_icon.strip())
                st.success(f"Categoria '{new_cat_name.strip()}' criada.")
                st.session_state["editing_cat"] = None
                st.rerun()

        st.divider()

        # Renomear categoria (mantido como alternativa rapida)
        if cats and not editing:
            st.markdown("**Renomear categoria**")
            st.caption("Ou clique na categoria ao lado para editar.")
            with st.form("rename_cat_form", clear_on_submit=True):
                old_cat  = st.selectbox("Categoria atual", cats)
                new_name = st.text_input("Novo nome")
                btn_ren  = st.form_submit_button("Renomear", type="primary")

            if btn_ren and new_name.strip():
                with db_session() as conn:
                    conn.execute(
                        "UPDATE category_rules SET category=? WHERE category=?",
                        (new_name.strip(), old_cat)
                    )
                    conn.execute(
                        "UPDATE transactions SET category=? WHERE category=?",
                        (new_name.strip(), old_cat)
                    )
                refresh_rules_cache()
                st.success(f"'{old_cat}' renomeada para '{new_name.strip()}'")
                st.rerun()


# ─── Aba Regras ───────────────────────────────────────────────────────────────

def _tab_rules():
    cats = _all_categories()
    subs = _all_subcategories()

    with st.expander("Adicionar nova regra", expanded=False):
        with st.form("new_rule_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            keyword    = c1.text_input("Palavra-chave", placeholder="Ex: UBER")
            match_type = c2.selectbox("Tipo", list(MATCH_LABELS.keys()),
                                      format_func=lambda k: MATCH_LABELS[k])
            priority   = c3.number_input("Prioridade", 0, 100, value=5)

            c4, c5 = st.columns(2)
            cat_sel = c4.selectbox("Categoria existente", ["—"] + cats,
                                   help="Escolha uma existente OU digite uma nova abaixo")
            new_cat = c4.text_input("Ou nova categoria", placeholder="deixe vazio p/ usar a de cima")
            sub_sel = c5.selectbox("Subcategoria existente", ["(nenhuma)"] + subs)
            new_sub = c5.text_input("Ou nova subcategoria")

            saved = st.form_submit_button("Salvar regra", type="primary")

        if saved:
            category    = new_cat.strip() if new_cat.strip() else (cat_sel if cat_sel != "—" else "")
            subcategory = new_sub.strip() if new_sub.strip() else (sub_sel if sub_sel != "(nenhuma)" else "")
            if not keyword.strip():
                st.error("Informe a palavra-chave.")
            elif not category:
                st.error("Escolha ou digite uma categoria.")
            else:
                add_rule(keyword.strip().upper(), match_type,
                         category, subcategory, int(priority))
                # Aplica automaticamente nos pendentes ao salvar nova regra
                n = bulk_recategorize(only_pending=True)
                st.success(f"Regra adicionada: '{keyword.upper()}' -> {category}. "
                           f"{n} lancamentos recategorizados automaticamente.")
                st.rerun()

    rules = get_all_rules()
    if not rules:
        st.info("Nenhuma regra cadastrada.")
        return

    f1, f2 = st.columns([2, 1])
    search_kw   = f1.text_input("Filtrar regras", placeholder="keyword ou categoria")
    show_inact  = f2.checkbox("Mostrar inativas")

    filtered = rules
    if search_kw:
        q = search_kw.upper()
        filtered = [r for r in rules
                    if q in r["keyword"].upper() or q in r["category"].upper()]
    if not show_inact:
        filtered = [r for r in filtered if r["active"]]

    st.markdown(f"**{len(filtered)} regras**")
    st.divider()

    col_spec = [0.5, 2.3, 1.3, 1.8, 1.4, 0.7, 0.8, 0.7]
    hdr = st.columns(col_spec)
    for col, lbl in zip(hdr, ["#", "Palavra-chave", "Tipo", "Categoria",
                               "Subcategoria", "Prio.", "Editar", "Del."]):
        col.markdown(f"**{lbl}**")
    st.divider()

    editing_rule = st.session_state.get("editing_rule")
    for rule in filtered:
        rid  = rule["id"]
        icon = CATEGORY_ICONS.get(rule["category"], "")
        cols = st.columns(col_spec)
        cols[0].write(str(rid))
        cols[1].write(f"`{rule['keyword']}`")
        cols[2].write(MATCH_LABELS.get(rule["match_type"], rule["match_type"]))
        cols[3].write(f"{icon} {rule['category']}")
        cols[4].write(rule.get("subcategory") or "-")
        cols[5].write(str(rule["priority"]))
        if cols[6].button("", icon=":material/edit:", key=f"editbtn_{rid}", help="Editar"):
            st.session_state["editing_rule"] = (None if editing_rule == rid else rid)
            st.rerun()
        if cols[7].button("", icon=":material/delete:", key=f"del_{rid}", help="Remover"):
            delete_rule(rid)
            st.success("Regra removida.")
            st.rerun()
        if editing_rule == rid:
            _edit_rule_form(rule, cats, subs)

    st.divider()

    # Recategorizar lancamentos
    st.markdown("**Aplicar regras nos lancamentos**")
    st.caption("Util depois de cadastrar novas regras ou renomear categorias.")
    rc1, rc2, _ = st.columns([2, 2, 3])
    if rc1.button("Recategorizar pendentes", use_container_width=True, key="recat_pending"):
        n = bulk_recategorize(only_pending=True)
        st.success(f"{n} lancamentos pendentes recategorizados.")
        st.rerun()
    if rc2.button("Recategorizar todos", use_container_width=True, key="recat_all"):
        n = bulk_recategorize(only_pending=False)
        st.success(f"{n} lancamentos recategorizados.")
        st.rerun()

    st.divider()
    if st.button("Exportar regras CSV"):
        df  = pd.DataFrame(rules)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Baixar CSV", data=csv,
                           file_name="regras.csv", mime="text/csv")


def _edit_rule_form(rule: dict, cats: list, subs: list):
    """Formulario inline de edicao de uma regra (categoria/subcategoria por dropdown + nova)."""
    rid = rule["id"]
    with st.container(border=True):
        st.markdown(f"**Editando regra #{rid}** — `{rule['keyword']}`")
        with st.form(f"edit_rule_{rid}", clear_on_submit=False):
            e1, e2, e3 = st.columns(3)
            keyword = e1.text_input("Palavra-chave", value=rule["keyword"], key=f"ekw_{rid}")
            mt_keys = list(MATCH_LABELS.keys())
            mt_idx  = mt_keys.index(rule["match_type"]) if rule["match_type"] in mt_keys else 0
            match_type = e2.selectbox("Tipo", mt_keys, index=mt_idx,
                                      format_func=lambda k: MATCH_LABELS[k], key=f"emt_{rid}")
            priority = e3.number_input("Prioridade", 0, 100,
                                       value=int(rule["priority"]), key=f"epr_{rid}")

            e4, e5 = st.columns(2)
            cur_cat  = rule.get("category") or ""
            cat_opts = cats if cur_cat in cats else ([cur_cat] + cats if cur_cat else cats)
            cat_idx  = cat_opts.index(cur_cat) if cur_cat in cat_opts else 0
            cat_sel  = e4.selectbox("Categoria existente", cat_opts, index=cat_idx, key=f"ecat_{rid}")
            new_cat  = e4.text_input("Ou nova categoria", value="", key=f"encat_{rid}")

            cur_sub  = rule.get("subcategory") or ""
            sub_opts = ["(nenhuma)"] + subs
            sub_idx  = sub_opts.index(cur_sub) if cur_sub in sub_opts else 0
            sub_sel  = e5.selectbox("Subcategoria existente", sub_opts, index=sub_idx, key=f"esub_{rid}")
            new_sub  = e5.text_input("Ou nova subcategoria", value="", key=f"ensub_{rid}")

            active = st.checkbox("Regra ativa", value=bool(rule["active"]), key=f"eact_{rid}")

            sc, cc = st.columns(2)
            save   = sc.form_submit_button("Salvar alteracoes", type="primary")
            cancel = cc.form_submit_button("Cancelar")

        if save:
            category    = new_cat.strip() if new_cat.strip() else cat_sel
            subcategory = new_sub.strip() if new_sub.strip() else ("" if sub_sel == "(nenhuma)" else sub_sel)
            if not keyword.strip():
                st.error("Informe a palavra-chave.")
            elif not category:
                st.error("Escolha ou digite uma categoria.")
            else:
                update_rule(rid, keyword=keyword.strip().upper(), match_type=match_type,
                            category=category, subcategory=subcategory,
                            priority=int(priority), active=int(active))
                st.session_state["editing_rule"] = None
                st.success("Regra atualizada.")
                st.rerun()
        if cancel:
            st.session_state["editing_rule"] = None
            st.rerun()
