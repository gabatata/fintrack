#!/bin/bash
## Script de deploy automatico do FinTrack no Ubuntu (Oracle Cloud / qualquer VPS)
## Execute como: bash deploy.sh
## Requer: Ubuntu 22.04 LTS, usuario com sudo

set -e  # Para se qualquer comando falhar

echo ""
echo "========================================"
echo " FinTrack - Deploy Automatico"
echo "========================================"
echo ""

# ── Variaveis (edite antes de rodar) ──────────────────────────────────────────
APP_DIR="/home/ubuntu/fintrack"
REPO_URL=""  # opcional: URL do seu git repo. Deixe vazio para upload manual.
DOMAIN=""    # Ex: fintrack.meudominio.com ou IP do servidor
# ──────────────────────────────────────────────────────────────────────────────

# Pede o dominio se nao foi preenchido
if [ -z "$DOMAIN" ]; then
    read -p "Dominio ou IP do servidor (ex: 192.168.1.100 ou meuapp.com): " DOMAIN
fi

echo "[1/8] Atualizando sistema..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    nginx certbot python3-certbot-nginx \
    git curl wget \
    tesseract-ocr tesseract-ocr-por \
    libgl1-mesa-glx

echo "[2/8] Criando estrutura de diretorios..."
mkdir -p $APP_DIR
mkdir -p $APP_DIR/data
mkdir -p $APP_DIR/config
mkdir -p $APP_DIR/.streamlit
mkdir -p $APP_DIR/deploy

echo "[3/8] Configurando ambiente virtual Python..."
python3 -m venv $APP_DIR/.venv
$APP_DIR/.venv/bin/pip install --upgrade pip -q

echo "[4/8] Instalando dependencias..."
if [ -f "$APP_DIR/requirements.txt" ]; then
    $APP_DIR/.venv/bin/pip install -r $APP_DIR/requirements.txt -q
else
    echo "AVISO: requirements.txt nao encontrado. Instale manualmente depois."
fi

# Garante que bcrypt e pyyaml estao instalados
$APP_DIR/.venv/bin/pip install bcrypt pyyaml -q

echo "[5/8] Configurando servico systemd..."
sudo cp $APP_DIR/deploy/fintrack.service /etc/systemd/system/fintrack.service

# Ajusta o usuario no service file
CURRENT_USER=$(whoami)
sudo sed -i "s/User=ubuntu/User=$CURRENT_USER/g" /etc/systemd/system/fintrack.service
sudo sed -i "s|/home/ubuntu/fintrack|$APP_DIR|g" /etc/systemd/system/fintrack.service

sudo systemctl daemon-reload
sudo systemctl enable fintrack
sudo systemctl restart fintrack

echo "[6/8] Configurando Nginx..."
sudo cp $APP_DIR/deploy/nginx-fintrack.conf /etc/nginx/sites-available/fintrack
sudo sed -i "s/SEU_DOMINIO/$DOMAIN/g" /etc/nginx/sites-available/fintrack
sudo ln -sf /etc/nginx/sites-available/fintrack /etc/nginx/sites-enabled/fintrack
sudo rm -f /etc/nginx/sites-enabled/default

# Valida config do nginx
sudo nginx -t

echo "[7/8] Configurando SSL com Certbot..."
# Se for IP, pula o SSL (so funciona com dominio)
if [[ $DOMAIN =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "AVISO: IP detectado. SSL so funciona com dominio. Configurando HTTP simples..."
    # Substitui config nginx por versao sem SSL
    sudo bash -c "cat > /etc/nginx/sites-available/fintrack << 'NGINX'
server {
    listen 80;
    server_name $DOMAIN;
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection upgrade;
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }
}
NGINX"
else
    sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN || \
        echo "AVISO: Certbot falhou. Configure SSL manualmente depois."
fi

sudo systemctl restart nginx

echo "[8/8] Configurando firewall..."
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw --force enable

echo ""
echo "========================================"
echo " Deploy concluido!"
echo "========================================"
echo ""
echo "  URL: http://$DOMAIN (ou https:// se SSL configurado)"
echo "  Usuario padrao: gabriel"
echo "  Senha padrao:   fintrack123"
echo ""
echo "  IMPORTANTE: Altere a senha no primeiro acesso!"
echo ""
echo "  Comandos uteis:"
echo "    Ver logs:     sudo journalctl -u fintrack -f"
echo "    Reiniciar:    sudo systemctl restart fintrack"
echo "    Status:       sudo systemctl status fintrack"
echo ""
