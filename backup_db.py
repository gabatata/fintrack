# -*- coding: utf-8 -*-
"""
Rotina de backup do banco FinTrack.

Por que existe
--------------
O backup "copiar o arquivo .db na mao" e arriscado porque o banco roda em
modo WAL (journal_mode=WAL): copiar apenas fintrack.db pode perder os ultimos
lancamentos que ainda estao no arquivo -wal. Este script usa a API oficial
sqlite3 .backup(), que produz uma copia consistente mesmo com o app aberto.

Uso
---
    python backup_db.py                # cria 1 backup em data/backups/
    python backup_db.py --keep 60      # mantem os 60 backups mais recentes
    python backup_db.py --out D:/bkp   # grava em outro diretorio (ex: pendrive)

Agendamento (opcional, faca uma vez)
------------------------------------
- Windows (Agendador de Tarefas): crie uma tarefa diaria que rode
      <caminho-do-python> backup_db.py
  no diretorio do projeto.
- Linux/servidor (cron): adicione ao crontab
      0 3 * * *  cd /home/ubuntu/fintrack && .venv/bin/python backup_db.py
"""
from __future__ import annotations
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "fintrack.db"
DEFAULT_OUT = ROOT / "data" / "backups"


def make_backup(db_path: Path, out_dir: Path) -> Path:
    """Cria uma copia consistente do banco. Retorna o caminho gerado."""
    if not db_path.exists():
        raise FileNotFoundError(f"Banco nao encontrado: {db_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    # timestamp no nome para ordenar e nunca sobrescrever
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = out_dir / f"fintrack_{stamp}.db"

    # Conexao de origem (read) e destino; .backup copia paginas de forma
    # atomica, respeitando o WAL — seguro mesmo com o app rodando.
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dest


def rotate(out_dir: Path, keep: int) -> list[Path]:
    """Mantem apenas os 'keep' backups mais recentes. Retorna os removidos."""
    if keep <= 0:
        return []
    backups = sorted(out_dir.glob("fintrack_*.db"), key=lambda p: p.name)
    removed = []
    while len(backups) > keep:
        old = backups.pop(0)
        try:
            old.unlink()
            removed.append(old)
        except OSError as e:
            print(f"  AVISO: nao consegui remover {old.name}: {e}")
    return removed


def main():
    ap = argparse.ArgumentParser(description="Backup do banco FinTrack (seguro com WAL).")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"Diretorio de saida (padrao: {DEFAULT_OUT})")
    ap.add_argument("--keep", type=int, default=30,
                    help="Quantos backups manter (padrao: 30; 0 = nunca apagar)")
    args = ap.parse_args()

    try:
        dest = make_backup(DB_PATH, args.out)
    except Exception as e:
        print(f"ERRO no backup: {e}")
        sys.exit(1)

    size_kb = dest.stat().st_size / 1024
    print(f"Backup criado: {dest}  ({size_kb:,.0f} KB)")

    removed = rotate(args.out, args.keep)
    if removed:
        print(f"Rotacao: {len(removed)} backup(s) antigo(s) removido(s).")


if __name__ == "__main__":
    main()
