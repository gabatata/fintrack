"""
Schema do banco de dados SQLite.
Todas as tabelas são criadas aqui via migrations.
"""
from .connection import db_session

SCHEMA_VERSION = 1

TABLES = [
    # ------------------------------------------------------------------ #
    # IMPORTS — registro de cada arquivo PDF importado
    # ------------------------------------------------------------------ #
    """
    CREATE TABLE IF NOT EXISTS imports (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        filename        TEXT    NOT NULL,
        filepath        TEXT    NOT NULL,
        file_hash       TEXT    NOT NULL UNIQUE,   -- SHA-256 do arquivo
        source_name     TEXT,                       -- Ex: "Nubank", "Itaú"
        account_label   TEXT,                       -- Ex: "Cartão Nubank"
        import_date     TEXT    NOT NULL,           -- ISO 8601
        status          TEXT    NOT NULL DEFAULT 'pending',
            -- pending | processing | done | error
        ocr_used        INTEGER NOT NULL DEFAULT 0, -- 0 = não, 1 = sim
        total_found     INTEGER DEFAULT 0,
        error_msg       TEXT,
        notes           TEXT
    )
    """,

    # ------------------------------------------------------------------ #
    # TRANSACTIONS — cada lançamento extraído ou manual
    # ------------------------------------------------------------------ #
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        import_id           INTEGER REFERENCES imports(id) ON DELETE SET NULL,
        tx_date             TEXT    NOT NULL,           -- ISO 8601 YYYY-MM-DD
        description_raw     TEXT    NOT NULL,           -- texto original do extrato
        description_norm    TEXT,                       -- texto normalizado
        merchant            TEXT,                       -- nome do estabelecimento
        amount              REAL    NOT NULL,           -- sempre positivo
        tx_type             TEXT    NOT NULL DEFAULT 'debit',
            -- debit | credit | reversal | fee
        installment_current INTEGER,                    -- parcela atual
        installment_total   INTEGER,                    -- total de parcelas
        account_label       TEXT,                       -- cartão / conta
        category            TEXT,
        subcategory         TEXT,
        billing_month       TEXT,                       -- YYYY-MM (mês real da fatura)
        is_recurring        INTEGER NOT NULL DEFAULT 0, -- 0/1
        recurrence_id       INTEGER REFERENCES recurring_patterns(id) ON DELETE SET NULL,
        review_status       TEXT    NOT NULL DEFAULT 'pending',
            -- pending | reviewed | ignored
        source              TEXT    NOT NULL DEFAULT 'pdf',
            -- pdf | manual | import
        duplicate_of        INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
        notes               TEXT,
        created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ------------------------------------------------------------------ #
    # CATEGORY_RULES — regras de categorização por palavra-chave
    # ------------------------------------------------------------------ #
    """
    CREATE TABLE IF NOT EXISTS category_rules (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword     TEXT    NOT NULL,               -- palavra-chave (case-insensitive)
        match_type  TEXT    NOT NULL DEFAULT 'contains',
            -- contains | startswith | exact | regex
        category    TEXT    NOT NULL,
        subcategory TEXT,
        priority    INTEGER NOT NULL DEFAULT 0,     -- maior = maior prioridade
        active      INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ------------------------------------------------------------------ #
    # RECURRING_PATTERNS — padrões de gastos recorrentes detectados
    # ------------------------------------------------------------------ #
    """
    CREATE TABLE IF NOT EXISTS recurring_patterns (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        merchant        TEXT    NOT NULL,           -- nome normalizado
        category        TEXT,
        subcategory     TEXT,
        avg_amount      REAL,
        frequency       TEXT,                       -- monthly | weekly | yearly | irregular
        status          TEXT    NOT NULL DEFAULT 'suggested',
            -- suggested | confirmed | dismissed
        last_seen       TEXT,                       -- data da última ocorrência
        occurrence_count INTEGER NOT NULL DEFAULT 0,
        notes           TEXT,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ------------------------------------------------------------------ #
    # PROCESSING_LOGS — log de cada passo do pipeline de importação
    # ------------------------------------------------------------------ #
    """
    CREATE TABLE IF NOT EXISTS processing_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        import_id   INTEGER REFERENCES imports(id) ON DELETE CASCADE,
        level       TEXT    NOT NULL DEFAULT 'info',  -- info | warning | error
        step        TEXT    NOT NULL,                  -- pdf_read | ocr | parse | save
        message     TEXT    NOT NULL,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ------------------------------------------------------------------ #
    # APP_CONFIG — configurações gerais da aplicação
    # ------------------------------------------------------------------ #
    """
    CREATE TABLE IF NOT EXISTS app_config (
        key     TEXT PRIMARY KEY,
        value   TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ------------------------------------------------------------------ #
    # EXCLUDED_TRANSACTIONS — "lápides" de lançamentos excluídos
    # Impede que o MESMO lançamento (e as demais parcelas da mesma compra)
    # voltem em reimportações. A fingerprint ignora o número da parcela atual.
    # ------------------------------------------------------------------ #
    """
    CREATE TABLE IF NOT EXISTS excluded_transactions (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        fingerprint         TEXT    NOT NULL UNIQUE,   -- nome+data+nº parcelas+valor parcela+valor total
        merchant            TEXT,
        description_norm    TEXT,
        tx_date             TEXT,
        amount              REAL,                       -- valor da parcela
        total_amount        REAL,                       -- valor total da compra
        installment_total   INTEGER,
        account_label       TEXT,
        excluded_at         TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ------------------------------------------------------------------ #
    # BLOCKED_KEYWORDS — bloqueio permanente por nome
    # Lançamentos cujo texto bate com a palavra-chave nunca são importados.
    # ------------------------------------------------------------------ #
    """
    CREATE TABLE IF NOT EXISTS blocked_keywords (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword     TEXT    NOT NULL,
        match_type  TEXT    NOT NULL DEFAULT 'contains',  -- contains | exact
        note        TEXT,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tx_date         ON transactions(tx_date)",
    "CREATE INDEX IF NOT EXISTS idx_tx_import        ON transactions(import_id)",
    "CREATE INDEX IF NOT EXISTS idx_tx_category      ON transactions(category)",
    "CREATE INDEX IF NOT EXISTS idx_tx_merchant      ON transactions(merchant)",
    "CREATE INDEX IF NOT EXISTS idx_tx_review        ON transactions(review_status)",
    "CREATE INDEX IF NOT EXISTS idx_tx_recurring     ON transactions(is_recurring)",
    "CREATE INDEX IF NOT EXISTS idx_rules_keyword    ON category_rules(keyword)",
    "CREATE INDEX IF NOT EXISTS idx_log_import       ON processing_logs(import_id)",
]

DEFAULT_RULES = [
    ("UBER", "contains", "Transporte", "Aplicativo", 10),
    ("99", "startswith", "Transporte", "Aplicativo", 5),
    ("CABIFY", "contains", "Transporte", "Aplicativo", 10),
    ("IFOOD", "contains", "Alimentação", "Delivery", 10),
    ("RAPPI", "contains", "Alimentação", "Delivery", 10),
    ("MCDONALDS", "contains", "Alimentação", "Fast Food", 10),
    ("BURGER KING", "contains", "Alimentação", "Fast Food", 10),
    ("NETFLIX", "contains", "Assinaturas", "Streaming", 10),
    ("SPOTIFY", "contains", "Assinaturas", "Streaming", 10),
    ("AMAZON PRIME", "contains", "Assinaturas", "Streaming", 10),
    ("DISNEY", "contains", "Assinaturas", "Streaming", 10),
    ("HBO", "contains", "Assinaturas", "Streaming", 10),
    ("APPLE", "contains", "Assinaturas", "Tecnologia", 8),
    ("GOOGLE", "contains", "Assinaturas", "Tecnologia", 8),
    ("AMAZON", "contains", "Compras", "E-commerce", 5),
    ("MERCADO LIVRE", "contains", "Compras", "E-commerce", 10),
    ("SHOPEE", "contains", "Compras", "E-commerce", 10),
    ("FARMACIA", "contains", "Saúde", "Farmácia", 10),
    ("DROGARIA", "contains", "Saúde", "Farmácia", 10),
    ("DROGA", "contains", "Saúde", "Farmácia", 8),
    ("ACADEMIA", "contains", "Saúde", "Academia", 10),
    ("SMART FIT", "contains", "Saúde", "Academia", 10),
    ("SUPERMERCADO", "contains", "Alimentação", "Supermercado", 10),
    ("CARREFOUR", "contains", "Alimentação", "Supermercado", 10),
    ("EXTRA", "contains", "Alimentação", "Supermercado", 8),
    ("PÃO DE AÇÚCAR", "contains", "Alimentação", "Supermercado", 10),
    ("ATACADÃO", "contains", "Alimentação", "Supermercado", 10),
    ("POSTO", "contains", "Transporte", "Combustível", 10),
    ("SHELL", "contains", "Transporte", "Combustível", 10),
    ("PETROBRAS", "contains", "Transporte", "Combustível", 10),
    ("IPVA", "contains", "Transporte", "IPVA/Taxas", 10),
    ("PEDAGIO", "contains", "Transporte", "Pedágio", 10),
    ("LIGHT", "contains", "Moradia", "Energia", 10),
    ("CPFL", "contains", "Moradia", "Energia", 10),
    ("SABESP", "contains", "Moradia", "Água", 10),
    ("CLARO", "contains", "Comunicação", "Telefone/Internet", 10),
    ("VIVO", "contains", "Comunicação", "Telefone/Internet", 10),
    ("TIM", "contains", "Comunicação", "Telefone/Internet", 10),
    ("OI", "startswith", "Comunicação", "Telefone/Internet", 8),
    ("NET ", "startswith", "Comunicação", "Telefone/Internet", 8),
    ("ALUGUEL", "contains", "Moradia", "Aluguel", 10),
    ("CONDOMINIO", "contains", "Moradia", "Condomínio", 10),
    ("CINEMA", "contains", "Lazer", "Cinema", 10),
    ("INGRESSO", "contains", "Lazer", "Eventos", 10),
    ("LIVRARIA", "contains", "Educação", "Livros", 10),
    ("UDEMY", "contains", "Educação", "Cursos Online", 10),
    ("COURSERA", "contains", "Educação", "Cursos Online", 10),
    ("ANUIDADE", "contains", "Banco/Taxas", "Anuidade", 10),
    ("JUROS", "contains", "Banco/Taxas", "Juros", 10),
    ("IOF", "contains", "Banco/Taxas", "IOF", 10),
]


def init_database():
    """Cria todas as tabelas e índices, e insere regras padrão."""
    with db_session() as conn:
        for sql in TABLES:
            conn.execute(sql)
        for sql in INDEXES:
            conn.execute(sql)

        # Inserir regras padrão apenas se a tabela estiver vazia
        count = conn.execute("SELECT COUNT(*) FROM category_rules").fetchone()[0]
        if count == 0:
            conn.executemany(
                """
                INSERT INTO category_rules (keyword, match_type, category, subcategory, priority)
                VALUES (?, ?, ?, ?, ?)
                """,
                DEFAULT_RULES,
            )

        # Config padrão
        conn.execute(
            "INSERT OR IGNORE INTO app_config (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.execute(
            "INSERT OR IGNORE INTO app_config (key, value) VALUES ('default_account', 'Cartão Principal')",
        )

        # Migração: nature em category_rules (v1.3)
        _cr_cols = [c["name"] for c in conn.execute("PRAGMA table_info(category_rules)").fetchall()]
        if "nature" not in _cr_cols:
            conn.execute("ALTER TABLE category_rules ADD COLUMN nature TEXT DEFAULT NULL")
            # Aplica natureza padrao por categoria
            _defaults = {
                "Alimentação":   "necessario",
                "Saúde":         "necessario",
                "Transporte":    "necessario",
                "Moradia":       "necessario",
                "Comunicação":   "necessario",
                "Banco/Taxas":   "necessario",
                "Educação":      "necessario",
                "Assinaturas":   "cortavel",
                "Compras":       "cortavel",
                "Lazer":         "cortavel",
                "Outros":        "cortavel",
                "Investimentos": "necessario",
            }
            for cat, nat in _defaults.items():
                conn.execute(
                    "UPDATE category_rules SET nature=? WHERE category=? AND nature IS NULL",
                    (nat, cat)
                )

        # Migração: campos de terceiros (v1.2)
        _tx_cols = [c["name"] for c in conn.execute("PRAGMA table_info(transactions)").fetchall()]
        for _col, _typ in [
            ("third_party_name", "TEXT"),
            ("third_party_type", "TEXT"),
            ("split_with",       "TEXT"),
            ("split_amount",     "REAL"),
            ("split_paid",       "INTEGER DEFAULT 0"),
        ]:
            if _col not in _tx_cols:
                try:
                    conn.execute(f"ALTER TABLE transactions ADD COLUMN {_col} {_typ}")
                except Exception:
                    pass

        # Migração: billing_month (adicionado v1.1)
        cols = [c["name"] for c in conn.execute("PRAGMA table_info(transactions)").fetchall()]
        if "billing_month" not in cols:
            conn.execute("ALTER TABLE transactions ADD COLUMN billing_month TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_billing ON transactions(billing_month)")
            # Popula existentes
            conn.execute("""
                UPDATE transactions
                SET billing_month = (
                    SELECT strftime('%Y-%m', i.import_date)
                    FROM imports i WHERE i.id = transactions.import_id
                )
                WHERE installment_current IS NOT NULL AND import_id IS NOT NULL
            """)
            conn.execute("""
                UPDATE transactions
                SET billing_month = strftime('%Y-%m', tx_date)
                WHERE billing_month IS NULL
            """)
