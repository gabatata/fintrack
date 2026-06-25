"""
Gerenciamento de conexão com o banco de dados SQLite.

Em uso LOCAL, opera sobre data/fintrack.db normalmente.
No Streamlit Cloud (disco temporário), o banco é sincronizado com a nuvem:
baixado quando o app liga e enviado depois de cada escrita. Veja cloud_sync.py.
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

from database import cloud_sync

# Caminho do banco de dados
DB_PATH = Path(__file__).parent.parent / "data" / "fintrack.db"

_downloaded = False


def _ensure_downloaded() -> None:
    """Baixa o banco da nuvem uma única vez por processo (se configurado)."""
    global _downloaded
    if _downloaded:
        return
    _downloaded = True  # marca antes para não repetir mesmo se falhar
    if cloud_sync.is_enabled():
        cloud_sync.download_db(DB_PATH)


def get_connection() -> sqlite3.Connection:
    """Retorna conexão com o banco, criando o arquivo se necessário."""
    _ensure_downloaded()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # Retorna dicts em vez de tuplas
    # Na nuvem usamos um único arquivo (DELETE) para o upload sair consistente;
    # localmente, WAL para melhor performance.
    conn.execute("PRAGMA journal_mode=" + ("DELETE" if cloud_sync.is_enabled() else "WAL"))
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_session():
    """Context manager para transações seguras (e sync com a nuvem após escrita)."""
    conn = get_connection()
    wrote = False
    try:
        yield conn
        wrote = conn.in_transaction  # houve INSERT/UPDATE/DELETE pendente?
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    # Envia para a nuvem fora do bloco (após fechar a conexão) só se houve escrita.
    if wrote and cloud_sync.is_enabled():
        cloud_sync.upload_db(DB_PATH)
