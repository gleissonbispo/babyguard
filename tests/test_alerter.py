"""
Unit tests for TelegramAlerter.

No real Telegram messages are sent — all HTTP calls are mocked.
Run with: pytest tests/test_alerter.py -v
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import telegram_alerter as ta_module
from telegram_alerter import TelegramAlerter


@pytest.fixture
def alerter():
    """Alerter with 3 messages and fast interval for quick tests."""
    inst = TelegramAlerter(
        token="fake_token_123",
        chat_id="99999",
        alert_count=3,
        alert_interval=0.01,
    )
    inst._session = MagicMock()
    return inst


# ---------------------------------------------------------------------------
# Alert sequence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_sends_exactly_alert_count_messages(alerter):
    """trigger_alert should send exactly alert_count messages in one cycle."""
    with patch.object(alerter, "_send_message", new_callable=AsyncMock, return_value=True) as mock:
        await alerter.trigger_alert()
        await asyncio.sleep(0.15)

    assert mock.call_count == 3


@pytest.mark.asyncio
async def test_cancel_stops_sequence_before_completion(alerter):
    """cancel_alert should abort the sequence before all messages are sent."""
    sent = []

    async def slow_send(text, **kwargs):
        sent.append(text)
        await asyncio.sleep(0.05)
        return True

    with patch.object(alerter, "_send_message", side_effect=slow_send):
        await alerter.trigger_alert()
        await asyncio.sleep(0.03)
        await alerter.cancel_alert()

    # With 50ms/message and cancel at 30ms, at most 1 message sent
    assert len(sent) < 3


@pytest.mark.asyncio
async def test_no_overlapping_alert_cycles(alerter):
    """Second trigger_alert while first is running should be a no-op."""
    with patch.object(alerter, "_send_message", new_callable=AsyncMock, return_value=True):
        await alerter.trigger_alert()
        first_task = alerter._alert_task

        await alerter.trigger_alert()  # Should be ignored
        second_task = alerter._alert_task

    assert first_task is second_task

    # Cleanup
    alerter._alerting = False
    first_task.cancel()


@pytest.mark.asyncio
async def test_alert_cycles_repeat_while_still_alerting(alerter):
    """Alert sequence loops until cancelled — parents must be woken up."""
    original_pause = ta_module._BETWEEN_CYCLES_PAUSE_SECONDS
    ta_module._BETWEEN_CYCLES_PAUSE_SECONDS = 0

    cycle_count = [0]
    original_get = alerter._get_alert_messages

    def counting_get():
        cycle_count[0] += 1
        return original_get()

    try:
        with patch.object(alerter, "_send_message", new_callable=AsyncMock, return_value=True), \
             patch.object(alerter, "_get_alert_messages", side_effect=counting_get):
            await alerter.trigger_alert()
            await asyncio.sleep(0.3)  # Enough time for 2+ fast cycles
            alerter._alerting = False
            if alerter._alert_task:
                alerter._alert_task.cancel()
                try:
                    await alerter._alert_task
                except asyncio.CancelledError:
                    pass
    finally:
        ta_module._BETWEEN_CYCLES_PAUSE_SECONDS = original_pause

    assert cycle_count[0] >= 2, "Alert should have cycled at least twice"


@pytest.mark.asyncio
async def test_cancel_sends_safe_confirmation(alerter):
    """cancel_alert must send a 'baby is safe' message to Telegram."""
    messages = []

    async def capture(text, **kwargs):
        messages.append(text)
        return True

    with patch.object(alerter, "_send_message", side_effect=capture):
        alerter._alerting = True
        await alerter.cancel_alert()

    assert any("TUDO BEM" in m or "segura" in m for m in messages), \
        "Expected safety confirmation message"


# ---------------------------------------------------------------------------
# Retry / rate limiting
# ---------------------------------------------------------------------------

def _make_response_ctx(json_data: dict) -> MagicMock:
    """
    Build a sync context manager mock for aiohttp session.post().

    aiohttp's session.post() is used as `async with session.post(url) as resp:`.
    The call is NOT awaited — it returns a context manager synchronously.
    __aenter__ is then awaited by the `async with` machinery.
    """
    resp = AsyncMock()
    resp.json.return_value = json_data
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_send_message_retries_on_429(alerter):
    """Should retry transparently when Telegram returns 429 Too Many Requests."""
    call_count = [0]
    responses = [
        {"ok": False, "error_code": 429, "description": "Too Many Requests", "parameters": {"retry_after": 0}},
        {"ok": True},
    ]

    def side_effect(*args, **kwargs):
        data = responses[min(call_count[0], 1)]
        call_count[0] += 1
        return _make_response_ctx(data)

    alerter._session.post = MagicMock(side_effect=side_effect)
    result = await alerter._send_message("test message")

    assert result is True
    assert call_count[0] == 2
    assert alerter.total_messages_sent == 1


@pytest.mark.asyncio
async def test_send_message_returns_false_after_max_retries(alerter):
    """Should return False without raising when all retry attempts fail."""
    alerter._session.post = MagicMock(
        return_value=_make_response_ctx({"ok": False, "error_code": 500, "description": "Internal error"})
    )
    result = await alerter._send_message("test", max_retries=2)

    assert result is False
    assert alerter.total_messages_sent == 0


@pytest.mark.asyncio
async def test_send_message_handles_network_error(alerter):
    """Should return False when a network error occurs, without raising."""
    import aiohttp

    alerter._session.post = MagicMock(side_effect=aiohttp.ClientConnectionError("unreachable"))
    result = await alerter._send_message("test", max_retries=1)

    assert result is False


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_message_fails_gracefully_without_session():
    """_send_message should return False (not raise) if session is None."""
    alerter = TelegramAlerter(token="t", chat_id="c")
    # _session is None by default
    result = await alerter._send_message("test")
    assert result is False


@pytest.mark.asyncio
async def test_heartbeat_lost_message_includes_elapsed(alerter):
    """send_heartbeat_lost should mention elapsed time in the message."""
    sent = []

    async def capture(text, **kwargs):
        sent.append(text)
        return True

    with patch.object(alerter, "_send_message", side_effect=capture):
        await alerter.send_heartbeat_lost(elapsed_seconds=42.0)

    assert any("42" in m for m in sent), "Elapsed seconds should appear in message"
