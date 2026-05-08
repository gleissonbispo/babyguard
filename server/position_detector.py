"""
Detector de Posição do BabyGuard.

Responsável por:
- Suavizar dados do acelerômetro (média móvel)
- Classificar a posição do bebê
- Rastrear duração de cada posição
- Emitir eventos quando condições de alerta são atendidas

Usa uma máquina de estados simples:

    ┌────────┐    az < -6.0     ┌──────────┐   > 5s   ┌─────────┐
    │  SAFE  │ ───────────────→ │ COUNTING │ ────────→ │ ALERT!  │
    │(UP/SIDE│ ←─────────────── │ (DOWN)   │           │(DOWN>5s)│
    └────────┘    az > -6.0     └──────────┘           └────┬────┘
         ▲                                                   │
         │              az > -6.0                            │
         └───────────────────────────────────────────────────┘
"""
import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable

logger = logging.getLogger("babyguard.detector")


class Position(str, Enum):
    """Posições possíveis do bebê."""
    FACE_UP = "UP"
    FACE_DOWN = "DOWN"
    SIDE = "SIDE"
    UNKNOWN = "UNKNOWN"


class SystemState(str, Enum):
    """Estados do sistema de monitoramento."""
    SAFE = "SAFE"          # Posição segura
    COUNTING = "COUNTING"  # Face down, contando tempo
    ALERT = "ALERT"        # Alerta ativo!
    OFFLINE = "OFFLINE"    # Sem dados do relógio


@dataclass
class DetectorStatus:
    """Status atual do detector — snapshot para o dashboard."""
    position: Position = Position.UNKNOWN
    state: SystemState = SystemState.OFFLINE
    face_down_seconds: float = 0.0
    smoothed_az: float = 0.0
    raw_az: float = 0.0
    packets_received: int = 0
    last_update: float = 0.0
    alert_triggered: bool = False
    alerts_sent_total: int = 0


class PositionDetector:
    """
    Detecta a posição do bebê e gerencia alertas.

    Usa média móvel para suavizar ruído do acelerômetro
    e uma máquina de estados para rastrear condições de perigo.
    """

    def __init__(
        self,
        face_down_threshold: float = -6.0,
        alert_threshold_seconds: float = 5.0,
        smoothing_window: int = 10,
        on_alert: Callable[[], Awaitable[None]] | None = None,
        on_safe: Callable[[], Awaitable[None]] | None = None,
    ):
        # Configuração
        self.face_down_threshold = face_down_threshold
        self.alert_threshold_seconds = alert_threshold_seconds
        self.smoothing_window = smoothing_window

        # Callbacks
        self._on_alert = on_alert
        self._on_safe = on_safe

        # Estado interno
        self._az_buffer: deque = deque(maxlen=smoothing_window)
        self._state = SystemState.OFFLINE
        self._position = Position.UNKNOWN
        self._face_down_start: float | None = None
        self._alert_active = False
        self._packets_received = 0
        self._alerts_sent_total = 0
        self._last_update = 0.0
        self._raw_az = 0.0

    def _smooth_az(self, new_az: float) -> float:
        """
        Calcula média móvel do eixo Z.

        A média móvel elimina picos de ruído. Com janela de 10 amostras
        a 5 amostras/segundo, suavizamos em ~2 segundos — rápido o
        suficiente para detectar uma virada real, lento o suficiente
        para ignorar uma batidinha.
        """
        self._az_buffer.append(new_az)
        return sum(self._az_buffer) / len(self._az_buffer)

    def _classify_position(self, smoothed_az: float) -> Position:
        """Classifica a posição baseado no eixo Z suavizado."""
        if smoothed_az > 6.0:
            return Position.FACE_UP
        elif smoothed_az < self.face_down_threshold:
            return Position.FACE_DOWN
        else:
            return Position.SIDE

    async def process_reading(self, packet: dict):
        """
        Processa uma leitura do acelerômetro.

        Este é o método principal — chamado para cada pacote UDP recebido.
        Atualiza a máquina de estados e dispara callbacks quando necessário.
        """
        az = packet.get("az", 0.0)
        self._raw_az = az
        self._packets_received += 1
        self._last_update = time.time()

        # 1. Suavizar
        smoothed_az = self._smooth_az(az)

        # 2. Classificar posição
        new_position = self._classify_position(smoothed_az)
        old_position = self._position
        self._position = new_position

        # 3. Máquina de estados
        now = time.time()

        if new_position == Position.FACE_DOWN:
            # Iniciou face down
            if self._face_down_start is None:
                self._face_down_start = now
                self._state = SystemState.COUNTING
                logger.warning("⚠️  Bebê virou de barriga para BAIXO! Contando...")

            # Verificar se ultrapassou o threshold
            elapsed = now - self._face_down_start
            if elapsed >= self.alert_threshold_seconds and not self._alert_active:
                self._state = SystemState.ALERT
                self._alert_active = True
                self._alerts_sent_total += 1
                logger.critical(
                    f"🚨 ALERTA! Bebê de barriga para baixo há {elapsed:.1f}s!"
                )
                if self._on_alert:
                    await self._on_alert()

        else:
            # Não está face down — resetar
            if self._face_down_start is not None:
                elapsed = now - self._face_down_start
                logger.info(
                    f"✅ Bebê voltou à posição segura. "
                    f"Ficou face down por {elapsed:.1f}s"
                )
                self._face_down_start = None

            if self._alert_active:
                self._alert_active = False
                logger.info("✅ Alerta cancelado — posição segura.")
                if self._on_safe:
                    await self._on_safe()

            self._state = SystemState.SAFE

    @property
    def face_down_seconds(self) -> float:
        """Retorna há quantos segundos o bebê está face down."""
        if self._face_down_start is None:
            return 0.0
        return time.time() - self._face_down_start

    @property
    def status(self) -> DetectorStatus:
        """Retorna snapshot do status atual."""
        smoothed = (
            sum(self._az_buffer) / len(self._az_buffer) if self._az_buffer else 0.0
        )
        return DetectorStatus(
            position=self._position,
            state=self._state,
            face_down_seconds=self.face_down_seconds,
            smoothed_az=round(smoothed, 2),
            raw_az=round(self._raw_az, 2),
            packets_received=self._packets_received,
            last_update=self._last_update,
            alert_triggered=self._alert_active,
            alerts_sent_total=self._alerts_sent_total,
        )