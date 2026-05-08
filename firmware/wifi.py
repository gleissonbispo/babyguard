"""
Módulo WiFi para o BabyGuard.
Gerencia conexão com a rede WiFi doméstica.
"""
import network
import time


def connect(ssid, password, timeout=15, watchdog_feed=None):
    """
    Conecta o ESP32 à rede WiFi.

    Args:
        ssid: Nome da rede WiFi.
        password: Senha da rede WiFi.
        timeout: Tempo máximo de espera em segundos.
        watchdog_feed: Callback opcional chamado a cada segundo durante a
            espera — use para alimentar o watchdog timer e evitar reset.

    Returns:
        str: Endereço IP atribuído.

    Raises:
        RuntimeError: Se não conseguir conectar dentro do timeout.
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print(f"  Ja conectado! IP: {ip}")
        return ip

    print(f"  Conectando a '{ssid}'", end="")
    wlan.connect(ssid, password)

    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout:
            wlan.active(False)
            raise RuntimeError(
                f"Timeout! Nao conseguiu conectar a '{ssid}' em {timeout}s. "
                "Verifique SSID e senha."
            )
        if watchdog_feed:
            watchdog_feed()
        print(".", end="")
        time.sleep(1)

    ip = wlan.ifconfig()[0]
    print(f"\n  Conectado! IP: {ip}")
    print(f"  Gateway: {wlan.ifconfig()[2]}")
    print(f"  RSSI: {wlan.status('rssi')} dBm")

    return ip


def disconnect():
    """Desconecta do WiFi."""
    wlan = network.WLAN(network.STA_IF)
    wlan.disconnect()
    wlan.active(False)
    print("  WiFi desconectado.")


def is_connected() -> bool:
    """Verifica se está conectado."""
    wlan = network.WLAN(network.STA_IF)
    return wlan.isconnected()


def get_ip() -> str:
    """Retorna o IP atual ou '0.0.0.0' se desconectado."""
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        return wlan.ifconfig()[0]
    return "0.0.0.0"
