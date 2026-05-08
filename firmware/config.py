"""
Configurações do BabyGuard — Firmware do T-Watch 2020.
⚠️ Edite os valores abaixo antes de fazer upload!
"""

# === WiFi ===
WIFI_SSID = "sua_rede"
WIFI_PASSWORD = "sua_senha"

# === Servidor ===
# IP do computador/Raspberry Pi que vai rodar o servidor Python
# Descubra com `ipconfig` (Windows) ou `ifconfig`/`ip addr` (Linux)
SERVER_IP = "192.168.1.199"
SERVER_PORT = 9999

# === Dispositivo ===
DEVICE_ID = "babyguard-001"

# === Timing ===
SEND_INTERVAL_MS = 200  # Enviar dados a cada 200ms (5x por segundo)

# === Hardware T-Watch 2020 ===
I2C_SDA = 21
I2C_SCL = 22
I2C_FREQ = 400000
VIBRATION_PIN = 4