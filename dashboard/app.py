"""
BabyGuard Dashboard — Monitoramento Visual em Tempo Real.

Roda com: streamlit run dashboard/app.py
"""
import streamlit as st
import sqlite3
import time
import json
import socket
import threading
from datetime import datetime, timedelta
from pathlib import Path

import plotly.graph_objects as go
import plotly.express as px

# Configuração da página
st.set_page_config(
    page_title="BabyGuard Monitor",
    page_icon="👶",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_PATH = Path("data/babyguard.db")


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_recent_positions(minutes=30):
    if not DB_PATH.exists():
        return []
    conn = get_db_connection()
    cutoff = time.time() - (minutes * 60)
    rows = conn.execute(
        "SELECT * FROM position_log WHERE timestamp > ? ORDER BY timestamp DESC LIMIT 500",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_alerts(hours=24):
    if not DB_PATH.exists():
        return []
    conn = get_db_connection()
    cutoff = time.time() - (hours * 3600)
    rows = conn.execute(
        "SELECT * FROM alert_log WHERE timestamp > ? ORDER BY timestamp DESC",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# === HEADER ===
st.title("👶 BabyGuard Monitor")
st.caption("Sistema de Monitoramento de Posição do Bebê")

# === MÉTRICAS PRINCIPAIS ===
col1, col2, col3, col4 = st.columns(4)

positions = get_recent_positions(minutes=5)
alerts = get_recent_alerts(hours=24)

if positions:
    latest = positions[0]
    current_pos = latest["position"]
    current_az = latest["az"]

    # Status atual
    with col1:
        if current_pos == "UP":
            st.metric("Status Atual", "SEGURO 🟢", "Barriga para cima")
        elif current_pos == "DOWN":
            st.metric("Status Atual", "PERIGO 🔴", "Barriga para baixo!")
        else:
            st.metric("Status Atual", "ATENÇÃO 🟡", "De lado")

    with col2:
        st.metric("Eixo Z", f"{current_az:+.1f} m/s²")

    with col3:
        st.metric("Alertas (24h)", len(alerts))

    with col4:
        last_time = datetime.fromtimestamp(latest["timestamp"])
        elapsed = datetime.now() - last_time
        st.metric("Última Leitura", f"{elapsed.seconds}s atrás")

else:
    st.warning("Sem dados recentes. Verifique se o servidor e o relógio estão ligados.")

# === GRÁFICO DE ACELERAÇÃO Z ===
st.subheader("Aceleração Eixo Z (últimos 30 min)")

positions_30 = get_recent_positions(minutes=30)
if positions_30:
    times = [datetime.fromtimestamp(p["timestamp"]) for p in reversed(positions_30)]
    az_values = [p["az"] for p in reversed(positions_30)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=times, y=az_values,
        mode="lines",
        name="Eixo Z",
        line=dict(color="#2196F3", width=2),
    ))

    # Linhas de threshold
    fig.add_hline(y=6.0, line_dash="dash", line_color="green",
                  annotation_text="Limite SEGURO")
    fig.add_hline(y=-6.0, line_dash="dash", line_color="red",
                  annotation_text="Limite PERIGO")
    fig.add_hline(y=0, line_dash="dot", line_color="gray")

    # Zonas coloridas
    fig.add_hrect(y0=6.0, y1=12, fillcolor="green", opacity=0.1)
    fig.add_hrect(y0=-12, y1=-6.0, fillcolor="red", opacity=0.1)

    fig.update_layout(
        yaxis_title="Aceleração Z (m/s²)",
        yaxis_range=[-12, 12],
        height=350,
        margin=dict(l=0, r=0, t=10, b=0),
    )

    st.plotly_chart(fig, use_container_width=True)

# === HISTÓRICO DE ALERTAS ===
st.subheader("Histórico de Alertas (24h)")

if alerts:
    for alert in alerts[:20]:  # Últimos 20 alertas
        alert_time = datetime.fromtimestamp(alert["timestamp"])
        alert_type = alert["alert_type"]
        duration = alert.get("duration_seconds", 0)

        if alert_type == "FACE_DOWN_ALERT":
            st.error(
                f"🔴 **{alert_time.strftime('%H:%M:%S')}** — "
                f"Bebê de barriga para baixo por {duration:.0f}s"
            )
        elif alert_type == "RETURNED_SAFE":
            st.success(
                f"🟢 **{alert_time.strftime('%H:%M:%S')}** — "
                f"Bebê voltou à posição segura"
            )
else:
    st.info("Nenhum alerta nas últimas 24 horas. Tudo tranquilo! 😊")

# Auto-refresh a cada 2 segundos
st.markdown(
    """
    <script>
        setTimeout(function() { window.location.reload(); }, 2000);
    </script>
    """,
    unsafe_allow_html=True,
)