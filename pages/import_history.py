"""
Página: Histórico de Importações
Exibe todos os PDFs importados e seus logs de processamento.
Permite excluir registro de importação para reimportar o mesmo arquivo.
"""
import streamlit as st

from services.import_service import get_imports, get_import_logs
from database.connection import db_session
from pages.components import page_header, amount_fmt
from utils.helpers import month_label


STATUS_ICONS = {
    "done": "✅",
    "processing": "⏳",
    "pending": "🕐",
    "error": "❌",
    "duplicate": "♻️",
}
LOG_ICONS = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}


def delete_import(import_id: int, delete_transactions: bool = True):
    """Remove o registro de importação (e opcionalmente seus lançamentos) do banco."""
    with db_session() as conn:
        if delete_transactions:
            conn.execute("DELETE FROM transactions WHERE import_id = ?", (import_id,))
        conn.execute("DELETE FROM processing_logs WHERE import_id = ?", (import_id,))
        conn.execute("DELETE FROM imports WHERE id = ?", (import_id,))


def render():
    page_header("Histórico de Importações", "Veja todos os PDFs importados e seus detalhes.")

    imports = get_imports()
    if not imports:
        st.info("Nenhuma importação realizada ainda. Acesse 'Importar PDF' para começar.")
        return

    st.markdown(f"**{len(imports)} importações registradas**")

    with st.expander("ℹ️ Como reimportar um arquivo já importado?"):
        st.markdown("""
        Se precisar reimportar um arquivo (por exemplo, após instalar um parser novo),
        clique em **🗑️ Excluir** na linha correspondente.

        Isso remove o registro do arquivo do banco, liberando-o para ser importado novamente.
        Você pode escolher se quer **manter ou apagar** os lançamentos daquela importação.
        """)

    st.divider()

    for imp in imports:
        _render_import_row(imp)


def _render_import_row(imp: dict):
    imp_id = imp["id"]
    status_icon = STATUS_ICONS.get(imp.get("status", ""), "❓")
    ocr_badge = "🔍 OCR" if imp.get("ocr_used") else ""
    date_str = imp.get("import_date", "")[:10]

    card_name  = imp.get('account_label', '') or imp.get('source_name', '') or "—"
    ref_month  = imp.get('ref_month')
    ref_lbl    = month_label(ref_month) if ref_month else "—"
    total_amt  = imp.get('total_amount', 0) or 0
    n_lanc     = imp.get('tx_count') or imp.get('total_found', 0)

    def _stack(label, value, color="var(--ft-text)"):
        return (f"<div style='color:var(--ft-text2);font-size:0.7rem;text-transform:uppercase;"
                f"letter-spacing:.04em'>{label}</div>"
                f"<div style='font-size:0.95rem;font-weight:600;color:{color}'>{value}</div>")

    with st.container():
        c1, c2, c3, c4, c5, c6 = st.columns([0.4, 3, 1.4, 1.5, 1.2, 1.9],
                                            vertical_alignment="center")
        c1.markdown(f"**{status_icon}**")
        c2.markdown(
            f"**{imp.get('filename', '')}**  \n"
            f"<span style='color:#888;font-size:0.8rem'>"
            f"💳 {card_name}  ·  {date_str} {ocr_badge}</span>",
            unsafe_allow_html=True,
        )
        c3.markdown(_stack("Mês ref.", ref_lbl), unsafe_allow_html=True)
        c4.markdown(_stack("Valor total", amount_fmt(total_amt)), unsafe_allow_html=True)
        c5.markdown(_stack("Lançamentos", n_lanc), unsafe_allow_html=True)

        with c6:
            b1, b2 = st.columns(2)
            if b1.button("📋 Logs", key=f"logs_{imp_id}", use_container_width=True):
                st.session_state[f"show_logs_{imp_id}"] = not st.session_state.get(
                    f"show_logs_{imp_id}", False
                )
            if b2.button("🗑️ Excluir", key=f"del_imp_{imp_id}",
                         use_container_width=True, type="primary"):
                st.session_state[f"confirm_del_imp_{imp_id}"] = True

        # ── Confirmação de exclusão ───────────────────────────────────────
        if st.session_state.get(f"confirm_del_imp_{imp_id}"):
            st.warning(
                f"**Excluir importação '{imp.get('filename', '')}'?**  \n"
                f"Isso liberará o arquivo para ser reimportado."
            )
            keep = st.checkbox(
                "Manter os lançamentos desta importação no banco",
                value=False,
                key=f"keep_tx_{imp_id}",
            )
            ca, cb, _ = st.columns([1.5, 1, 4])
            if ca.button("✅ Confirmar", key=f"ok_del_imp_{imp_id}", type="primary"):
                delete_import(imp_id, delete_transactions=not keep)
                st.session_state[f"confirm_del_imp_{imp_id}"] = False
                msg = "Importação excluída. Lançamentos mantidos." if keep else \
                      "Importação e lançamentos excluídos."
                st.success(f"{msg} Você já pode reimportar o arquivo.")
                st.rerun()
            if cb.button("Cancelar", key=f"no_del_imp_{imp_id}"):
                st.session_state[f"confirm_del_imp_{imp_id}"] = False
                st.rerun()

        if imp.get("error_msg"):
            st.error(f"Erro: {imp['error_msg']}")

        # ── Logs expandidos ───────────────────────────────────────────────
        if st.session_state.get(f"show_logs_{imp_id}"):
            logs = get_import_logs(imp_id)
            if logs:
                with st.expander(f"📋 Logs da importação #{imp_id}", expanded=True):
                    for log in logs:
                        icon = LOG_ICONS.get(log.get("level", "info"), "ℹ️")
                        ts = log.get("created_at", "")[:19]
                        st.markdown(
                            f"{icon} `{ts}` **[{log['step']}]** {log['message']}"
                        )
            else:
                st.info("Sem logs para esta importação.")

        st.divider()
