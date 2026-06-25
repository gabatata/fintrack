"""
Página: Importar PDF
Pipeline visual de importação com preview e confirmação.
"""
import streamlit as st
from pathlib import Path

from services.import_service import import_pdf
from pages.components import page_header, amount_fmt, format_date_br
from utils.helpers import save_uploaded_file
from ocr.ocr_engine import is_ocr_available

UPLOADS_DIR = Path(__file__).parent.parent / "data" / "uploads"


def render():
    page_header("Importar Extrato PDF", "Faça upload do PDF do seu cartão ou conta.")

    # Status do OCR - so mostra aviso se Tesseract nao estiver instalado
    if not is_ocr_available():
        with st.expander("OCR opcional nao instalado (clique para detalhes)", expanded=False):
            st.info(
                "O OCR so e necessario para faturas **escaneadas (imagem)**.  \n"
                "PDFs com texto (a maioria das faturas de banco/cartao) sao lidos normalmente sem ele.  \n\n"
                "Para habilitar OCR no **Windows**, instale o Tesseract:  \n"
                "`winget install UB-Mannheim.TesseractOCR`  \n"
                "Depois reinicie o app. (Linux/WSL: `sudo apt install tesseract-ocr tesseract-ocr-por`)"
            )

    st.divider()

    # ── Formulário de upload ──────────────────────────────────────────────
    with st.form("upload_form"):
        uploaded = st.file_uploader("Selecione o PDF do extrato", type=["pdf"])
        col1, col2 = st.columns(2)
        account_label = col1.text_input(
            "Nome do cartão/conta",
            placeholder="Ex: Nubank, Itaú Platinum...",
        )
        source_name = col2.text_input(
            "Instituição (opcional)",
            placeholder="Ex: Nubank, Itaú...",
        )
        force_ocr = st.checkbox("Forçar OCR mesmo com texto disponível")
        submitted = st.form_submit_button("Importar", icon=":material/upload_file:", type="primary", use_container_width=True)

    if not submitted or not uploaded:
        _show_tips()
        return

    if not account_label.strip():
        st.error("Informe o nome do cartão/conta.")
        return

    # ── Salva arquivo ─────────────────────────────────────────────────────
    with st.spinner("Salvando arquivo..."):
        pdf_path = save_uploaded_file(uploaded, UPLOADS_DIR)

    # ── Pipeline de importação com barra de progresso ─────────────────────
    progress_bar = st.progress(0, text="Iniciando...")
    status_box = st.empty()
    result = {}

    pipeline = import_pdf(
        pdf_path=pdf_path,
        account_label=account_label.strip(),
        source_name=source_name.strip(),
        force_ocr=force_ocr,
    )

    try:
        while True:
            step_info = next(pipeline)
            progress_bar.progress(step_info["pct"] / 100, text=step_info["msg"])
            status_box.info(step_info["msg"])
    except StopIteration as e:
        result = e.value

    # ── Resultado ─────────────────────────────────────────────────────────
    progress_bar.empty()
    status_box.empty()

    if result.get("status") == "duplicate":
        st.warning("⚠️ Este arquivo já foi importado anteriormente. Importação ignorada.")
        return

    if result.get("status") == "error":
        st.error(f"❌ Erro na importação: {result.get('error')}")
        return

    # ── Resumo da importação ──────────────────────────────────────────────
    st.success(f"✅ Importação concluída!")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Encontrados", result.get("total_found", 0))
    c2.metric("Salvos", result.get("total_saved", 0))
    c3.metric("Duplicatas ignoradas", result.get("duplicates", 0))
    c4.metric("Bloqueados", result.get("blocked", 0),
              help="Excluídos anteriormente ou bloqueados por nome (seção Excluídos)")

    if result.get("ocr_used"):
        st.info("🔍 OCR foi utilizado para ler este documento.")

    # ── Preview dos lançamentos importados ────────────────────────────────
    preview = result.get("preview", [])
    if preview:
        st.divider()
        st.markdown("**📋 Preview dos lançamentos importados**")
        st.caption("Revise os lançamentos. Você pode editá-los em 'Todos os Lançamentos'.")

        # Filtra duplicatas do preview
        non_dup = [t for t in preview if not t.get("duplicate_of")]
        if non_dup:
            import pandas as pd
            df = pd.DataFrame(non_dup)[
                ["tx_date", "description_raw", "description_norm",
                 "merchant", "amount", "category", "account_label"]
            ]
            df.columns = ["Data", "Descrição Original", "Descrição Norm.",
                          "Merchant", "Valor", "Categoria", "Conta"]
            df["Data"] = df["Data"].apply(format_date_br)
            df["Valor"] = df["Valor"].apply(amount_fmt)
            st.dataframe(df, use_container_width=True, hide_index=True)

        dups = [t for t in preview if t.get("duplicate_of")]
        if dups:
            with st.expander(f"⚠️ {len(dups)} lançamentos ignorados como duplicata"):
                for d in dups:
                    st.write(
                        f"- {format_date_br(d['tx_date'])} | "
                        f"{d['description_raw']} | {amount_fmt(d['amount'])}"
                    )


def _show_tips():
    with st.expander("💡 Dicas para importação"):
        st.markdown("""
        - **Formatos suportados:** PDF de extratos de cartão de crédito ou conta corrente
        - **OCR automático:** PDFs escaneados são detectados e processados automaticamente
        - **Revisão:** Após importar, revise os lançamentos em **Todos os Lançamentos**
        - **Duplicatas:** O sistema detecta e ignora arquivos já importados
        - **Nome do cartão:** Use um nome consistente (ex: "Nubank") para facilitar os filtros
        """)
