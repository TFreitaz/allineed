"""
Controle de schema do banco (Neon/Postgres) via migrations simples em SQL.

Como funciona:
- Cada mudança de schema vira um arquivo .sql numerado dentro de db/migrations/
  (ex: 0001_create_users_and_messages.sql, 0002_add_algo.sql, ...).
- O script mantém uma tabela `schema_migrations` no próprio banco, registrando
  quais arquivos já foram aplicados.
- Rodar o script de novo só aplica os arquivos NOVOS (que ainda não estão
  registrados) — por isso é seguro rodar várias vezes (idempotente).

Uso:
    python db/migrate.py            # aplica todas as migrations pendentes
    python db/migrate.py --status   # só mostra o que já foi aplicado / pendente

Para criar uma nova mudança de schema no futuro:
    1. Crie um novo arquivo em db/migrations/, ex: 0002_add_users_bio.sql
    2. Escreva o SQL (ALTER TABLE, CREATE TABLE, etc.)
    3. Rode `python db/migrate.py` de novo — só esse novo arquivo será aplicado.
"""

import os
import sys
from pathlib import Path

import psycopg2

from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    if not DATABASE_URL:
        print("Erro: defina a variável de ambiente DATABASE_URL (connection string do Neon).")
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL)


def ensure_migrations_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def get_applied_migrations(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def get_migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_migration(conn, filepath: Path) -> None:
    sql = filepath.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO schema_migrations (filename) VALUES (%s)",
            (filepath.name,),
        )
    conn.commit()
    print(f"  aplicada: {filepath.name}")


def run(show_status_only: bool = False) -> None:
    conn = get_connection()
    try:
        ensure_migrations_table(conn)
        applied = get_applied_migrations(conn)
        all_files = get_migration_files()
        pending = [f for f in all_files if f.name not in applied]

        if show_status_only:
            print("Aplicadas:")
            for f in all_files:
                if f.name in applied:
                    print(f"  [x] {f.name}")
            print("Pendentes:")
            for f in pending:
                print(f"  [ ] {f.name}")
            return

        if not pending:
            print("Nenhuma migration pendente. Schema já está atualizado.")
            return

        print(f"Aplicando {len(pending)} migration(s) pendente(s)...")
        for filepath in pending:
            apply_migration(conn, filepath)
        print("Concluído.")
    finally:
        conn.close()


if __name__ == "__main__":
    run(show_status_only="--status" in sys.argv)
