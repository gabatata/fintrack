# 💰 FinTrack — Gestão Financeira Pessoal

Aplicação local para importar extratos PDF de cartões, extrair lançamentos com OCR, categorizar gastos e visualizar dashboards financeiros.

---

## 📦 Stack

| Componente | Tecnologia |
|---|---|
| Interface | Streamlit |
| Banco de dados | SQLite (local, sem servidor) |
| Extração PDF | pdfplumber + pypdf |
| OCR | Tesseract + PyMuPDF |
| Dados | pandas |
| Gráficos | Plotly |

---

## 🚀 Instalação e execução — passo a passo

### 1. Pré-requisitos

- Python 3.10 ou superior
- Git (opcional)

### 2. Instalar o Tesseract OCR no sistema

**Ubuntu / Debian / WSL:**
```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-por
```

**macOS (Homebrew):**
```bash
brew install tesseract
brew install tesseract-lang  # inclui português
```

**Windows:**
1. Baixe o instalador em: https://github.com/UB-Mannheim/tesseract/wiki
2. Instale e adicione o caminho ao PATH do sistema
3. Baixe o arquivo de língua portuguesa (`por.traineddata`) e coloque em `C:\Program Files\Tesseract-OCR\tessdata\`

**Verificar instalação:**
```bash
tesseract --version
tesseract --list-langs  # deve mostrar "por" na lista
```

### 3. Clonar / baixar o projeto

```bash
# Se via git:
git clone <url-do-repo>
cd fintrack

# Ou simplesmente extraia o .zip e entre na pasta
```

### 4. Criar ambiente virtual (recomendado)

```bash
python -m venv .venv

# Ativar no Linux/macOS:
source .venv/bin/activate

# Ativar no Windows:
.venv\Scripts\activate
```

### 5. Instalar dependências Python

```bash
pip install -r requirements.txt
```

> **Nota:** `opencv-python-headless` pode demorar um pouco na primeira instalação.

### 6. (Opcional) Carregar dados de demonstração

Para ver a aplicação funcionando com dados fictícios antes de importar seus extratos:

```bash
python seed_data.py
```

Isso cria ~4 meses de lançamentos de demonstração com categorias, recorrências e múltiplos cartões.

### 7. Rodar a aplicação

```bash
streamlit run app.py
```

A aplicação abrirá automaticamente em `http://localhost:8501` no seu navegador.

---

## 📁 Estrutura do projeto

```
fintrack/
├── app.py                    # Entrypoint Streamlit
├── seed_data.py              # Gerador de dados de demonstração
├── requirements.txt
│
├── database/
│   ├── connection.py         # Conexão SQLite
│   └── models.py             # Schema + inicialização
│
├── pages/
│   ├── components.py         # Componentes UI reutilizáveis
│   ├── dashboard.py          # Dashboard principal
│   ├── import_pdf.py         # Importação de PDFs
│   ├── transactions.py       # Lista e edição de lançamentos
│   ├── recurring.py          # Recorrentes / assinaturas
│   ├── manual_expense.py     # Cadastro manual
│   ├── category_rules.py     # Gerenciamento de regras
│   └── import_history.py     # Histórico de importações
│
├── parsers/
│   ├── base_parser.py        # Classe base abstrata
│   ├── generic_parser.py     # Parser genérico (regex)
│   ├── nubank_parser.py      # Parser específico Nubank
│   ├── parser_factory.py     # Seleção automática de parser
│   └── pdf_reader.py         # Extração de texto
│
├── ocr/
│   ├── ocr_engine.py         # Motor OCR (Tesseract)
│   ├── preprocessor.py       # Pré-processamento de imagem
│   └── quality_checker.py    # Decisão de usar OCR
│
├── services/
│   ├── import_service.py     # Pipeline de importação
│   ├── transaction_service.py # CRUD de transações
│   ├── categorization_service.py # Regras de categoria
│   ├── normalization_service.py  # Normalização de descrições
│   ├── recurrence_service.py     # Detecção de recorrência
│   └── deduplication_service.py  # Anti-duplicata
│
├── utils/
│   ├── helpers.py            # Funções utilitárias
│   └── logger.py             # Logger centralizado
│
└── data/
    ├── fintrack.db           # Banco SQLite (criado automaticamente)
    ├── fintrack.log          # Log da aplicação
    └── uploads/              # PDFs importados
```

---

## 🗄️ Schema do banco de dados

### `imports`
Registro de cada arquivo PDF importado. Campo `file_hash` evita reimportação.

### `transactions`
Todos os lançamentos (de PDFs ou manuais). Inclui descrição original, normalizada, merchant, categoria, status de revisão e flag de recorrência.

### `category_rules`
Regras de palavra-chave para categorização automática. Suporta `contains`, `startswith`, `exact` e `regex`.

### `recurring_patterns`
Padrões de recorrência detectados. Status: `suggested` → `confirmed` ou `dismissed`.

### `processing_logs`
Log detalhado de cada etapa do pipeline de importação (útil para debug).

### `app_config`
Configurações chave-valor da aplicação.

---

## 🔧 Como adicionar parsers para novos bancos

1. Crie `parsers/meuparser.py` herdando de `BaseParser`
2. Implemente `can_parse()` (retorna True se o PDF for do seu banco)
3. Implemente `parse_text()` (extrai lançamentos)
4. Registre em `parsers/parser_factory.py` na lista `SPECIFIC_PARSERS`

---

## 💡 Dicas de uso

- **Primeira vez:** Rode `python seed_data.py` para ver o dashboard com dados reais
- **Revisão:** Lançamentos importados ficam como "Pendente" até você revisá-los
- **Regras:** Corrija uma categoria manualmente → marque "Criar regra automática" para que funcione nos próximos imports
- **Recorrências:** Execute "Re-detectar recorrências" após importar vários meses
- **Backup:** Basta copiar o arquivo `data/fintrack.db`

---

## 🛠️ Solução de problemas

**OCR não funciona:**
```bash
# Verifique se está instalado:
which tesseract
tesseract --list-langs

# Se não aparecer "por", instale:
sudo apt install tesseract-ocr-por
```

**PDF não extrai texto:**
- O PDF pode ser uma imagem escaneada → ative o OCR
- Alguns PDFs protegidos não permitem extração → tente remover a proteção antes

**Erro de importação:**
- Verifique os logs em `data/fintrack.log`
- Acesse "Histórico de Importações" → clique em "Ver logs"
