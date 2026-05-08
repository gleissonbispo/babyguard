"""
UDP Simulator — Simula o T-Watch 2020 enviando dados para o servidor.

Uso: python tests/udp_simulator.py [--scenario SCENARIO] [--host HOST] [--port PORT]

Cenários disponíveis:
  stable_up       Bebê de costas estável (padrão)
  stable_down     Bebê de bruços estável (deve disparar alerta em 5s)
  flip_test       Começa de costas, vira de bruços por 10s, volta
  noisy           Sinal ruidoso com picos esporádicos
  wifi_drop       Simula interrupção seguida de reconexão

Execute: python tests/udp_simulator.py --scenario flip_test
"""
import socket
import json
import time
import argparse
import math
import random
from datetime import datetime

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9999
SEND_INTERVAL = 0.2  # 200ms, igual ao firmware real


def send_packet(sock: socket.socket, addr: tuple, seq: int, az: float, pos: str) -> None:
    packet = {
        "id": "simulator-001",
        "ts": int(time.time() * 1000),
        "seq": seq,
        "ax": round(random.uniform(-0.3, 0.3), 2),
        "ay": round(random.uniform(-0.3, 0.3), 2),
        "az": round(az, 2),
        "pos": pos,
    }
    data = json.dumps(packet).encode()
    sock.sendto(data, addr)


def classify(az: float) -> str:
    if az > 6.0:
        return "UP"
    elif az < -6.0:
        return "DOWN"
    return "SIDE"


def run_scenario(scenario: str, host: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = (host, port)
    seq = 0

    print(f"Simulando cenário '{scenario}' para {host}:{port}")
    print("Ctrl+C para parar\n")

    try:
        if scenario == "stable_up":
            while True:
                az = 9.5 + random.uniform(-0.3, 0.3)
                send_packet(sock, addr, seq, az, "UP")
                if seq % 25 == 0:
                    print(f"  [{seq:>6d}] UP   | Z: {az:+.2f}")
                seq += 1
                time.sleep(SEND_INTERVAL)

        elif scenario == "stable_down":
            print("ATENÇÃO: Este cenário deve disparar alerta em ~5 segundos!\n")
            while True:
                az = -9.5 + random.uniform(-0.3, 0.3)
                send_packet(sock, addr, seq, az, "DOWN")
                if seq % 25 == 0:
                    print(f"  [{seq:>6d}] DOWN | Z: {az:+.2f}")
                seq += 1
                time.sleep(SEND_INTERVAL)

        elif scenario == "flip_test":
            phases = [
                (10.0, 9.5, "UP",   "Fase 1: face up (10s)"),
                (10.0, -9.5, "DOWN", "Fase 2: face DOWN - alerta em 5s!"),
                (10.0, 9.5, "UP",   "Fase 3: voltou seguro (10s)"),
                (5.0,  0.0, "SIDE", "Fase 4: de lado (5s)"),
            ]
            for duration, az_base, pos, label in phases:
                print(f"\n{label}")
                end = time.time() + duration
                while time.time() < end:
                    az = az_base + random.uniform(-0.3, 0.3)
                    actual_pos = classify(az)
                    send_packet(sock, addr, seq, az, actual_pos)
                    seq += 1
                    time.sleep(SEND_INTERVAL)

        elif scenario == "noisy":
            print("Sinal ruidoso com picos esporádicos de DOWN...\n")
            while True:
                # 90% UP, 10% picos DOWN
                if random.random() < 0.1:
                    az = -9.0
                    pos = "DOWN"
                else:
                    az = 9.5 + random.uniform(-0.5, 0.5)
                    pos = "UP"
                send_packet(sock, addr, seq, az, pos)
                if seq % 25 == 0:
                    print(f"  [{seq:>6d}] {pos:>4s} | Z: {az:+.2f}")
                seq += 1
                time.sleep(SEND_INTERVAL)

        elif scenario == "wifi_drop":
            print("Simulando queda de WiFi após 5s...\n")
            end_connected = time.time() + 5
            while time.time() < end_connected:
                az = 9.5 + random.uniform(-0.2, 0.2)
                send_packet(sock, addr, seq, az, "UP")
                seq += 1
                time.sleep(SEND_INTERVAL)

            print("WiFi caiu! Sem envio por 15 segundos...")
            time.sleep(15)

            print("WiFi reconectado! Retomando...\n")
            while True:
                az = 9.5 + random.uniform(-0.2, 0.2)
                send_packet(sock, addr, seq, az, "UP")
                if seq % 25 == 0:
                    print(f"  [{seq:>6d}] UP   | Z: {az:+.2f}")
                seq += 1
                time.sleep(SEND_INTERVAL)

    except KeyboardInterrupt:
        print(f"\n\nSimulação encerrada. Pacotes enviados: {seq}")
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="Simulador UDP do BabyGuard")
    parser.add_argument(
        "--scenario",
        choices=["stable_up", "stable_down", "flip_test", "noisy", "wifi_drop"],
        default="stable_up",
        help="Cenário a simular",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    run_scenario(args.scenario, args.host, args.port)


if __name__ == "__main__":
    main()
