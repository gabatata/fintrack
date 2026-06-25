"""
Gerador de dados mock para testes.
Cria lançamentos realistas para demonstrar a aplicação.
Execute: python seed_data.py
"""
import sys, random
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from database import init_database, db_session
from services.transaction_service import save_transactions
from services.recurrence_service import detect_recurring

MERCHANTS = [
    # (merchant, categoria, subcategoria, valor_base, recorrente)
    ("NETFLIX",        "Assinaturas",  "Streaming",       55.90,  True),
    ("SPOTIFY",        "Assinaturas",  "Streaming",       21.90,  True),
    ("AMAZON PRIME",   "Assinaturas",  "Streaming",       19.90,  True),
    ("DISNEY PLUS",    "Assinaturas",  "Streaming",       43.90,  True),
    ("APPLE",          "Assinaturas",  "Tecnologia",      37.90,  True),
    ("GOOGLE PLAY",    "Assinaturas",  "Tecnologia",      19.90,  True),
    ("SMART FIT",      "Saúde",        "Academia",        99.90,  True),
    ("CLARO",          "Comunicação",  "Internet",       129.90,  True),
    ("UBER",           "Transporte",   "Aplicativo",      25.50,  False),
    ("UBER",           "Transporte",   "Aplicativo",      18.90,  False),
    ("IFOOD",          "Alimentação",  "Delivery",        52.00,  False),
    ("IFOOD",          "Alimentação",  "Delivery",        39.80,  False),
    ("RAPPI",          "Alimentação",  "Delivery",        67.50,  False),
    ("CARREFOUR",      "Alimentação",  "Supermercado",   245.00,  False),
    ("PAO DE ACUCAR",  "Alimentação",  "Supermercado",   187.40,  False),
    ("ATACADAO",       "Alimentação",  "Supermercado",   312.00,  False),
    ("MCDONALDS",      "Alimentação",  "Fast Food",       45.90,  False),
    ("BURGER KING",    "Alimentação",  "Fast Food",       38.00,  False),
    ("DROGARIA SP",    "Saúde",        "Farmácia",        89.60,  False),
    ("FARMACIA",       "Saúde",        "Farmácia",        45.00,  False),
    ("POSTO SHELL",    "Transporte",   "Combustível",    280.00,  False),
    ("MERCADO LIVRE",  "Compras",      "E-commerce",     153.00,  False),
    ("SHOPEE",         "Compras",      "E-commerce",      87.50,  False),
    ("AMAZON",         "Compras",      "E-commerce",     210.00,  False),
    ("LIVRARIA CULT",  "Educação",     "Livros",          62.00,  False),
    ("UDEMY",          "Educação",     "Cursos",          27.90,  False),
    ("CINEMA",         "Lazer",        "Cinema",          38.00,  False),
    ("CONDOMINIO",     "Moradia",      "Condomínio",     650.00,  True),
]

ACCOUNTS = ["Nubank", "Itaú Platinum", "Bradesco Gold"]


def generate_mock_data(months: int = 4):
    """Gera lançamentos para os últimos N meses."""
    init_database()

    transactions = []
    today = date.today()
    total = 0

    for month_offset in range(months):
        ref_date = date(today.year, today.month, 1) - timedelta(days=30 * month_offset)

        for merchant, category, subcategory, base_amount, is_recurring in MERCHANTS:
            # Pula alguns não-recorrentes aleatoriamente para ser realista
            if not is_recurring and random.random() < 0.35:
                continue

            # Variação leve no valor
            amount = round(base_amount * random.uniform(0.92, 1.08), 2)

            # Data: recorrentes no mesmo dia todo mês, outros aleatórios
            if is_recurring:
                day = random.randint(1, 10)
            else:
                day = random.randint(1, 28)

            try:
                tx_date = date(ref_date.year, ref_date.month, day)
            except ValueError:
                tx_date = date(ref_date.year, ref_date.month, 28)

            # Não gera datas futuras
            if tx_date > today:
                continue

            account = random.choice(ACCOUNTS)

            transactions.append({
                "tx_date": tx_date.isoformat(),
                "description_raw": f"{merchant} {'12345' if not is_recurring else ''}".strip(),
                "description_norm": merchant,
                "merchant": merchant,
                "amount": amount,
                "tx_type": "debit",
                "account_label": account,
                "category": category,
                "subcategory": subcategory,
                "is_recurring": int(is_recurring),
                "review_status": "reviewed",
                "source": "manual",
                "notes": "Dado de demonstração",
            })
            total += 1

    # Adiciona alguns pagamentos manuais avulsos
    extras = [
        ("Almoço República", "Alimentação", "Restaurante", 42.0),
        ("Uber Eats entrega", "Alimentação", "Delivery", 55.0),
        ("Estacionamento shopping", "Transporte", "Estacionamento", 12.0),
        ("Livro técnico", "Educação", "Livros", 89.0),
        ("Happy hour", "Lazer", "Bar", 78.0),
    ]
    for desc, cat, subcat, amount in extras:
        day = random.randint(1, 28)
        tx_date = date(today.year, today.month, day)
        if tx_date <= today:
            transactions.append({
                "tx_date": tx_date.isoformat(),
                "description_raw": desc,
                "description_norm": desc.upper(),
                "merchant": desc.upper()[:20],
                "amount": amount,
                "tx_type": "debit",
                "account_label": "Nubank",
                "category": cat,
                "subcategory": subcat,
                "is_recurring": 0,
                "review_status": "reviewed",
                "source": "manual",
                "notes": "Dado de demonstração",
            })
            total += 1

    save_transactions(transactions)
    detect_recurring()
    print(f"✅ {total} lançamentos de demonstração criados para {months} meses.")


if __name__ == "__main__":
    generate_mock_data(months=4)
