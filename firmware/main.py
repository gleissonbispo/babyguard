"""
BabyGuard — Firmware Principal do T-Watch 2020.

Este script:
1. Inicializa o acelerômetro BMA425 via I2C
2. Conecta ao WiFi com reconexão automática e backoff exponencial
3. Envia dados de aceleração via UDP a cada 200ms
4. Watchdog timer para auto-reset se o firmware travar
5. gc.collect() periódico para evitar fragmentação de memória
"""
from machine import Pin, I2C, WDT
import socket
import json
import time
import machine
import gc

from bma423 import BMA423
import wifi
import config

machine.freq(80_000_000)

print("\n" + "=" * 50)
print("  BabyGuard — Iniciando...")
print("=" * 50)

# 1. Inicializar I2C e Acelerômetro
print("\n[1/3] Inicializando acelerômetro...")
i2c = I2C(0, scl=Pin(config.I2C_SCL), sda=Pin(config.I2C_SDA), freq=config.I2C_FREQ)
accel = BMA423(i2c)

# 2. Conectar WiFi — feito ANTES do watchdog pois pode levar até 15 segundos
print("\n[2/3] Conectando WiFi...")
ip = wifi.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

# 3. Criar socket UDP
print("\n[3/3] Configurando comunicação UDP...")
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_addr = (config.SERVER_IP, config.SERVER_PORT)
print(f"  Destino: {config.SERVER_IP}:{config.SERVER_PORT}")

# Watchdog criado APOS toda inicialização — reseta se o loop principal
# travar por mais de 8 segundos (proteção contra bloqueios inesperados)
wdt = WDT(timeout=8000)

print("\n" + "=" * 50)
print("  BabyGuard ATIVO — Monitorando bebê!")
print("=" * 50)

# ===== CONSTANTES DO LOOP (definidas fora do loop para eficiência) =====

WIFI_CHECK_INTERVAL = 150  # 150 * 200ms = 30 segundos entre verificações
GC_INTERVAL = 250          # 250 * 200ms = 50 segundos entre gc.collect()
LOG_INTERVAL = 25          # 25 * 200ms = 5 segundos entre logs no console

seq = 0
_wifi_backoff = 1  # segundos de backoff exponencial para reconexão WiFi

# ===== LOOP PRINCIPAL =====

try:
    while True:
        wdt.feed()  # Informar ao watchdog que o firmware está vivo

        # Ler acelerômetro com tratamento de falha
        try:
            reading = accel.get_full_reading()
        except Exception as e:
            print(f"  Accel: Erro na leitura: {e}")
            time.sleep_ms(config.SEND_INTERVAL_MS)
            continue

        # ts usa ticks_ms() — mais confiável que time.time() sem NTP
        packet = {
            "id": config.DEVICE_ID,
            "ts": time.ticks_ms(),
            "seq": seq,
            "ax": reading["ax"],
            "ay": reading["ay"],
            "az": reading["az"],
            "pos": reading["pos"],
        }

        try:
            data = json.dumps(packet).encode()
            sock.sendto(data, server_addr)
            _wifi_backoff = 1  # Resetar backoff após envio bem-sucedido
        except OSError as e:
            print(f"  UDP: Erro ao enviar: {e}")

        seq += 1

        # Log periódico com status de memória
        if seq % LOG_INTERVAL == 0:
            print(
                f"  Pkts: {seq} | Pos: {reading['pos']} "
                f"| Z: {reading['az']:.1f} | RAM livre: {gc.mem_free()}"
            )

        # Verificar e reconectar WiFi se necessário
        if seq % WIFI_CHECK_INTERVAL == 0 and not wifi.is_connected():
            print(f"  WiFi: Desconectado! Backoff: {_wifi_backoff}s")
            time.sleep(_wifi_backoff)
            try:
                # Passa wdt.feed como callback — alimentado a cada segundo
                # da tentativa de reconexão, evitando reset do watchdog
                ip = wifi.connect(
                    config.WIFI_SSID,
                    config.WIFI_PASSWORD,
                    watchdog_feed=wdt.feed,
                )
                _wifi_backoff = 1
                print(f"  WiFi: Reconectado! IP: {ip}")
            except Exception as e:
                print(f"  WiFi: Falha na reconexão: {e}")
                # Backoff exponencial: 1 → 2 → 4 → 8 → 16 → 32 → 60s (máx)
                _wifi_backoff = min(_wifi_backoff * 2, 60)

        # Liberar memória fragmentada periodicamente
        if seq % GC_INTERVAL == 0:
            gc.collect()

        time.sleep_ms(config.SEND_INTERVAL_MS)

except KeyboardInterrupt:
    print("\n\n  BabyGuard desligado.")
    sock.close()
    wifi.disconnect()
