# BabyGuard — Guia de Deploy no Raspberry Pi Zero W2

> Guia prático e completo para colocar o BabyGuard em produção. Siga os passos em ordem. Ao final, o servidor será iniciado automaticamente toda vez que o Pi ligar.

---

## Visão geral do processo

```
1. Flash do OS no cartão SD
2. Primeiro acesso via SSH
3. Atualizar sistema e configurar segurança
4. Instalar Python e dependências
5. Clonar/copiar o código
6. Configurar .env com credenciais
7. Testar manualmente
8. Criar serviço systemd
9. Testar o serviço
10. Checklist final antes de usar com o bebê
```

---

## 1. Preparação do Raspberry Pi Zero W2

### 1.1 Download e flash do Raspberry Pi OS

1. Baixe o **Raspberry Pi Imager** em [raspberrypi.com/software](https://www.raspberrypi.com/software/)
2. Abra o Imager
3. Clique em **Choose OS** → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (64-bit)**
   - Por que Lite? Sem interface gráfica — economiza ~200MB de RAM
   - Por que 64-bit? O Zero W2 tem processador de 64 bits; aproveite
4. Clique em **Choose Storage** → selecione seu cartão SD (mínimo 8GB)
5. Clique no ícone de engrenagem (configurações avançadas) antes de gravar:
   - **Hostname:** `babyguard`
   - **Enable SSH:** sim, com senha
   - **Username:** `pi`
   - **Password:** escolha uma senha forte (não use `raspberry`)
   - **WiFi SSID e Password:** configure aqui — o Pi vai conectar automaticamente
   - **Timezone:** `America/Sao_Paulo`
6. Clique **WRITE** e aguarde (~5 minutos)

### 1.2 Primeiro acesso via SSH

Insira o cartão SD no Pi, ligue-o e aguarde ~60 segundos para o boot.

```bash
# No seu PC (Windows: use PuTTY ou Windows Terminal)
ssh pi@babyguard.local

# Se não funcionar pelo hostname, descubra o IP no roteador e use:
ssh pi@192.168.1.XXX
```

### 1.3 Atualização do sistema

```bash
# Atualizar lista de pacotes e instalar atualizações
sudo apt update && sudo apt upgrade -y

# Isso pode demorar 5-15 minutos no Zero W2 — tenha paciência
```

### 1.4 Configurações de segurança básicas

```bash
# Alterar hostname (se não fez pelo Imager)
sudo hostnamectl set-hostname babyguard

# Verificar data/hora
timedatectl
# Se errada:
sudo timedatectl set-timezone America/Sao_Paulo

# Instalar fail2ban (bloqueia tentativas de força bruta no SSH)
sudo apt install fail2ban -y
```

---

## 2. Instalação do Ambiente Python

### 2.1 Verificar Python disponível

```bash
python3 --version
# Raspberry Pi OS Bookworm vem com Python 3.11+
# Se for < 3.11, instale:
# sudo apt install python3.11 python3.11-venv -y
```

### 2.2 Criar ambiente virtual

```bash
# Instalar dependências do venv
sudo apt install python3-venv python3-pip -y

# Criar venv no diretório home do usuário pi
python3 -m venv /home/pi/venv

# Ativar (você precisará fazer isso toda vez que usar manualmente)
source /home/pi/venv/bin/activate
```

> **Por que não usar Docker?**  
> O Raspberry Pi Zero W2 tem apenas 512MB de RAM. Um container Docker ocupa ~50-100MB adicionais. Com um venv Python, o overhead é praticamente zero. Para este projeto, Docker não traz benefício algum e prejudica a performance.

---

## 3. Deploy do Código

### 3.1 Opção A: Git clone (recomendado se o repositório for privado ou você for atualizar)

```bash
# Instalar git
sudo apt install git -y

# Clonar o repositório
cd /home/pi
git clone https://github.com/SEU_USUARIO/babyguard.git
cd babyguard
```

### 3.2 Opção B: rsync/scp (do seu PC para o Pi)

```bash
# Do seu PC (ajuste o caminho):
rsync -avz --exclude '.env' --exclude 'data/' --exclude '__pycache__' \
    "C:/Users/SeuUsuario/Área de Trabalho/Projetos Portfolio/babyguard/" \
    pi@babyguard.local:/home/pi/babyguard/
```

### 3.3 Instalar dependências Python

```bash
# No Pi, com venv ativado:
source /home/pi/venv/bin/activate
cd /home/pi/babyguard
pip install -r server/requirements.txt
```

### 3.4 Configurar o .env

```bash
# Criar arquivo de configuração
cd /home/pi/babyguard
cp .env.example .env
nano .env
```

Preencha com seus valores reais:
```env
TELEGRAM_BOT_TOKEN=SEU_TOKEN_AQUI
TELEGRAM_CHAT_ID=SEU_CHAT_ID_AQUI
SERVER_HOST=0.0.0.0
SERVER_PORT=9999
ALERT_THRESHOLD_SECONDS=5
HEARTBEAT_TIMEOUT=30
```

Para obter seu chat_id: envie uma mensagem para o seu bot e acesse:
```
https://api.telegram.org/botSEU_TOKEN/getUpdates
```

### 3.5 Criar diretório de dados

```bash
mkdir -p /home/pi/babyguard/data
```

### 3.6 Testar manualmente antes de criar o serviço

```bash
source /home/pi/venv/bin/activate
cd /home/pi/babyguard
python3 server/babyguard_server.py
```

Você deve ver algo como:
```
14:32:01 [babyguard] INFO: BabyGuard Server ATIVO!
14:32:01 [babyguard] INFO: UDP: 0.0.0.0:9999
14:32:01 [babyguard.telegram] INFO: Telegram Alerter inicializado.
```

E receber mensagem no Telegram: `🟢 BabyGuard ATIVO`

Em outro terminal, verifique se o UDP está chegando:
```bash
# Ligar o relógio e observar:
sudo tcpdump -i wlan0 udp port 9999 -c 10
```

Para parar: `Ctrl+C`

---

## 4. Serviço systemd

### 4.1 Criar o arquivo de serviço

```bash
sudo nano /etc/systemd/system/babyguard.service
```

Cole o conteúdo abaixo:

```ini
[Unit]
Description=BabyGuard Baby Monitor Server
Documentation=https://github.com/gleissonbispo/babyguard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/babyguard
ExecStart=/home/pi/venv/bin/python3 server/babyguard_server.py

# Reinicia sempre que o processo sair (por erro ou normalmente)
Restart=always
RestartSec=5

# Variáveis de ambiente do arquivo .env
EnvironmentFile=/home/pi/babyguard/.env

# Limites de segurança
NoNewPrivileges=true

# Logs para journald
StandardOutput=journal
StandardError=journal
SyslogIdentifier=babyguard

[Install]
WantedBy=multi-user.target
```

### 4.2 Ativar e iniciar o serviço

```bash
# Recarregar systemd para reconhecer o novo arquivo
sudo systemctl daemon-reload

# Habilitar no boot automático
sudo systemctl enable babyguard

# Iniciar agora
sudo systemctl start babyguard

# Verificar status
sudo systemctl status babyguard
```

Saída esperada:
```
● babyguard.service - BabyGuard Baby Monitor Server
     Loaded: loaded (/etc/systemd/system/babyguard.service; enabled)
     Active: active (running) since ...
```

### 4.3 Comandos úteis do dia a dia

```bash
# Ver status atual
systemctl status babyguard

# Ver logs em tempo real (Ctrl+C para sair)
journalctl -u babyguard -f

# Ver últimas 100 linhas de log
journalctl -u babyguard -n 100

# Reiniciar o serviço (após atualizar o código, por exemplo)
sudo systemctl restart babyguard

# Parar temporariamente
sudo systemctl stop babyguard

# Desabilitar do boot (se quiser desligar permanentemente)
sudo systemctl disable babyguard
```

---

## 5. Monitoramento e Manutenção

### 5.1 Script de health check (cron)

Crie um script que verifica se o serviço está rodando e reinicia se necessário:

```bash
nano /home/pi/babyguard/scripts/healthcheck.sh
```

```bash
#!/bin/bash
if ! systemctl is-active --quiet babyguard; then
    echo "$(date): BabyGuard parado! Reiniciando..." >> /home/pi/babyguard/data/healthcheck.log
    systemctl start babyguard
fi
```

```bash
chmod +x /home/pi/babyguard/scripts/healthcheck.sh

# Adicionar ao cron (verifica a cada 5 minutos)
crontab -e
```

Adicione a linha:
```
*/5 * * * * /home/pi/babyguard/scripts/healthcheck.sh
```

### 5.2 Limpeza periódica do banco de dados

O SQLite cresce indefinidamente. Crie uma limpeza semanal:

```bash
nano /home/pi/babyguard/scripts/cleanup_db.sh
```

```bash
#!/bin/bash
DB="/home/pi/babyguard/data/babyguard.db"
# Apagar registros de posição com mais de 30 dias
sqlite3 "$DB" "DELETE FROM position_log WHERE timestamp < strftime('%s', 'now', '-30 days');"
sqlite3 "$DB" "DELETE FROM heartbeat_log WHERE timestamp < strftime('%s', 'now', '-30 days');"
sqlite3 "$DB" "VACUUM;"
echo "$(date): Limpeza do banco concluída" >> /home/pi/babyguard/data/cleanup.log
```

```bash
chmod +x /home/pi/babyguard/scripts/cleanup_db.sh

# Adicionar ao cron (todo domingo às 3h)
crontab -e
# 0 3 * * 0 /home/pi/babyguard/scripts/cleanup_db.sh
```

### 5.3 Monitorar temperatura do CPU

O Zero W2 pode superaquecer sem dissipador:

```bash
# Temperatura atual
vcgencmd measure_temp

# Monitorar em tempo real
watch -n 2 vcgencmd measure_temp

# Normal: 50-65°C em idle. Acima de 80°C é preocupante.
```

Recomendação: use um dissipador de alumínio sobre o processador do Pi Zero W2.

### 5.4 Monitorar RAM e disco

```bash
# Uso de memória
free -h

# Uso de disco
df -h

# Processos e CPU
top
# ou (mais amigável):
htop  # sudo apt install htop -y
```

### 5.5 Rotação de logs do systemd

Por padrão, journald retém logs até encher o disco. Configure um limite:

```bash
sudo nano /etc/systemd/journald.conf
```

Adicione ou descomente:
```ini
SystemMaxUse=100M
MaxRetentionSec=2week
```

```bash
sudo systemctl restart systemd-journald
```

### 5.6 Atualizar o código em produção

```bash
# Com git:
cd /home/pi/babyguard
git pull
sudo systemctl restart babyguard

# Com rsync (do seu PC):
rsync -avz --exclude '.env' --exclude 'data/' \
    "C:/Users/gleis/.../babyguard/" \
    pi@babyguard.local:/home/pi/babyguard/
ssh pi@babyguard.local "sudo systemctl restart babyguard"
```

---

## 6. Otimizações para Zero W2

### 6.1 Desabilitar serviços desnecessários

```bash
# Bluetooth (não usamos)
sudo systemctl disable bluetooth
sudo systemctl disable hciuart

# Avahi/mDNS (útil para .local, mas consome recursos)
# Desabilite apenas se não precisar de babyguard.local:
# sudo systemctl disable avahi-daemon

# Serviço de impressão (definitivamente não precisamos)
sudo systemctl disable cups 2>/dev/null || true
```

### 6.2 Configurar swap com ZRAM

O Zero W2 tem 512MB RAM. ZRAM cria swap comprimido na RAM — melhor que swap em cartão SD (que desgasta o cartão).

```bash
sudo apt install zram-tools -y

# Configurar para usar 50% da RAM como zram
sudo nano /etc/default/zramswap
# PERCENT=50

sudo systemctl restart zramswap
```

### 6.3 Sem dashboard Streamlit em produção

O dashboard consome ~150-200MB de RAM quando rodando. No Zero W2 com 512MB, isso é inaceitável. **Não inicie o Streamlit em produção.**

Todos os alertas importantes chegam via Telegram. O SQLite pode ser consultado diretamente:
```bash
sqlite3 /home/pi/babyguard/data/babyguard.db \
    "SELECT datetime(timestamp,'unixepoch','localtime'), alert_type, duration_seconds \
     FROM alert_log ORDER BY timestamp DESC LIMIT 20;"
```

### 6.4 Configurar timezone

```bash
sudo timedatectl set-timezone America/Sao_Paulo
timedatectl  # Verificar
```

---

## 7. Troubleshooting

### O serviço não inicia

```bash
# Ver erros detalhados
journalctl -u babyguard -n 50 --no-pager

# Testar manualmente para ver o erro:
source /home/pi/venv/bin/activate
cd /home/pi/babyguard
python3 server/babyguard_server.py
```

Causas comuns:
- `.env` não existe ou tem token errado → verifique com `cat .env`
- `data/` não existe → `mkdir -p /home/pi/babyguard/data`
- Dependências não instaladas → `pip install -r server/requirements.txt`
- Porta 9999 em uso → `sudo lsof -i :9999`

### Não recebe dados do relógio

```bash
# Verificar se o UDP está chegando
sudo tcpdump -i wlan0 udp port 9999 -c 10

# Verificar se a porta está aberta no servidor
sudo ss -ulnp | grep 9999

# Verificar firewall (se habilitado)
sudo ufw status
sudo ufw allow 9999/udp
```

Causas comuns:
- Relógio e Pi em redes diferentes (invitado vs principal)
- IP do servidor errado no `firmware/config.py`
- Relógio sem WiFi (verifique a saída serial via Thonny)

### Mensagens do Telegram não chegam

```bash
# Testar a API do Telegram manualmente
curl -s "https://api.telegram.org/botSEU_TOKEN/getMe" | python3 -m json.tool
```

Causas comuns:
- Token inválido → recrie o bot com BotFather
- Chat ID errado → use `getUpdates` para confirmar
- Internet do Pi sem acesso ao Telegram → `ping api.telegram.org`
- Firewall bloqueando HTTPS saída → raro em rede doméstica

### Verificar se o UDP está chegando (método simples)

```bash
# Instalar netcat
sudo apt install netcat-openbsd -y

# Escutar na porta 9999 e exibir dados recebidos
nc -u -l 9999

# Em outro terminal, se quiser simular pacotes do relógio:
echo '{"id":"test","az":9.5,"pos":"UP"}' | nc -u localhost 9999
```

### Testar alertas Telegram de forma isolada

```bash
source /home/pi/venv/bin/activate
cd /home/pi/babyguard
python3 -c "
import asyncio
from server.telegram_alerter import TelegramAlerter
import os
from dotenv import load_dotenv
load_dotenv()

async def test():
    a = TelegramAlerter(os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID'))
    await a.start()
    await asyncio.sleep(2)
    await a.stop()

asyncio.run(test())
"
```

### Resetar tudo e começar do zero

```bash
sudo systemctl stop babyguard
sudo systemctl disable babyguard
sudo rm /etc/systemd/system/babyguard.service
sudo systemctl daemon-reload

rm -rf /home/pi/babyguard/data/
# Refaça a partir do passo 3.5
```

---

## 8. Checklist de Deploy

Execute estes testes antes de confiar o bebê ao sistema:

### Hardware
- [ ] T-Watch carregado (bateria > 80%)
- [ ] Firmware carregado e funcionando (LED piscando ou output no Thonny)
- [ ] Relógio fixado firmemente na roupa do bebê (não solto)
- [ ] Raspberry Pi Zero W2 ligado e com dissipador (temperatura < 65°C)

### Rede
- [ ] Relógio conectado ao WiFi (verificar RSSI no serial)
- [ ] Raspberry Pi na mesma rede WiFi
- [ ] Pacotes UDP chegando ao servidor (`tcpdump`)

### Software
- [ ] Serviço systemd rodando: `systemctl status babyguard`
- [ ] Sem erros nos logs: `journalctl -u babyguard -n 20`
- [ ] `.env` configurado com credenciais válidas

### Telegram
- [ ] Mensagem `BabyGuard ATIVO` recebida no Telegram
- [ ] **Teste real**: vire o relógio de barriga pra baixo por 6 segundos
- [ ] Alertas chegaram no celular de todos os responsáveis
- [ ] Alertas pararam após virar de volta

### Final
- [ ] Carregador do Pi conectado (não use bateria portátil — pode acabar)
- [ ] Celular com notificações do Telegram habilitadas e volume ligado
- [ ] Todos os responsáveis têm o chat do bot salvo

---

> **Lembrete:** este guia assume uso em rede doméstica. Para deployment em rede corporativa ou com requisitos de segurança adicionais, consulte um profissional de TI.
