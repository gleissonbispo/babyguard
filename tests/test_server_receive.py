"""
Teste: Servidor recebe dados UDP e exibe.
Execute este teste e depois rode o simulador (test_udp_sender.py).
"""
import asyncio
import json
from datetime import datetime

HOST = "0.0.0.0"
PORT = 9999

ICONS = {"UP": "🟢", "DOWN": "🔴", "SIDE": "🟡"}


class SimpleProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.count = 0

    def datagram_received(self, data, addr):
        self.count += 1
        try:
            packet = json.loads(data.decode())
            pos = packet.get("pos", "?")
            az = packet.get("az", 0)
            icon = ICONS.get(pos, "❓")
            now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"  [{now}] #{self.count:>5d} | {icon} {pos:>4s} | Z:{az:+7.2f} | from {addr[0]}")
        except Exception as e:
            print(f"  Erro: {e}")


async def main():
    print("=" * 55)
    print("  BabyGuard — Teste do Servidor (Receptor)")
    print(f"  Escutando em {HOST}:{PORT}")
    print("  Rode test_udp_sender.py em outro terminal!")
    print("=" * 55 + "\n")

    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        SimpleProtocol,
        local_addr=(HOST, PORT),
    )

    try:
        await asyncio.sleep(3600)  # Roda por 1 hora
    finally:
        transport.close()


if __name__ == "__main__":
    asyncio.run(main())