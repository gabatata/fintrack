# -*- coding: utf-8 -*-
"""
Sincronizacao do banco SQLite com armazenamento na nuvem (Supabase Storage).

Quando as variaveis de ambiente estao configuradas (no Streamlit Cloud isso vem
de st.secrets -> os.environ, feito no app.py), o banco e:
  - BAIXADO da nuvem quando o app liga          -> download_db()
  - ENVIADO para a nuvem depois de cada escrita -> upload_db()

Sem essas variaveis (uso LOCAL), is_enabled() e False e nada acontece: o app
usa o arquivo data/fintrack.db local exatamente como antes.

Modelo simples (1 usuario, banco de ~160 KB): sincroniza o arquivo inteiro.
"""
from __future__ import annotations
import os
from pathlib import Path

from utils.logger import get_logger

log = get_logger(__name__)


def _cfg():
    """Le a configuracao das variaveis de ambiente. Retorna None se nao houver."""
    url = (os.environ.get("FINTRACK_SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("FINTRACK_SUPABASE_KEY") or ""
    bucket = os.environ.get("FINTRACK_SUPABASE_BUCKET") or "fintrack"
    obj = os.environ.get("FINTRACK_DB_OBJECT") or "fintrack.db"
    if url and key:
        return url, key, bucket, obj
    return None


def is_enabled() -> bool:
    """True se a sincronizacao com a nuvem estiver configurada."""
    return _cfg() is not None


def _object_url(url: str, bucket: str, obj: str) -> str:
    return f"{url}/storage/v1/object/{bucket}/{obj}"


# Trava de seguranca: so permitimos SUBIR o banco depois de confirmar o estado
# da nuvem na descida (download OK, ou 404 = nuvem legitimamente vazia). Se a
# descida FALHAR (rede/credencial), uploads ficam bloqueados para nunca
# sobrescrever a nuvem com um banco que nao representa o estado real.
_download_ok = False


def _local_tx_count(db_path: Path) -> int:
    """Conta transacoes no banco local (para nao subir banco vazio)."""
    try:
        import sqlite3
        c = sqlite3.connect(str(db_path))
        try:
            return c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        finally:
            c.close()
    except Exception:
        return -1  # em duvida, nao bloqueia por contagem


def download_db(db_path: Path) -> bool:
    """Baixa o banco da nuvem para db_path. Retorna True se baixou."""
    global _download_ok
    cfg = _cfg()
    if not cfg:
        return False
    url, key, bucket, obj = cfg
    try:
        import requests
        r = requests.get(
            _object_url(url, bucket, obj),
            headers={"Authorization": f"Bearer {key}", "apikey": key},
            timeout=30,
        )
        if r.status_code == 200 and r.content:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.write_bytes(r.content)
            _download_ok = True
            log.info(f"Banco baixado da nuvem ({len(r.content)} bytes).")
            return True
        if r.status_code == 404:
            _download_ok = True  # nuvem vazia de verdade: seguro subir depois
            log.info("Sem banco na nuvem ainda; sera criado no primeiro uso.")
        else:
            log.warning(f"Download do banco falhou: HTTP {r.status_code} {r.text[:150]}")
    except Exception as e:
        log.error(f"Erro ao baixar banco da nuvem: {e}")
    return False


def upload_db(db_path: Path) -> bool:
    """Envia (upsert) o banco local para a nuvem. Retorna True se enviou."""
    cfg = _cfg()
    if not cfg or not db_path.exists():
        return False

    # Protecao 1: nunca subir se nao confirmamos o estado da nuvem na descida.
    if not _download_ok:
        log.warning("Upload BLOQUEADO: download da nuvem nao confirmado nesta "
                    "sessao (evita sobrescrever dados da nuvem).")
        return False
    # Protecao 2: nunca subir um banco SEM transacoes por cima da nuvem.
    if _local_tx_count(db_path) == 0:
        log.warning("Upload BLOQUEADO: banco local sem transacoes "
                    "(evita zerar a nuvem).")
        return False

    url, key, bucket, obj = cfg
    try:
        import requests
        data = db_path.read_bytes()
        r = requests.post(
            _object_url(url, bucket, obj),
            headers={
                "Authorization": f"Bearer {key}",
                "apikey": key,
                "Content-Type": "application/octet-stream",
                "x-upsert": "true",  # cria ou substitui
                "Cache-Control": "no-cache",
            },
            data=data,
            timeout=60,
        )
        if r.status_code in (200, 201):
            return True
        log.warning(f"Upload do banco falhou: HTTP {r.status_code} {r.text[:150]}")
    except Exception as e:
        log.error(f"Erro ao enviar banco para a nuvem: {e}")
    return False
