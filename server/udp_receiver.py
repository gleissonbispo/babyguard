"""
Receptor UDP assíncrono.

Recebe pacotes do T-Watch 2020 e coloca numa fila (asyncio.Queue)
para processamento pelo detector de posição.
"""
import asyncio
import json
import logging
from datetime import datetime

logger = logging.getLogger("babyguard.udp")

_MAX_PACKET_SIZE = 512  # bytes — pacotes maiores são descartados (proteção contra lixo)
_REQUIRED_FIELDS = {"az", "pos"}  # campos obrigatórios para processamento


class UDPReceiver:
    """Recebe dados do acelerômetro via UDP."""

    def __init__(self, host: str, port: int, data_queue: asyncio.Queue):
        self.host = host
        self.port = port
        self.data_queue = data_queue
        self.packet_count = 0
        self.last_packet_time: datetime | None = None
        self._transport = None

    async def start(self) -> None:
        """Inicia o servidor UDP."""
        loop = asyncio.get_event_loop()

        transport, _ = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(self),
            local_addr=(self.host, self.port),
        )
        self._transport = transport
        logger.info(f"UDP escutando em {self.host}:{self.port}")

    async def stop(self) -> None:
        """Para o servidor UDP."""
        if self._transport:
            self._transport.close()
            logger.info("UDP parado.")

    def _handle_packet(self, data: bytes, addr: tuple) -> None:
        """Valida e enfileira um pacote recebido."""
        # Rejeitar pacotes absurdamente grandes (proteção contra DoS local)
        if len(data) > _MAX_PACKET_SIZE:
            logger.warning(
                f"Pacote muito grande de {addr[0]}: {len(data)} bytes (máximo: {_MAX_PACKET_SIZE})"
            )
            return

        # Decodificar JSON
        try:
            packet = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Pacote malformado de {addr[0]}: {e} | raw: {data[:80]!r}")
            return

        if not isinstance(packet, dict):
            logger.error(f"Pacote não é um objeto JSON de {addr[0]}")
            return

        # Validar campos obrigatórios
        missing = _REQUIRED_FIELDS - packet.keys()
        if missing:
            logger.warning(f"Pacote sem campos obrigatórios {missing} de {addr[0]}")
            return

        # Validar tipos dos campos críticos
        if not isinstance(packet.get("az"), (int, float)):
            logger.warning(f"Campo 'az' inválido de {addr[0]}: {packet.get('az')!r}")
            return

        # Enriquecer pacote com metadados do servidor
        packet["_received_at"] = datetime.now().isoformat()
        packet["_source_ip"] = addr[0]

        self.packet_count += 1
        self.last_packet_time = datetime.now()

        # Enfileirar para processamento — descarta mais antigo se cheio
        try:
            self.data_queue.put_nowait(packet)
        except asyncio.QueueFull:
            logger.warning("Fila cheia! Descartando pacote mais antigo.")
            try:
                self.data_queue.get_nowait()
                self.data_queue.put_nowait(packet)
            except asyncio.QueueEmpty:
                pass


class _UDPProtocol(asyncio.DatagramProtocol):
    """Protocolo asyncio para recepção UDP."""

    def __init__(self, receiver: UDPReceiver):
        self.receiver = receiver

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self.receiver._handle_packet(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.error(f"Erro UDP: {exc}")
