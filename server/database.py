"""
Persistência de dados com SQLite.
Registra eventos de posição e alertas para análise posterior.
"""
import sqlite3
import time
import logging
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger("babyguard.db")

DB_PATH = Path("data/babyguard.db")


def init_db():
    """Cria o banco de dados e tabelas se não existirem."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS position_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                device_id TEXT NOT NULL,
                position TEXT NOT NULL,
                az REAL NOT NULL,
                ax REAL,
                ay REAL
            );

            CREATE TABLE IF NOT EXISTS alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                device_id TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                duration_seconds REAL,
                message TEXT
            );

            CREATE TABLE IF NOT EXISTS heartbeat_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                device_id TEXT NOT NULL,
                packets_received INTEGER,
                status TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_position_ts
                ON position_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_alert_ts
                ON alert_log(timestamp);
        """)
    logger.info(f"Banco de dados inicializado: {DB_PATH}")


@contextmanager
def _get_conn():
    """Context manager para conexão SQLite."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_position(device_id: str, position: str, az: float, ax: float = 0, ay: float = 0):
    """Registra uma leitura de posição (a cada 5 segundos para economizar espaço)."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO position_log (timestamp, device_id, position, az, ax, ay) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), device_id, position, az, ax, ay),
        )


def log_alert(device_id: str, alert_type: str, duration: float = 0, message: str = ""):
    """Registra um evento de alerta."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO alert_log (timestamp, device_id, alert_type, duration_seconds, message) "
            "VALUES (?, ?, ?, ?, ?)",
            (time.time(), device_id, alert_type, duration, message),
        )
    logger.info(f"Alerta registrado: {alert_type} ({duration:.1f}s)")


def get_recent_positions(device_id: str, minutes: int = 60) -> list[dict]:
    """Retorna posições dos últimos N minutos."""
    cutoff = time.time() - (minutes * 60)
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM position_log WHERE device_id = ? AND timestamp > ? "
            "ORDER BY timestamp DESC LIMIT 1000",
            (device_id, cutoff),
        ).fetchall()
    return [dict(row) for row in rows]


def get_recent_alerts(device_id: str, hours: int = 24) -> list[dict]:
    """Retorna alertas das últimas N horas."""
    cutoff = time.time() - (hours * 3600)
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM alert_log WHERE device_id = ? AND timestamp > ? "
            "ORDER BY timestamp DESC",
            (device_id, cutoff),
        ).fetchall()
    return [dict(row) for row in rows]