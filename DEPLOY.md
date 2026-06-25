# FinTrack — Guia de Deploy no Oracle Cloud
### Windows 10 + Acesso pelo PC e Celular

---

## O que voce vai ter no final

- FinTrack rodando 24h na nuvem, **gratuito**
- Acesso pelo celular ou qualquer PC so abrindo o navegador
- Um **atalho na Area de Trabalho** que abre o app com um duplo clique
- Dados compartilhados entre todos os dispositivos

```
Clique duplo no atalho
        ↓
  Navegador abre
        ↓
  Tela de login
        ↓
  Oracle Cloud (Ubuntu) — rodando 24h
        ├── Nginx (HTTPS)
        ├── FinTrack (Streamlit)
        └── fintrack.db (SQLite)
```

---

## Ferramentas necessarias no Windows

Baixe antes de comecar:

| Ferramenta | Link | Para que serve |
|---|---|---|
| **PuTTY** | https://putty.org | Terminal SSH (conectar no servidor) |
| **PuTTYgen** | (vem junto com PuTTY) | Gerar chave SSH |
| **WinSCP** | https://winscp.net | Enviar arquivos para o servidor |

---

## Parte 1 — Criar servidor Oracle Cloud (gratuito)

### 1.1 Criar conta Oracle Cloud
1. Acesse **https://cloud.oracle.com** e clique em **"Start for free"**
2. Preencha nome, email, telefone
3. Use um cartao de credito valido — **nao cobra nada no Free Tier**
4. Escolha a regiao: **Brazil East (Sao Paulo)**
5. Confirme o email e conclua o cadastro

### 1.2 Gerar chave SSH com PuTTYgen
Voce precisa de uma chave SSH para se conectar ao servidor com seguranca.

1. Abra o **PuTTYgen** (vem junto com o instalador do PuTTY)
2. Clique em **"Generate"** e mova o mouse pela area em branco ate completar a barra
3. No campo **"Key comment"**, escreva: `fintrack`
4. Clique em **"Save private key"** → salve como `fintrack_key.ppk` em `C:\Users\Gabriel\.ssh\`
   - Se a pasta `.ssh` nao existir, crie ela
5. **Copie todo o texto** que aparece no campo grande no topo (começa com `ssh-rsa...`) — voce vai precisar dele no proximo passo

### 1.3 Criar a instancia (servidor virtual)
1. No Oracle Cloud, menu lateral → **Compute → Instances → Create Instance**
2. Configure:
   - **Name:** `fintrack`
   - **Image:** clique em "Change Image" → selecione **Ubuntu 22.04 LTS (Minimal)**
   - **Shape:** clique em "Change Shape" → Ampere → `VM.Standard.A1.Flex`
     - OCPUs: **2**, Memory: **12 GB** (maximo gratuito)
   - **Add SSH keys:** selecione "Paste public keys" e cole o texto `ssh-rsa...` que copiou
3. Clique em **"Create"** e aguarde ~2 minutos

### 1.4 Anotar o IP do servidor
1. Clique na instancia criada
2. Anote o **"Public IP address"** (ex: `150.230.45.123`)

### 1.5 Abrir portas no firewall Oracle (OBRIGATORIO)
O Oracle tem um firewall proprio que precisa ser configurado:

1. Na pagina da instancia, clique no nome da **Subnet**
2. Clique em **"Default Security List"**
3. Clique em **"Add Ingress Rules"** e adicione:

| Source CIDR | Protocol | Port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

4. Clique em **"Add Ingress Rules"** para salvar

---

## Parte 2 — (Opcional) Configurar dominio

Se tiver um dominio (ex: no Registro.br):
1. Crie um registro DNS tipo **A**:
   - Nome: `fintrack` (ou qualquer subdominio)
   - Valor: IP do servidor Oracle
2. Aguarde ~15 minutos para propagacao

Se nao tiver dominio, use o IP diretamente — funciona normalmente, so sem HTTPS.

---

## Parte 3 — Conectar ao servidor com PuTTY

1. Abra o **PuTTY**
2. Em **"Host Name"**, digite o IP do servidor: `150.230.45.123`
3. Port: `22`
4. No menu lateral: **Connection → SSH → Auth → Credentials**
5. Em **"Private key file"**, clique em "Browse" e selecione o arquivo `fintrack_key.ppk`
6. Volte em **Session**, em **"Saved Sessions"** escreva `fintrack` e clique em **Save**
   (assim voce nao precisa configurar toda vez)
7. Clique em **"Open"**
8. Na primeira conexao aparece um aviso de segurança → clique **"Accept"**
9. Login: `ubuntu` (pressione Enter — sem senha, a chave e a autenticacao)

Voce deve ver algo como: `ubuntu@fintrack:~$`

---

## Parte 4 — Enviar os arquivos com WinSCP

1. Abra o **WinSCP**
2. Clique em **"New Site"**
3. Configure:
   - **File protocol:** SFTP
   - **Host name:** IP do servidor
   - **Port:** 22
   - **User name:** `ubuntu`
4. Clique em **"Advanced..."** → SSH → Authentication
5. Em **"Private key file"**, selecione o `fintrack_key.ppk`
6. Clique OK → **Save** (com o nome `fintrack`) → **Login**
7. Na janela do WinSCP:
   - **Lado esquerdo:** navegue ate `C:\Users\Gabriel\Desktop\Apps\fintrack\`
   - **Lado direito:** voce esta em `/home/ubuntu/`
   - **Arraste a pasta `fintrack`** do lado esquerdo para o lado direito
8. Aguarde o upload (pode levar 1-2 minutos)

---

## Parte 5 — Rodar o deploy

De volta ao PuTTY (terminal do servidor):

```bash
cd ~/fintrack
chmod +x deploy/deploy.sh
bash deploy/deploy.sh
```

Quando perguntar o dominio ou IP, digite o IP do servidor (ou seu dominio, se tiver):
```
Dominio ou IP do servidor: 150.230.45.123
```

O script vai instalar tudo automaticamente (~5 minutos). No final voce ve:
```
Deploy concluido!
URL: http://150.230.45.123
Usuario padrao: gabriel
Senha padrao:   fintrack123
```

---

## Parte 6 — Migrar seus dados do PC

Para levar o banco de dados atual para o servidor:

1. No WinSCP, abra novamente a conexao `fintrack`
2. Lado esquerdo: navegue ate `C:\Users\Gabriel\Desktop\Apps\fintrack\fintrack\data\`
3. Lado direito: navegue ate `/home/ubuntu/fintrack/data/`
4. Arraste o arquivo `fintrack.db` para o lado direito
5. No PuTTY, reinicie o app:
```bash
sudo systemctl restart fintrack
```

---

## Parte 7 — Criar o atalho na Area de Trabalho

### 7.1 Editar a URL nos arquivos de atalho
Antes de criar o atalho, voce precisa colocar o IP/dominio:

1. Abra o arquivo `create_shortcut.ps1` no Bloco de Notas
2. Na linha `$URL = "https://SEU_DOMINIO_OU_IP"`, substitua pelo seu IP ou dominio:
   ```
   $URL = "http://150.230.45.123"
   ```
   (use `https://` se tiver dominio com SSL, `http://` se for so IP)
3. Salve o arquivo

### 7.2 Rodar o script de criacao do atalho
1. Clique com botao direito no arquivo `create_shortcut.ps1`
2. Selecione **"Executar com PowerShell"**
3. Se aparecer aviso de seguranca, clique em **"Executar assim mesmo"**
4. Um atalho **FinTrack** aparece na Area de Trabalho

### 7.3 Testar
- Clique duplo no atalho **FinTrack** na Area de Trabalho
- O navegador abre automaticamente na tela de login
- Entre com `gabriel` / `fintrack123`
- **IMEDIATAMENTE** vá em "Alterar senha" no menu lateral e troque a senha!

### 7.4 Atalho no celular (Android/iPhone)
No celular, abra o navegador e acesse `http://IP_DO_SERVIDOR`:
- **Android Chrome:** menu (tres pontos) → "Adicionar a tela inicial"
- **iPhone Safari:** botao compartilhar → "Adicionar a tela inicial"

O icone aparece na tela inicial como se fosse um app.

---

## Atualizando o app no futuro

Quando receber arquivos novos do FinTrack:
1. Abra WinSCP → conecte em `fintrack`
2. Arraste os arquivos novos para as pastas correspondentes no servidor
3. No PuTTY:
```bash
sudo systemctl restart fintrack
```

---

## Comandos uteis no PuTTY

```bash
# Ver se o app esta rodando
sudo systemctl status fintrack

# Ver logs em tempo real (Ctrl+C para sair)
sudo journalctl -u fintrack -f

# Reiniciar o app
sudo systemctl restart fintrack

# Ver uso de disco
df -h

# Ver uso de memoria
free -h
```

---

## Custos

| Recurso | Custo |
|---|---|
| Servidor Oracle Cloud (2 cores, 12GB RAM) | **Gratuito permanente** |
| 50 GB de armazenamento | **Gratuito** |
| Transferencia de dados (10 TB/mes) | **Gratuito** |
| Dominio .com.br (opcional) | ~R$ 40/ano |
| SSL Let's Encrypt (opcional) | **Gratuito** |
| **Total mensal** | **R$ 0** |

---

## Solucao de problemas

**Nao consigo conectar no PuTTY**
- Verifique se adicionou as regras de Ingress no Oracle (Parte 1.5)
- Verifique se o IP esta correto

**App nao abre no navegador**
```bash
sudo systemctl status fintrack   # ve se esta rodando
sudo journalctl -u fintrack -n 50  # ve os ultimos erros
```

**WinSCP nao conecta**
- Verifique se selecionou o arquivo `.ppk` correto (nao o `.pub`)
- Confirme que o usuario e `ubuntu` (minusculo)

**Esqueci a senha do FinTrack**
No PuTTY:
```bash
cd ~/fintrack
.venv/bin/python3 - << 'EOF'
import sys; sys.path.insert(0,'.')
from auth import hash_password, _load_config, _save_config
config = _load_config()
config['users']['gabriel']['password'] = hash_password('nova_senha_aqui')
_save_config(config)
print('Senha redefinida!')
EOF
```
