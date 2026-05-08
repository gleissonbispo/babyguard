"""
Configuração do Servidor BabyGuard.
Carrega valores do .env com fallbacks seguros.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class ServerConfig:
    """Configuração imutável do servidor."""

    # Rede
    host: str = os.getenv("SERVER_HOST", "0.0.0.0")
    port: int = int(os.getenv("SERVER_PORT", "9999"))

    # Telegram
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Detecção
    alert_threshold_seconds: float = float(os.getenv("ALERT_THRESHOLD_SECONDS", "5"))
    alert_message_count: int = int(os.getenv("ALERT_MESSAGE_COUNT", "10"))
    alert_interval_seconds: float = float(os.getenv("ALERT_INTERVAL_SECONDS", "1.0"))

    # Thresholds do acelerômetro (m/s²)
    face_up_threshold: float = 6.0    # az > este valor → FACE_UP
    face_down_threshold: float = -6.0  # az < este valor → FACE_DOWN

    # Health check — 5s era curto demais (qualquer hiccup de rede dispara falso alarme)
    heartbeat_timeout_seconds: float = float(os.getenv("HEARTBEAT_TIMEOUT", "30"))

    def validate(self) -> list[str]:
        """Valida configurações e retorna lista de erros."""
        errors = []
        if not self.telegram_token:
            errors.append("TELEGRAM_BOT_TOKEN não configurado!")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID não configurado!")
        if self.alert_threshold_seconds <= 0:
            errors.append("ALERT_THRESHOLD_SECONDS deve ser > 0!")
        return errors


# Instância global
config = ServerConfig()