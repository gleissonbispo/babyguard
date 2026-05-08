"""
BabyGuard Server — Servidor Principal.

Orquestra todos os componentes:
- Recepção UDP dos dados do acelerômetro
- Detecção de posição
- Alertas via Telegram
- Logging no banco de dados
- Monitoramento de heartbeat (conexão com o relógio)
"""
import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

from config import config
from udp_receiver import UDPReceiver
from position_detector import PositionDetector
from telegram_alerter import TelegramAlerter
import database as db

# Garantir que o diretório de dados existe antes de configurar o FileHandler
Path("data").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/babyguard.log"),
    ],
)
logger = logging.getLogger("babyguard")

_HEARTBEAT_ALERT_COOLDOWN = 300  # segundos entre alertas de heartbeat perdido


class BabyGuardServer:
    """Servidor principal do BabyGuard."""

    def __init__(self):
        self.data_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        self.alerter = TelegramAlerter(
            token=config.telegram_token,
            chat_id=config.telegram_chat_id,
            alert_count=config.alert_message_count,
            alert_interval=config.alert_interval_seconds,
        )

        self.detector = PositionDetector(
            face_down_threshold=config.face_down_threshold,
            alert_threshold_seconds=config.alert_threshold_seconds,
            on_alert=self._on_alert,
            on_safe=self._on_safe,
        )

        self.receiver = UDPReceiver(
            host=config.host,
            port=config.port,
            data_queue=self.data_queue,
        )

        self._running = False
        self._last_log_time = 0.0
        self._log_interval = 5.0
        self._last_device_id = "unknown"
        self._last_heartbeat_alert_time = 0.0

    async def _on_alert(self) -> None:
        """Callback quando alerta é disparado."""
        logger.critical("DISPARANDO ALERTAS TELEGRAM!")
        db.log_alert(
            device_id=self._last_device_id,
            alert_type="FACE_DOWN_ALERT",
            duration=self.detector.face_down_seconds,
            message="Bebê de barriga para baixo por mais de 5 segundos",
        )
        await self.alerter.trigger_alert()

    async def _on_safe(self) -> None:
        """Callback quando bebê volta à posição segura."""
        logger.info("Bebê em posição segura — cancelando alertas.")
        db.log_alert(
            device_id=self._last_device_id,
            alert_type="RETURNED_SAFE",
            duration=self.detector.face_down_seconds,
            message="Bebê voltou à posição segura",
        )
        await self.alerter.cancel_alert()

    async def _process_data(self) -> None:
        """Loop principal: processa dados da fila e monitora heartbeat."""
        while self._running:
            try:
                packet = await asyncio.wait_for(
                    self.data_queue.get(), timeout=1.0
                )
                self._last_device_id = packet.get("id", "unknown")
                await self.detector.process_reading(packet)

                # Log periódico no banco de dados
                now = time.time()
                if now - self._last_log_time >= self._log_interval:
                    status = self.detector.status
                    db.log_position(
                        device_id=self._last_device_id,
                        position=status.position.value,
                        az=status.smoothed_az,
                        ax=packet.get("ax", 0),
                        ay=packet.get("ay", 0),
                    )
                    self._last_log_time = now

            except asyncio.TimeoutError:
                await self._check_heartbeat()
            except Exception as e:
                logger.error(f"Erro no processamento: {e}", exc_info=True)

    async def _check_heartbeat(self) -> None:
        """Verifica se o relógio está enviando dados e alerta se não estiver."""
        if not self.receiver.last_packet_time:
            return

        elapsed = time.time() - self.receiver.last_packet_time.timestamp()
        if elapsed <= config.heartbeat_timeout_seconds:
            return

        logger.warning(f"Sem dados do relógio há {elapsed:.0f}s!")

        # Alertar no Telegram com cooldown para não spammar
        now = time.time()
        if now - self._last_heartbeat_alert_time >= _HEARTBEAT_ALERT_COOLDOWN:
            self._last_heartbeat_alert_time = now
            await self.alerter.send_heartbeat_lost(elapsed)

    async def _print_status(self) -> None:
        """Exibe status no terminal a cada 500ms."""
        icons = {"SAFE": "🟢", "COUNTING": "🟡", "ALERT": "🔴", "OFFLINE": "⚫"}

        while self._running:
            status = self.detector.status
            icon = icons.get(status.state.value, "?")

            line = (
                f"  {icon} {status.state.value:>8s} "
                f"| Pos: {status.position.value:>4s} "
                f"| Z: {status.smoothed_az:+7.2f} "
                f"| FaceDown: {status.face_down_seconds:5.1f}s "
                f"| Pkts: {status.packets_received} "
                f"| Alertas: {status.alerts_sent_total}"
            )
            print(f"\r{line}", end="", flush=True)

            await asyncio.sleep(0.5)

    async def start(self) -> None:
        """Valida config, inicia todos os componentes e entra no loop principal."""
        errors = config.validate()
        if errors:
            for err in errors:
                logger.error(f"Config: {err}")
            logger.error("Corrija as configurações no .env e tente novamente.")
            sys.exit(1)

        db.init_db()
        await self.receiver.start()
        await self.alerter.start()

        self._running = True

        logger.info("=" * 55)
        logger.info("  BabyGuard Server ATIVO!")
        logger.info(f"  UDP: {config.host}:{config.port}")
        logger.info(f"  Threshold: {config.alert_threshold_seconds}s")
        logger.info(f"  Alertas: {config.alert_message_count} mensagens")
        logger.info(f"  Heartbeat timeout: {config.heartbeat_timeout_seconds}s")
        logger.info("=" * 55)

        await asyncio.gather(
            self._process_data(),
            self._print_status(),
        )

    async def stop(self) -> None:
        """Para todos os componentes de forma graciosa."""
        if not self._running:
            return
        self._running = False
        await self.receiver.stop()
        await self.alerter.stop()
        logger.info("BabyGuard Server encerrado.")


async def main() -> None:
    server = BabyGuardServer()
    stop_event = asyncio.Event()

    def _request_stop():
        asyncio.create_task(server.stop())
        stop_event.set()

    # Registrar handlers de sinal (SIGTERM não existe no Windows, mas SIGINT sim)
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT,):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except (NotImplementedError, AttributeError):
            pass  # Windows não suporta add_signal_handler para todos os sinais

    # SIGTERM só existe em Unix
    if hasattr(signal, "SIGTERM"):
        try:
            loop.add_signal_handler(signal.SIGTERM, _request_stop)
        except (NotImplementedError, AttributeError):
            pass

    try:
        await server.start()
    except KeyboardInterrupt:
        pass
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
