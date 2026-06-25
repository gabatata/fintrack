"""
Serviço de normalização de descrições de lançamentos.
Transforma "NETFLIX.COM 12345 SP" em "NETFLIX".
"""
from __future__ import annotations
import re
from utils.helpers import normalize_text
from utils.logger import get_logger

log = get_logger(__name__)

# Ruídos comuns em extratos de cartão
NOISE_PATTERNS = [
    r"\*+\w*",                          # *ASSINATURA, ***
    r"\b[A-Z]{2,3}\s+\d{5,}\b",        # SP 12345678, RJ 99999
    r"\b\d{10,}\b",                     # Códigos longos
    r"\b[A-Z0-9]{6,}\*[A-Z0-9]+\b",    # Códigos de transação
    r"\s+\d{2}/\d{2}\s*$",             # Data no final
    r"\s+\d{4}\s*$",                   # Ano no final
    r"\bBRL\b|\bBR\b|\bSA\b|\bLTDA\b|\bME\b|\bEIRELI\b|\bEPP\b",  # Sufixos jurídicos
    r"\b(?:SAO PAULO|RIO DE JANEIRO|BELO HORIZONTE|CURITIBA|SALVADOR|FORTALEZA)\b",
    r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",  # CNPJ
    r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",         # CPF
    r"(?<=[A-Z])\s+\d+\s*$",           # Número no final
    r"\bINT\b|\bCOM\b|\bNET\b$",       # .COM, .NET no final
    r"[.]{2,}",                         # Reticências
    r"[\[\]{}|\\]",                     # Caracteres de ruído
]

# Mapeamentos diretos de normalização (aplicados em ordem)
MERCHANT_ALIASES = {
    "NETFLIX": ["NETFLIX", "NETFLIXCOM", "NETFLIX COM"],
    "SPOTIFY": ["SPOTIFY", "SPOTIFY AB", "SPOTIFY BRAZIL"],
    "UBER": ["UBER", "UBER TRIP", "UBER DO BRASIL", "UBERTRIP"],
    "IFOOD": ["IFOOD", "IFOOD COM", "IFD"],
    "AMAZON": ["AMAZON", "AMAZON BR", "AMAZON BRASIL", "AMZ"],
    "MERCADO LIVRE": ["MERCADO LIVRE", "MERCADOLIVRE", "MELI"],
    "RAPPI": ["RAPPI", "RAPPI BR"],
    "MCDONALDS": ["MCDONALDS", "MC DONALDS", "MCDONALD"],
    "BURGER KING": ["BURGER KING", "BURGERKING"],
    "APPLE": ["APPLE", "APPLE COM BR", "APPLE SERVICES", "APPLE STORE"],
    "GOOGLE": ["GOOGLE", "GOOGLE PLAY", "GOOGLE SERVICES", "GOOGLE LLC"],
    "SHOPEE": ["SHOPEE", "SHOPEE BR"],
    "SMART FIT": ["SMART FIT", "SMARTFIT"],
    "DISNEY PLUS": ["DISNEY PLUS", "DISNEY+", "DISNEY STREAMING"],
    "HBO MAX": ["HBO MAX", "MAX STREAMING", "HBO"],
}

# Inverte o mapeamento para lookup rápido
_ALIAS_LOOKUP: dict[str, str] = {}
for canonical, aliases in MERCHANT_ALIASES.items():
    for alias in aliases:
        _ALIAS_LOOKUP[alias] = canonical


def normalize_description(raw: str) -> tuple[str, str]:
    """
    Normaliza uma descrição de lançamento.
    Retorna (description_norm, merchant).
    """
    if not raw:
        return "", ""

    text = normalize_text(raw)  # Remove acentos, maiúsculo, limpa

    # Aplica remoção de ruídos
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Verifica alias direto
    merchant = _lookup_alias(text)

    # Se não encontrou alias, usa as primeiras palavras significativas
    if not merchant:
        merchant = _extract_merchant_name(text)

    return text, merchant


def _lookup_alias(text: str) -> str:
    """
    Procura texto em tabela de aliases conhecidos.
    Usa correspondencia por palavra inteira (word-boundary) em vez de
    substring, para evitar falsos positivos (ex.: 'ML' batendo em qualquer
    descricao que contenha as letras 'ml').
    """
    # Exato
    if text in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[text]
    # Aliases mais especificos (mais longos) tem prioridade
    for alias in sorted(_ALIAS_LOOKUP, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return _ALIAS_LOOKUP[alias]
    return ""


def _extract_merchant_name(text: str) -> str:
    """
    Extrai nome do merchant das primeiras palavras relevantes.
    Remove números e palavras com menos de 2 caracteres.
    """
    words = text.split()
    clean_words = []
    for word in words[:4]:  # Considera no máximo 4 palavras
        if re.match(r"^\d+$", word):  # Pula tokens numéricos
            continue
        if len(word) < 2:
            continue
        clean_words.append(word)
        if len(clean_words) >= 2:
            break

    return " ".join(clean_words) if clean_words else text[:30]


def batch_normalize(descriptions: list[str]) -> list[tuple[str, str]]:
    """Normaliza uma lista de descrições em batch."""
    return [normalize_description(d) for d in descriptions]
