"""
Integration tests — full monitoring cycle without real hardware.

These tests exercise the complete path from raw accelerometer readings
through position detection to alert callbacks.

Scenario tested:
    UP (stable) → face down > threshold → ALERT fires → UP again → SAFE
"""
import asyncio
import pytest
from unittest.mock import AsyncMock

from position_detector import PositionDetector, SystemState, Position


async def _send_readings(detector: PositionDetector, az: float, count: int, delay: float = 0.0):
    """Helper: send count readings of az to detector with optional per-reading delay."""
    for _ in range(count):
        await detector.process_reading({"az": az, "pos": "DOWN" if az < 0 else "UP"})
        if delay:
            await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# Core cycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_cycle_up_down_alert_safe():
    """
    Canonical safety cycle:
      1. Stable face-up → SAFE
      2. Face-down longer than threshold → ALERT
      3. Returns face-up → SAFE and alert cancelled

    Uses smoothing_window=1 so the state machine reacts on the very first reading
    without needing to overcome a full 10-sample buffer from the previous phase.
    """
    alert_mock = AsyncMock()
    safe_mock = AsyncMock()

    detector = PositionDetector(
        alert_threshold_seconds=0.2,
        smoothing_window=1,
        on_alert=alert_mock,
        on_safe=safe_mock,
    )

    # Phase 1 — face up
    await _send_readings(detector, az=9.5, count=5)
    assert detector.status.position == Position.FACE_UP
    assert detector.status.state == SystemState.SAFE

    # Phase 2 — face down, exceed threshold
    await _send_readings(detector, az=-9.5, count=5, delay=0.05)
    await asyncio.sleep(0.25)
    await detector.process_reading({"az": -9.5})

    assert detector.status.state == SystemState.ALERT
    alert_mock.assert_called_once()
    safe_mock.assert_not_called()

    # Phase 3 — returns to safe
    await _send_readings(detector, az=9.5, count=5)

    assert detector.status.state == SystemState.SAFE
    safe_mock.assert_called_once()


@pytest.mark.asyncio
async def test_brief_face_down_does_not_alert():
    """If baby flips back before threshold, no alert is sent."""
    alert_mock = AsyncMock()

    detector = PositionDetector(
        alert_threshold_seconds=5.0,
        on_alert=alert_mock,
    )

    await _send_readings(detector, az=-9.5, count=10)   # face down
    await _send_readings(detector, az=9.5, count=15)    # back to safe immediately

    alert_mock.assert_not_called()
    assert detector.status.state == SystemState.SAFE


@pytest.mark.asyncio
async def test_alert_fires_exactly_once_per_episode():
    """Sustained face-down after threshold triggers on_alert only once."""
    alert_mock = AsyncMock()

    detector = PositionDetector(
        alert_threshold_seconds=0.1,
        on_alert=alert_mock,
    )

    await _send_readings(detector, az=-9.5, count=10, delay=0.02)
    await asyncio.sleep(0.2)
    # Keep sending face-down — should NOT fire again
    await _send_readings(detector, az=-9.5, count=20)

    alert_mock.assert_called_once()


@pytest.mark.asyncio
async def test_multiple_episodes_fire_separate_alerts():
    """Each face-down episode (with recovery in between) fires its own alert."""
    alert_mock = AsyncMock()
    safe_mock = AsyncMock()

    # smoothing_window=1: each episode's first reading immediately changes state
    detector = PositionDetector(
        alert_threshold_seconds=0.1,
        smoothing_window=1,
        on_alert=alert_mock,
        on_safe=safe_mock,
    )

    for episode in range(3):
        # Face down — timer starts on first reading
        await _send_readings(detector, az=-9.5, count=5, delay=0.03)
        await asyncio.sleep(0.15)
        await detector.process_reading({"az": -9.5})

        # Recover — immediate transition back to SAFE
        await _send_readings(detector, az=9.5, count=5)

    assert alert_mock.call_count == 3
    assert safe_mock.call_count == 3


# ---------------------------------------------------------------------------
# Noisy signal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_intermittent_noise_does_not_alert():
    """Occasional face-down spikes in a mostly face-up signal should not alert."""
    alert_mock = AsyncMock()

    detector = PositionDetector(
        alert_threshold_seconds=0.5,
        on_alert=alert_mock,
    )

    for i in range(60):
        # 1 spike per 10 readings, rest face-up
        az = -9.5 if i % 10 == 0 else 9.5
        await detector.process_reading({"az": az})

    alert_mock.assert_not_called()


@pytest.mark.asyncio
async def test_side_position_not_treated_as_face_down():
    """SIDE position should keep detector in SAFE, not COUNTING."""
    alert_mock = AsyncMock()

    detector = PositionDetector(
        alert_threshold_seconds=0.1,
        on_alert=alert_mock,
    )

    await _send_readings(detector, az=0.0, count=20)

    assert detector.status.position == Position.SIDE
    assert detector.status.state == SystemState.SAFE
    alert_mock.assert_not_called()


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_initial_state_is_offline():
    detector = PositionDetector()
    assert detector.status.state == SystemState.OFFLINE


@pytest.mark.asyncio
async def test_first_up_reading_transitions_to_safe():
    detector = PositionDetector()
    for _ in range(10):
        await detector.process_reading({"az": 9.5})
    assert detector.status.state == SystemState.SAFE


@pytest.mark.asyncio
async def test_counting_state_during_countdown():
    detector = PositionDetector(alert_threshold_seconds=5.0)
    await _send_readings(detector, az=-9.5, count=10)
    assert detector.status.state == SystemState.COUNTING
