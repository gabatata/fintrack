# Deploy grátis do FinTrack (online, sem PC ligado)

Stack: **GitHub** (código) + **Supabase Storage** (banco) + **Streamlit Community Cloud** (roda o app).
Resultado: uma URL privada (só seu Google) que abre no celular e no PC, com o PC desligado.

O código já está preparado e commitado. Siga os 3 passos.

---

## Passo 1 — GitHub (subir o código)

1. Em https://github.com/new crie um repositório **privado** chamado `fintrack` (não marque "Add README").
2. No terminal, dentro da pasta do projeto, rode (troque `SEU_USUARIO`):

   ```bash
   git remote add origin https://github.com/SEU_USUARIO/fintrack.git
   git push -u origin main
   ```

   Se pedir login, aceite o popup do navegador (você já está logado no GitHub no Chrome).

---

## Passo 2 — Supabase (guardar o banco)

1. Em https://supabase.com → **New project** (escolha região mais perto, ex: South America).
   Anote a senha do banco (não vamos usá-la, mas o Supabase pede).
2. No projeto: menu **Storage** → **New bucket** → nome **`fintrack`** → deixe **Private** → Create.
3. Entre no bucket `fintrack` → **Upload file** → envie o arquivo:

   ```
   data/seed_supabase/fintrack.db
   ```

   ⚠️ O nome do arquivo no bucket precisa ficar **`fintrack.db`** (é o que ele já é).
4. Pegue as credenciais: menu **Project Settings** (engrenagem) → **API**:
   - **Project URL** → algo como `https://abcd1234.supabase.co`
   - **Project API keys** → copie a chave **`service_role`** (a secreta, NÃO a `anon`).

   > A `service_role` fica só no servidor do Streamlit (nos secrets), nunca no git. Por isso o bucket pode ser privado.

---

## Passo 3 — Streamlit Community Cloud (rodar o app)

1. Em https://share.streamlit.io → **Create app** → **Deploy from GitHub**.
2. Selecione: repositório `SEU_USUARIO/fintrack`, branch `main`, **Main file path** = `app.py`.
3. **Advanced settings**:
   - **Python version**: `3.11` (ou 3.12).
   - **Secrets**: cole exatamente isto (preenchendo com os seus valores do Passo 2):

     ```toml
     [supabase]
     url = "https://SEU-PROJETO.supabase.co"
     key = "SUA_SERVICE_ROLE_KEY"
     bucket = "fintrack"
     db_object = "fintrack.db"
     ```
4. Clique **Deploy**. A primeira vez leva alguns minutos (instala as dependências).

### Deixar privado (só você)
Depois que subir: no painel do app → **Settings** → **Sharing** →
"Who can view this app" = **specific people** → adicione seu **e-mail do Google**.
Pronto: só você, logado no Google, consegue abrir.

---

## Como fica o dia a dia

- **Usar**: abra a URL no celular ou PC, logue com seu Google. Sempre online, PC desligado.
- **Importar PDF / editar / excluir**: funciona igual ao local; cada mudança é
  salva no Supabase automaticamente (o banco sincroniza sozinho).
- **Mexer no código**: edite localmente, teste com `run_local.bat`, e suba com
  `git push`. O Streamlit Cloud reimplanta sozinho a cada push.

## Coisas boas de saber

- **Cold start**: se ficar sem uso, o app "dorme" e a primeira abertura demora ~30s pra acordar. Normal.
- **Supabase grátis dorme após ~7 dias sem uso**: se um dia o app der erro de
  sincronização, entre no painel do Supabase e clique pra reativar o projeto.
- **Um usuário por vez**: o banco é sincronizado como arquivo único. Evite editar
  ao mesmo tempo em dois aparelhos (a última gravação vence).
- **Backup**: seu banco local (`data/fintrack.db`) continua existindo como cópia
  de segurança. Para baixar o da nuvem, é só pegar o arquivo no bucket do Supabase.

## Testar a sincronização ANTES de subir (opcional)

Crie `.streamlit/secrets.toml` (já é ignorado pelo git) com o mesmo bloco `[supabase]`
acima e rode `run_local.bat`. O app vai **baixar** o banco da nuvem ao abrir e
**enviar** a cada alteração. (Cuidado: nesse modo o seu local passa a refletir o da nuvem.)
