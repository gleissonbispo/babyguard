"""
Sistema de Alertas via Telegram.

Envia mensagens urgentes quando o bebê está em posição de perigo.
Usa aiohttp para chamadas HTTP assíncronas à API do Telegram.
"""
import asyncio
import logging

import aiohttp

logger = logging.getLogger("babyguard.telegram")

_ALERT_MESSAGES = [
    "🚨🚨🚨 <b>ALERTA BABYGUARD!</b> 🚨🚨🚨\n\n"
    "O BEBE ESTA DE BARRIGA PARA BAIXO HA MAIS DE 5 SEGUNDOS!\n\n"
    "VERIFIQUE O BEBE AGORA!",

    "🔴🔴🔴 ALERTA 2/10 🔴🔴🔴\n\n"
    "O BEBE CONTINUA DE BARRIGA PARA BAIXO!\n"
    "VIRE O BEBE IMEDIATAMENTE!",

    "⚠️⚠️⚠️ ALERTA 3/10 ⚠️⚠️⚠️\n\n"
    "ATENCAO! BEBE EM POSICAO DE RISCO!\n"
    "ACORDE E VERIFIQUE!",

    "🚨 ALERTA 4/10\n\n"
    "BEBE AINDA DE BARRIGA PARA BAIXO!\n"
    "RISCO DE SUFOCAMENTO!",

    "🔴 ALERTA 5/10\n\n"
    "METADE DOS ALERTAS ENVIADOS!\n"
    "O BEBE PRECISA SER VIRADO!",

    "⚠️ ALERTA 6/10\n\nVERIFIQUE O BEBE AGORA!",
    "🚨 ALERTA 7/10\n\nBEBE EM PERIGO! ACORDE!",
    "🔴 ALERTA 8/10\n\nURGENTE! VERIFIQUE O BEBE!",
    "⚠️ ALERTA 9/10\n\nULTIMO AVISO! BEBE DE BARRIGA PARA BAIXO!",

    "🚨🚨🚨 ALERTA 10/10 — REINICIANDO CICLO 🚨🚨🚨\n\n"
    "TODOS OS ALERTAS DESTE CICLO FORAM ENVIADOS.\n"
    "Um novo ciclo começa agora — acorde e verifique o bebe!",
]

_BETWEEN_CYCLES_PAUSE_SECONDS = 30  # pausa entre ciclos repetidos de alerta


class TelegramAlerter:
    """Gerencia envio de alertas via Telegram Bot API."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        alert_count: int = 10,
        alert_interval: float = 1.0,
    ):
        self.token = token
        self.chat_id = chat_id
        self.alert_count = alert_count
        self.alert_interval = alert_interval
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._session: aiohttp.ClientSession | None = None
        self._alerting = False
        self._alert_task: asyncio.Task | None = None
        self.total_messages_sent = 0

    async def start(self) -> None:
        """Inicializa a sessão HTTP e envia mensagem de ativação."""
        self._session = aiohttp.ClientSession()
        logger.info("Telegram Alerter inicializado.")
        await self._send_message(
            "🟢 <b>BabyGuard ATIVO</b>\n\n"
            "O sistema de monitoramento está ligado e funcionando.\n"
            "Você receberá alertas se o bebê virar de barriga para baixo."
        )

    async def stop(self) -> None:
        """Cancela alertas ativos, envia mensagem de encerramento e fecha sessão."""
        await self.cancel_alert()
        if self._session:
            await self._send_message(
                "🔴 <b>BabyGuard DESLIGADO</b>\n\n"
                "O sistema de monitoramento foi encerrado."
            )
            await self._session.close()
            logger.info("Telegram Alerter encerrado.")

    async def _send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        max_retries: int = 3,
    ) -> bool:
        """
        Envia uma mensagem via Telegram com retry e backoff exponencial.

        Retorna True se enviado com sucesso, False após esgotar tentativas.
        """
        if not self._session:
            logger.error("Sessão não inicializada!")
            return False

        url = f"{self._base_url}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}

        for attempt in range(max_retries):
            try:
                async with self._session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        self.total_messages_sent += 1
                        return True

                    error_code = data.get("error_code", 0)
                    description = data.get("description", "")

                    # Rate limit: aguardar o retry_after sugerido pela API
                    if error_code == 429:
                        retry_after = data.get("parameters", {}).get("retry_after", 2 ** attempt)
                        logger.warning(f"Rate limit Telegram — aguardando {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    logger.error(f"Telegram API erro: {description}")
                    return False

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                backoff = 2 ** attempt
                logger.warning(f"Tentativa {attempt + 1}/{max_retries} falhou: {e}. Backoff: {backoff}s")
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff)

        logger.error("Mensagem Telegram descartada após esgotar tentativas.")
        return False

    async def trigger_alert(self) -> None:
        """
        Inicia sequência de alertas em loop.

        Envia alert_count mensagens (1/segundo) e repete com pausa de 30s
        enquanto o bebê permanecer face down. A repetição garante que os
        pais sejam acordados mesmo se dormirem durante o primeiro ciclo.
        """
        if self._alerting:
            logger.warning("Alerta já em andamento — ignorando segundo trigger.")
            return

        self._alerting = True
        self._alert_task = asyncio.create_task(self._alert_sequence())

    async def _alert_sequence(self) -> None:
        """Loop de alertas: repete ciclos até bebê voltar à posição segura."""
        cycle = 0
        while self._alerting:
            cycle += 1
            logger.critical(f"Iniciando ciclo de alertas #{cycle}")

            for i, message in enumerate(self._get_alert_messages()):
                if not self._alerting:
                    logger.info(f"Sequência cancelada no ciclo #{cycle}, mensagem {i + 1}.")
                    return

                success = await self._send_message(message)
                if success:
                    logger.warning(f"[Ciclo {cycle}] Alerta {i + 1}/{self.alert_count} enviado.")
                else:
                    logger.error(f"[Ciclo {cycle}] Falha ao enviar alerta {i + 1}.")

                if i < self.alert_count - 1:
                    await asyncio.sleep(self.alert_interval)

            if self._alerting:
                logger.info(f"Ciclo #{cycle} completo — pausa de {_BETWEEN_CYCLES_PAUSE_SECONDS}s.")
                # Pausa entre ciclos, verificando cancelamento a cada segundo
                for _ in range(_BETWEEN_CYCLES_PAUSE_SECONDS):
                    if not self._alerting:
                        return
                    await asyncio.sleep(1)

        logger.info("Sequência de alertas encerrada.")

    def _get_alert_messages(self) -> list[str]:
        """Retorna as mensagens de alerta limitadas a alert_count."""
        return _ALERT_MESSAGES[: self.alert_count]

    async def cancel_alert(self) -> None:
        """Cancela a sequência de alertas e envia confirmação de segurança."""
        if self._alerting:
            self._alerting = False
            if self._alert_task and not self._alert_task.done():
                self._alert_task.cancel()
                try:
                    await self._alert_task
                except asyncio.CancelledError:
                    pass

            await self._send_message(
                "✅ <b>TUDO BEM!</b>\n\n"
                "O bebê voltou para a posição segura.\n"
                "O monitoramento continua ativo."
            )
            logger.info("Alerta cancelado — bebê em posição segura.")

    async def send_status(self, status_text: str) -> None:
        """Envia mensagem de status (não-urgente)."""
        await self._send_message(f"ℹ️ {status_text}")

    async def send_heartbeat_lost(self, elapsed_seconds: float) -> None:
        """Alerta quando perde conexão com o relógio."""
        await self._send_message(
            "⚠️ <b>CONEXÃO PERDIDA</b>\n\n"
            f"O relógio BabyGuard não envia dados há {elapsed_seconds:.0f}s!\n"
            "Verifique se o relógio está ligado e no alcance do WiFi.\n\n"
            "<b>Atenção:</b> o monitoramento está inativo enquanto o relógio estiver offline."
        )
