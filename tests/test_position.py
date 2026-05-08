"""
Unit tests for PositionDetector — the core safety logic of BabyGuard.

These tests validate:
- Position classification (UP / DOWN / SIDE)
- Moving average smoothing
- State machine transitions (OFFLINE → SAFE → COUNTING → ALERT → SAFE)
- Alert timing accuracy
- Edge cases: missing fields, noisy signal, rapid transitions
"""
import asyncio
import pytest
from unittest.mock import AsyncMock

from position_detector import PositionDetector, Position, SystemState


# ---------------------------------------------------------------------------
# Position classification
# ---------------------------------------------------------------------------

class TestPositionClassification:
    """Verifies that az values map to the correct position labels."""

    def setup_method(self):
        self.detector = PositionDetector(alert_threshold_seconds=5.0)

    @pytest.mark.asyncio
    async def test_face_up_detected(self):
        for _ in range(10):
            await self.detector.process_reading({"az": 9.5})
        assert self.detector.status.position == Position.FACE_UP

    @pytest.mark.asyncio
    async def test_face_down_detected(self):
        for _ in range(10):
            await self.detector.process_reading({"az": -9.5})
        assert self.detector.status.position == Position.FACE_DOWN

    @pytest.mark.asyncio
    async def test_side_detected(self):
        for _ in range(10):
            await self.detector.process_reading({"az": 0.5})
        assert self.detector.status.position == Position.SIDE

    @pytest.mark.asyncio
    async def test_threshold_boundary_up(self):
        """az == 6.01 should be FACE_UP."""
        for _ in range(10):
            await self.detector.process_reading({"az": 6.01})
        assert self.detector.status.position == Position.FACE_UP

    @pytest.mark.asyncio
    async def test_threshold_boundary_down(self):
        """az == -6.01 should be FACE_DOWN."""
        for _ in range(10):
            await self.detector.process_reading({"az": -6.01})
        assert self.detector.status.position == Position.FACE_DOWN

    @pytest.mark.asyncio
    async def test_threshold_boundary_side(self):
        """az == 5.99 should be SIDE (between thresholds)."""
        for _ in range(10):
            await self.detector.process_reading({"az": 5.99})
        assert self.detector.status.position == Position.SIDE


# ---------------------------------------------------------------------------
# Alert system
# ---------------------------------------------------------------------------

class TestAlertSystem:
    """Verifies alert triggers and cancellations."""

    @pytest.mark.asyncio
    async def test_alert_triggers_after_threshold(self):
        """Alert fires when face down longer than threshold."""
        alert_mock = AsyncMock()
        detector = PositionDetector(
            alert_threshold_seconds=0.3,
            on_alert=alert_mock,
        )

        for _ in range(15):
            await detector.process_reading({"az": -9.5})
            await asyncio.sleep(0.03)

        await asyncio.sleep(0.35)
        await detector.process_reading({"az": -9.5})

        alert_mock.assert_called_once()
        assert detector.status.state == SystemState.ALERT

    @pytest.mark.asyncio
    async def test_no_alert_before_threshold(self):
        """No alert if face down time never exceeds threshold."""
        alert_mock = AsyncMock()
        detector = PositionDetector(
            alert_threshold_seconds=5.0,
            on_alert=alert_mock,
        )

        for _ in range(10):
            await detector.process_reading({"az": -9.5})

        alert_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_alert_when_returns_to_safe(self):
        """Returning to safe position before threshold cancels the countdown."""
        alert_mock = AsyncMock()
        detector = PositionDetector(
            alert_threshold_seconds=5.0,
            on_alert=alert_mock,
        )

        for _ in range(10):
            await detector.process_reading({"az": -9.5})

        for _ in range(15):
            await detector.process_reading({"az": 9.5})

        alert_mock.assert_not_called()
        assert detector.status.state == SystemState.SAFE

    @pytest.mark.asyncio
    async def test_safe_callback_on_recovery(self):
        """on_safe is called when baby returns to safe position after alert."""
        safe_mock = AsyncMock()
        detector = PositionDetector(
            alert_threshold_seconds=0.1,
            on_safe=safe_mock,
        )

        for _ in range(15):
            await detector.process_reading({"az": -9.5})
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.2)
        await detector.process_reading({"az": -9.5})

        for _ in range(15):
            await detector.process_reading({"az": 9.5})

        safe_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_alert_fires_exactly_once_per_episode(self):
        """Continuous face-down readings after threshold do not re-trigger."""
        alert_mock = AsyncMock()
        detector = PositionDetector(
            alert_threshold_seconds=0.1,
            on_alert=alert_mock,
        )

        for _ in range(10):
            await detector.process_reading({"az": -9.5})
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.2)
        # Keep sending face-down — should NOT re-trigger
        for _ in range(30):
            await detector.process_reading({"az": -9.5})

        alert_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_second_episode_triggers_new_alert(self):
        """After returning safe, a second face-down episode fires a new alert."""
        alert_mock = AsyncMock()
        safe_mock = AsyncMock()
        # smoothing_window=1 ensures the timer starts on the very first reading,
        # without requiring 10 readings to overcome the previous buffer state.
        detector = PositionDetector(
            alert_threshold_seconds=0.1,
            smoothing_window=1,
            on_alert=alert_mock,
            on_safe=safe_mock,
        )

        # First episode
        for _ in range(5):
            await detector.process_reading({"az": -9.5})
            await asyncio.sleep(0.03)
        await asyncio.sleep(0.15)
        await detector.process_reading({"az": -9.5})
        assert alert_mock.call_count == 1

        # Return safe
        for _ in range(5):
            await detector.process_reading({"az": 9.5})
        safe_mock.assert_called_once()

        # Second episode
        for _ in range(5):
            await detector.process_reading({"az": -9.5})
            await asyncio.sleep(0.03)
        await asyncio.sleep(0.15)
        await detector.process_reading({"az": -9.5})
        assert alert_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_state_is_counting_during_countdown(self):
        """State should be COUNTING when face down but below threshold."""
        detector = PositionDetector(alert_threshold_seconds=5.0)

        for _ in range(10):
            await detector.process_reading({"az": -9.5})

        assert detector.status.state == SystemState.COUNTING

    @pytest.mark.asyncio
    async def test_face_down_seconds_increases(self):
        """face_down_seconds increases while baby is face down."""
        detector = PositionDetector(alert_threshold_seconds=5.0)

        await detector.process_reading({"az": -9.5})
        await asyncio.sleep(0.1)
        await detector.process_reading({"az": -9.5})

        assert detector.face_down_seconds > 0.05

    @pytest.mark.asyncio
    async def test_face_down_seconds_resets_on_safe(self):
        """face_down_seconds resets to 0 when baby returns to safe position."""
        detector = PositionDetector(alert_threshold_seconds=5.0, smoothing_window=1)

        await detector.process_reading({"az": -9.5})
        await asyncio.sleep(0.05)  # let time pass so face_down_seconds > 0
        await detector.process_reading({"az": -9.5})

        assert detector.face_down_seconds > 0.0

        for _ in range(5):
            await detector.process_reading({"az": 9.5})

        assert detector.face_down_seconds == 0.0


# ---------------------------------------------------------------------------
# Signal smoothing
# ---------------------------------------------------------------------------

class TestSmoothing:
    """Verifies that the moving average filters out noise."""

    @pytest.mark.asyncio
    async def test_noise_doesnt_trigger_false_alarm(self):
        """Occasional spikes in a stable signal should not trigger an alert."""
        alert_mock = AsyncMock()
        detector = PositionDetector(
            alert_threshold_seconds=5.0,
            on_alert=alert_mock,
        )

        # 90% face-up, 10% noise spikes face-down
        for i in range(50):
            az = 9.5 if i % 10 != 0 else -9.5
            await detector.process_reading({"az": az})

        alert_mock.assert_not_called()
        assert detector.status.position == Position.FACE_UP

    @pytest.mark.asyncio
    async def test_smoothed_az_approaches_real_value(self):
        """After enough readings, smoothed_az should be close to the raw value."""
        detector = PositionDetector()

        for _ in range(20):
            await detector.process_reading({"az": 9.5})

        assert abs(detector.status.smoothed_az - 9.5) < 0.5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Verifies graceful handling of unexpected inputs."""

    @pytest.mark.asyncio
    async def test_missing_az_uses_default_zero(self):
        """Packet without 'az' should default to 0.0 without raising."""
        detector = PositionDetector()
        await detector.process_reading({"pos": "SIDE"})  # no crash
        assert detector.status.packets_received == 1

    @pytest.mark.asyncio
    async def test_extra_fields_are_ignored(self):
        """Extra packet fields should not cause errors."""
        detector = PositionDetector()
        await detector.process_reading({
            "az": 9.5, "pos": "UP", "battery": 85, "unknown_field": True
        })
        assert detector.status.position == Position.FACE_UP

    @pytest.mark.asyncio
    async def test_initial_state_is_offline(self):
        """Before any readings, state should be OFFLINE."""
        detector = PositionDetector()
        assert detector.status.state == SystemState.OFFLINE

    @pytest.mark.asyncio
    async def test_packet_counter_increments(self):
        detector = PositionDetector()
        for i in range(5):
            await detector.process_reading({"az": 9.5})
        assert detector.status.packets_received == 5
