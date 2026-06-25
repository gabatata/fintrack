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


def download_db(db_path: Path) -> bool:
    """Baixa o banco da nuvem para db_path. Retorna True se baixou."""
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
            log.info(f"Banco baixado da nuvem ({len(r.content)} bytes).")
            return True
        if r.status_code == 404:
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
