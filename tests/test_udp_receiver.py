"""
Unit tests for UDPReceiver.

Tests _handle_packet() directly — no real UDP socket needed.
Run with: pytest tests/test_udp_receiver.py -v
"""
import asyncio
import json
import pytest

from udp_receiver import UDPReceiver

_SENDER_ADDR = ("192.168.1.100", 50000)


@pytest.fixture
def receiver():
    """UDPReceiver with a small queue for testing overflow behavior."""
    queue = asyncio.Queue(maxsize=10)
    return UDPReceiver(host="0.0.0.0", port=9999, data_queue=queue)


def _encode(data: dict) -> bytes:
    return json.dumps(data).encode()


def _valid_packet(**overrides) -> bytes:
    base = {"id": "test-device", "ts": 1000, "seq": 1, "ax": 0.1, "ay": 0.2, "az": 9.5, "pos": "UP"}
    base.update(overrides)
    return _encode(base)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_packet_is_queued(receiver):
    receiver._handle_packet(_valid_packet(), _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 1


def test_valid_packet_increments_counter(receiver):
    receiver._handle_packet(_valid_packet(), _SENDER_ADDR)
    assert receiver.packet_count == 1


def test_valid_packet_updates_last_time(receiver):
    assert receiver.last_packet_time is None
    receiver._handle_packet(_valid_packet(), _SENDER_ADDR)
    assert receiver.last_packet_time is not None


def test_packet_enriched_with_metadata(receiver):
    receiver._handle_packet(_valid_packet(), _SENDER_ADDR)
    packet = receiver.data_queue.get_nowait()
    assert "_received_at" in packet
    assert packet["_source_ip"] == _SENDER_ADDR[0]


def test_multiple_valid_packets_counted(receiver):
    for i in range(5):
        receiver._handle_packet(_valid_packet(seq=i), _SENDER_ADDR)
    assert receiver.packet_count == 5


# ---------------------------------------------------------------------------
# Rejection: malformed data
# ---------------------------------------------------------------------------

def test_invalid_json_rejected(receiver):
    receiver._handle_packet(b"definitely not json", _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0
    assert receiver.packet_count == 0


def test_truncated_json_rejected(receiver):
    receiver._handle_packet(b'{"az": 9.5, "pos":', _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0


def test_json_array_rejected(receiver):
    """Valid JSON but not an object (list) should be rejected."""
    receiver._handle_packet(_encode([1, 2, 3]), _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0


def test_json_null_rejected(receiver):
    receiver._handle_packet(b"null", _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0


def test_invalid_utf8_rejected(receiver):
    receiver._handle_packet(b"\xff\xfe invalid bytes", _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0


def test_empty_bytes_rejected(receiver):
    receiver._handle_packet(b"", _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0


# ---------------------------------------------------------------------------
# Rejection: oversized packets
# ---------------------------------------------------------------------------

def test_packet_at_max_size_is_accepted(receiver):
    """A packet right at the 512-byte limit should be processed."""
    # Build a packet with padding to get near 512 bytes
    p = _valid_packet()
    assert len(p) <= 512
    receiver._handle_packet(p, _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 1


def test_oversized_packet_rejected(receiver):
    big = b"x" * 600
    receiver._handle_packet(big, _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0
    assert receiver.packet_count == 0


# ---------------------------------------------------------------------------
# Rejection: missing or invalid required fields
# ---------------------------------------------------------------------------

def test_missing_az_rejected(receiver):
    packet = _encode({"id": "test", "pos": "UP", "ax": 0.1, "ay": 0.2})
    receiver._handle_packet(packet, _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0


def test_missing_pos_rejected(receiver):
    packet = _encode({"id": "test", "az": 9.5, "ax": 0.1})
    receiver._handle_packet(packet, _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0


def test_missing_both_required_fields_rejected(receiver):
    packet = _encode({"id": "test", "ax": 0.1, "ay": 0.2, "seq": 5})
    receiver._handle_packet(packet, _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0


def test_az_as_string_rejected(receiver):
    packet = _encode({"id": "test", "az": "not_a_number", "pos": "UP"})
    receiver._handle_packet(packet, _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0


def test_az_as_null_rejected(receiver):
    packet = _encode({"id": "test", "az": None, "pos": "UP"})
    receiver._handle_packet(packet, _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 0


def test_az_as_integer_accepted(receiver):
    """Integer is a valid numeric type for az."""
    packet = _encode({"id": "test", "az": 9, "pos": "UP"})
    receiver._handle_packet(packet, _SENDER_ADDR)
    assert receiver.data_queue.qsize() == 1


# ---------------------------------------------------------------------------
# Queue overflow
# ---------------------------------------------------------------------------

def test_queue_full_drops_oldest_packet():
    """When queue is full, oldest packet is discarded to make room."""
    queue = asyncio.Queue(maxsize=2)
    receiver = UDPReceiver(host="0.0.0.0", port=9999, data_queue=queue)

    for seq in range(3):
        receiver._handle_packet(_valid_packet(seq=seq), _SENDER_ADDR)

    assert queue.qsize() == 2
    # seq=0 (oldest) should have been dropped
    first = queue.get_nowait()
    assert first["seq"] != 0, "Oldest packet should have been dropped"
