"""
Página: Cadastrar Despesa Manual
Formulário para lançamentos que não vêm de PDF.
"""
import streamlit as st
from datetime import date

from services.transaction_service import save_transactions, get_accounts
from services.categorization_service import get_categories
from pages.components import page_header, amount_fmt
from utils.helpers import CATEGORY_ICONS

CATEGORIES = list(CATEGORY_ICONS.keys()) + ["Outros"]
PAYMENT_FORMS = [
    "Cartão de Crédito", "Cartão de Débito", "Dinheiro",
    "PIX", "TED/DOC", "Boleto", "Outro",
]


def render():
    page_header("Despesa Manual", "Cadastre despesas que não constam em nenhum extrato.")

    # Busca contas existentes para sugerir
    existing_accounts = get_accounts()

    with st.form("manual_expense_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        tx_date = c1.date_input("Data", value=date.today())
        amount = c2.number_input("Valor (R$)", min_value=0.01, step=0.01, format="%.2f")

        description = st.text_input("Descrição *", placeholder="Ex: Almoço com cliente, Farmácia...")

        c3, c4 = st.columns(2)
        category = c3.selectbox("Categoria", CATEGORIES)

        # Subcategoria: livre digitação
        subcategory = c4.text_input("Subcategoria (opcional)", placeholder="Ex: Fast Food")

        c5, c6 = st.columns(2)
        payment_form = c5.selectbox("Forma de pagamento", PAYMENT_FORMS)

        # Cartão/conta: lista existentes + opção de digitar
        account_options = [""] + existing_accounts + ["+ Nova conta"]
        account_sel = c6.selectbox("Cartão / Conta", account_options,
                                   format_func=lambda x: "Selecionar..." if not x else x)
        if account_sel == "+ Nova conta":
            account_label = st.text_input("Nome da nova conta")
        else:
            account_label = account_sel

        c7, c8 = st.columns(2)
        is_recurring = c7.checkbox("É recorrente (assinatura)?")
        notes = c8.text_input("Observações", placeholder="Anotação livre...")

        submitted = st.form_submit_button("Salvar Despesa", icon=":material/save:", type="primary", use_container_width=True)

    if submitted:
        if not description.strip():
            st.error("A descrição é obrigatória.")
            return
        if amount <= 0:
            st.error("Informe um valor maior que zero.")
            return

        tx = {
            "tx_date": tx_date.isoformat(),
            "description_raw": description.strip(),
            "description_norm": description.strip().upper(),
            "merchant": description.strip().upper()[:40],
            "amount": amount,
            "tx_type": "debit",
            "account_label": account_label.strip() if account_label else payment_form,
            "category": category,
            "subcategory": subcategory,
            "is_recurring": int(is_recurring),
            "review_status": "reviewed",  # Manual já nasce revisado
            "source": "manual",
            "notes": notes,
        }

        save_transactions([tx])
        st.success(
            f"✅ Despesa salva: **{description}** — {amount_fmt(amount)} "
            f"em {tx_date.strftime('%d/%m/%Y')}"
        )

    # ── Atalhos rápidos ───────────────────────────────────────────────────
    st.divider()
    st.markdown("**💡 Lançamentos rápidos**")
    st.caption("Cadastre gastos do dia a dia sem preencher todo o formulário.")

    q1, q2, q3 = st.columns(3)
    with q1:
        if st.button("☕ Café / Lanche", use_container_width=True):
            _quick_save("Café / Lanche", "Alimentação", "Lanche")
    with q2:
        if st.button("🚌 Transporte público", use_container_width=True):
            _quick_save("Transporte público", "Transporte", "Público")
    with q3:
        if st.button("🅿️ Estacionamento", use_container_width=True):
            _quick_save("Estacionamento", "Transporte", "Estacionamento")


def _quick_save(description: str, category: str, subcategory: str):
    """Salva lançamento rápido com valor a completar."""
    st.session_state["quick_desc"] = description
    st.session_state["quick_cat"] = category
    st.session_state["quick_subcat"] = subcategory
    st.info(f"Preencha o valor para '{description}' no formulário acima.")
