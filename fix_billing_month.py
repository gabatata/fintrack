# -*- coding: utf-8 -*-
"""
Script de correcao do billing_month no banco local.
Execute uma vez: python fix_billing_month.py

Regra:
- Todos os lancamentos de um mesmo import recebem o billing_month
  igual ao mes do VENCIMENTO detectado no PDF.
- Vencimento 05/03/2026 -> billing_month = 2026-03
- Lancamentos manuais (sem import_id) mantem billing_month = mes da transacao.
"""
import sys
import re
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from database import init_database
from database.connection import db_session

init_database()

# Padroes para detectar vencimento no nome do arquivo ou nas importacoes
VENCIMENTO_PATTERNS = [
    r"[Vv]enc[ei]mento[:\s]+\d{2}/(\d{2})/(\d{4})",
    r"[Vv]ence\s+em\s+\d{2}/(\d{2})/(\d{4})",
    r"(\d{2})/(\d{4})",   # fallback: MM/YYYY em qualquer lugar
]


def detect_vencimento_from_pdf(filepath: str):
    """Tenta ler o vencimento diretamente do PDF."""
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            text = ""
            for page in pdf.pages[:3]:
                text += (page.extract_text() or "") + "\n"

        for pat in VENCIMENTO_PATTERNS[:2]:   # so os dois especificos
            m = re.search(pat, text)
            if m:
                venc_mo = int(m.group(1))
                venc_yr = int(m.group(2))
                return f"{venc_yr}-{venc_mo:02d}"
    except Exception as e:
        print(f"  Nao foi possivel ler PDF: {e}")
    return None


def fix():
    with db_session() as conn:
        # Busca todos os imports
        imports = conn.execute(
            "SELECT id, filename, filepath, import_date FROM imports ORDER BY id"
        ).fetchall()

        print(f"Encontrados {len(imports)} imports para verificar.\n")

        for imp in imports:
            imp_id   = imp["id"]
            filename = imp["filename"]
            filepath = imp["filepath"]
            imp_date = imp["import_date"]

            print(f"Import #{imp_id}: {filename}")

            # 1) Tenta detectar vencimento no PDF
            billing_month = None
            if filepath and Path(filepath).exists():
                billing_month = detect_vencimento_from_pdf(filepath)
                if billing_month:
                    print(f"  Vencimento detectado no PDF: {billing_month}")
            else:
                print(f"  Arquivo nao encontrado: {filepath}")

            # 2) Fallback: usa mes do import_date (quando o arquivo foi importado)
            if not billing_month:
                # Tenta extrair o mes do nome do arquivo
                m = re.search(r"(\d{4})[_-](\d{2})", filename)
                if m:
                    billing_month = f"{m.group(1)}-{m.group(2)}"
                    print(f"  Mes extraido do nome do arquivo: {billing_month}")
                else:
                    # Usa mes do import_date como fallback final
                    billing_month = imp_date[:7]
                    print(f"  Usando mes do import como fallback: {billing_month}")

            # 3) Conta quantos lancamentos serao atualizados
            count = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE import_id = ?",
                (imp_id,)
            ).fetchone()[0]

            # 4) Atualiza
            conn.execute(
                "UPDATE transactions SET billing_month = ? WHERE import_id = ?",
                (billing_month, imp_id)
            )
            print(f"  {count} lancamentos -> billing_month = {billing_month}\n")

        # 5) Lancamentos manuais: usa mes da tx_date
        manual_count = conn.execute(
            """
            UPDATE transactions
            SET billing_month = strftime('%Y-%m', tx_date)
            WHERE import_id IS NULL
            """
        ).rowcount
        if manual_count:
            print(f"Lancamentos manuais corrigidos: {manual_count}")

        # Resumo final
        rows = conn.execute(
            """
            SELECT billing_month, COUNT(*) as cnt, SUM(amount) as total
            FROM transactions
            WHERE tx_type = 'debit'
            GROUP BY billing_month
            ORDER BY billing_month
            """
        ).fetchall()
        print("\nDistribuicao final por billing_month:")
        for r in rows:
            print(f"  {r['billing_month']}: {r['cnt']} lancamentos, R$ {r['total']:,.2f}")

    print("\nCorrecao concluida. Reinicie o app.")


if __name__ == "__main__":
    fix()
