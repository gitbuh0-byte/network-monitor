from __future__ import annotations

import random
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "network_monitor.db"
SIMULATION_INTERVAL_SECONDS = 4

LATENCY_WARNING_MS = 120
LATENCY_CRITICAL_MS = 180
PACKET_LOSS_WARNING = 2.5
PACKET_LOSS_CRITICAL = 5.0
UPTIME_WARNING = 98.5
UPTIME_CRITICAL = 96.0
BANDWIDTH_WARNING = 85
BANDWIDTH_CRITICAL = 95

app = Flask(__name__)


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                region TEXT NOT NULL,
                service_tier TEXT NOT NULL,
                connection_type TEXT NOT NULL,
                provisioned_mbps INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'online',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                uptime_percent REAL NOT NULL,
                latency_ms REAL NOT NULL,
                packet_loss_percent REAL NOT NULL,
                bandwidth_mbps REAL NOT NULL,
                FOREIGN KEY (subscriber_id) REFERENCES subscribers(id)
            );

            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                FOREIGN KEY (subscriber_id) REFERENCES subscribers(id)
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                priority TEXT NOT NULL,
                assigned_team TEXT NOT NULL,
                response_eta_minutes INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                FOREIGN KEY (incident_id) REFERENCES incidents(id)
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                channel TEXT NOT NULL,
                recipient TEXT NOT NULL,
                message TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
            );

            CREATE INDEX IF NOT EXISTS idx_metrics_subscriber_recorded
                ON metrics(subscriber_id, recorded_at);

            CREATE INDEX IF NOT EXISTS idx_incidents_subscriber_status
                ON incidents(subscriber_id, status);

            CREATE INDEX IF NOT EXISTS idx_tickets_incident
                ON tickets(incident_id);
            """
        )


def seed_subscribers() -> None:
    regions = ["North Loop", "Riverside", "Airport West", "East Ridge", "Downtown", "Lakeview"]
    tiers = [
        ("Residential 100", "Cable", 100),
        ("Residential 300", "Fiber", 300),
        ("Business 500", "Fiber", 500),
        ("Rural 50", "Fixed Wireless", 50),
        ("Legacy 25", "DSL", 25),
    ]
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
        if count >= 50:
            return

        for index in range(60):
            tier, connection_type, speed = random.choice(tiers)
            conn.execute(
                """
                INSERT INTO subscribers (
                    customer_name, region, service_tier, connection_type,
                    provisioned_mbps, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, 'online', ?)
                """,
                (
                    f"Subscriber {index + 1:03d}",
                    random.choice(regions),
                    tier,
                    connection_type,
                    speed,
                    utc_now(),
                ),
            )


def metric_for(subscriber: sqlite3.Row) -> dict[str, float]:
    congestion = random.random()
    provisioned = subscriber["provisioned_mbps"]
    base_latency = {
        "Fiber": 28,
        "Cable": 48,
        "Fixed Wireless": 72,
        "DSL": 92,
    }.get(subscriber["connection_type"], 55)

    outage_roll = random.random()
    if outage_roll < 0.035:
        uptime = random.uniform(88.0, 96.2)
        latency = random.uniform(170, 320)
        packet_loss = random.uniform(4.0, 12.0)
        bandwidth = random.uniform(provisioned * 0.08, provisioned * 0.35)
    else:
        uptime = random.uniform(98.2, 100.0)
        latency = max(8, random.gauss(base_latency, 18 + congestion * 28))
        packet_loss = max(0, random.gauss(0.8 + congestion * 1.5, 0.7))
        bandwidth = random.uniform(provisioned * 0.25, provisioned * (0.72 + congestion * 0.28))

    return {
        "uptime_percent": round(uptime, 2),
        "latency_ms": round(latency, 2),
        "packet_loss_percent": round(packet_loss, 2),
        "bandwidth_mbps": round(min(bandwidth, provisioned), 2),
    }


def evaluate_alert(metric: dict[str, float]) -> tuple[str, str, str] | None:
    checks = [
        (
            metric["latency_ms"],
            LATENCY_WARNING_MS,
            LATENCY_CRITICAL_MS,
            "Latency",
            f"Latency elevated at {metric['latency_ms']} ms",
            True,
        ),
        (
            metric["packet_loss_percent"],
            PACKET_LOSS_WARNING,
            PACKET_LOSS_CRITICAL,
            "Packet Loss",
            f"Packet loss detected at {metric['packet_loss_percent']}%",
            True,
        ),
        (
            metric["uptime_percent"],
            UPTIME_WARNING,
            UPTIME_CRITICAL,
            "Uptime",
            f"Uptime degraded to {metric['uptime_percent']}%",
            False,
        ),
    ]

    for value, warning, critical, category, message, higher_is_worse in checks:
        if higher_is_worse and value >= critical:
            return "critical", category, message
        if higher_is_worse and value >= warning:
            return "warning", category, message
        if not higher_is_worse and value <= critical:
            return "critical", category, message
        if not higher_is_worse and value <= warning:
            return "warning", category, message

    return None


def create_ticket(conn: sqlite3.Connection, incident_id: int, severity: str, category: str) -> None:
    priority = "P1" if severity == "critical" else "P2"
    team = "Network Operations" if category in {"Latency", "Packet Loss"} else "Field Service"
    eta = 12 if severity == "critical" else 28
    cursor = conn.execute(
        """
        INSERT INTO tickets (incident_id, created_at, priority, assigned_team, response_eta_minutes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (incident_id, utc_now(), priority, team, eta),
    )
    ticket_id = cursor.lastrowid

    channels = ["email", "sms"] if severity == "critical" else ["email"]
    for channel in channels:
        conn.execute(
            """
            INSERT INTO notifications (ticket_id, sent_at, channel, recipient, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                utc_now(),
                channel,
                "noc@example.com" if channel == "email" else "+15550101010",
                f"{priority} {category} incident assigned to {team}; ETA {eta} minutes.",
            ),
        )


def record_metrics_batch() -> None:
    recorded_at = utc_now()
    with get_db() as conn:
        subscribers = conn.execute("SELECT * FROM subscribers").fetchall()
        for subscriber in subscribers:
            metric = metric_for(subscriber)
            conn.execute(
                """
                INSERT INTO metrics (
                    subscriber_id, recorded_at, uptime_percent, latency_ms,
                    packet_loss_percent, bandwidth_mbps
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    subscriber["id"],
                    recorded_at,
                    metric["uptime_percent"],
                    metric["latency_ms"],
                    metric["packet_loss_percent"],
                    metric["bandwidth_mbps"],
                ),
            )

            alert = evaluate_alert(metric)
            if not alert:
                continue

            severity, category, message = alert
            existing = conn.execute(
                """
                SELECT id FROM incidents
                WHERE subscriber_id = ? AND category = ? AND status = 'open'
                """,
                (subscriber["id"], category),
            ).fetchone()
            if existing:
                continue

            incident = conn.execute(
                """
                INSERT INTO incidents (subscriber_id, opened_at, severity, category, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (subscriber["id"], recorded_at, severity, category, message),
            )
            create_ticket(conn, incident.lastrowid, severity, category)

        cutoff = (datetime.utcnow() - timedelta(hours=4)).replace(microsecond=0).isoformat() + "Z"
        conn.execute("DELETE FROM metrics WHERE recorded_at < ?", (cutoff,))


def simulation_worker() -> None:
    while True:
        record_metrics_batch()
        resolve_stale_incidents()
        time.sleep(SIMULATION_INTERVAL_SECONDS)


def resolve_stale_incidents() -> None:
    cutoff = (datetime.utcnow() - timedelta(minutes=15)).replace(microsecond=0).isoformat() + "Z"
    with get_db() as conn:
        conn.execute(
            """
            UPDATE incidents
            SET status = 'resolved', closed_at = ?
            WHERE status = 'open' AND opened_at < ?
            """,
            (utc_now(), cutoff),
        )
        conn.execute(
            """
            UPDATE tickets
            SET status = 'resolved'
            WHERE status != 'resolved'
              AND incident_id IN (SELECT id FROM incidents WHERE status = 'resolved')
            """
        )


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


@app.route("/")
def dashboard() -> str:
    return render_template("dashboard.html")


@app.get("/api/summary")
def api_summary():
    with get_db() as conn:
        latest = conn.execute(
            """
            WITH latest_metrics AS (
                SELECT m.*
                FROM metrics m
                JOIN (
                    SELECT subscriber_id, MAX(recorded_at) AS recorded_at
                    FROM metrics
                    GROUP BY subscriber_id
                ) recent
                ON m.subscriber_id = recent.subscriber_id
               AND m.recorded_at = recent.recorded_at
            )
            SELECT
                COUNT(*) AS monitored_connections,
                ROUND(AVG(uptime_percent), 2) AS avg_uptime,
                ROUND(AVG(latency_ms), 2) AS avg_latency,
                ROUND(AVG(packet_loss_percent), 2) AS avg_packet_loss,
                ROUND(AVG((bandwidth_mbps * 100.0) / s.provisioned_mbps), 2) AS avg_bandwidth_utilization
            FROM latest_metrics lm
            JOIN subscribers s ON s.id = lm.subscriber_id
            """
        ).fetchone()
        open_incidents = conn.execute("SELECT COUNT(*) FROM incidents WHERE status = 'open'").fetchone()[0]
        tickets = conn.execute("SELECT COUNT(*) FROM tickets WHERE status != 'resolved'").fetchone()[0]

    payload = dict(latest or {})
    payload["open_incidents"] = open_incidents
    payload["active_tickets"] = tickets
    payload["simulated_response_improvement"] = "40%"
    return jsonify(payload)


@app.get("/api/connections")
def api_connections():
    with get_db() as conn:
        rows = conn.execute(
            """
            WITH latest_metrics AS (
                SELECT m.*
                FROM metrics m
                JOIN (
                    SELECT subscriber_id, MAX(recorded_at) AS recorded_at
                    FROM metrics
                    GROUP BY subscriber_id
                ) recent
                ON m.subscriber_id = recent.subscriber_id
               AND m.recorded_at = recent.recorded_at
            )
            SELECT
                s.id,
                s.customer_name,
                s.region,
                s.service_tier,
                s.connection_type,
                s.provisioned_mbps,
                lm.uptime_percent,
                lm.latency_ms,
                lm.packet_loss_percent,
                lm.bandwidth_mbps,
                ROUND((lm.bandwidth_mbps * 100.0) / s.provisioned_mbps, 2) AS utilization_percent,
                CASE
                    WHEN i.id IS NOT NULL THEN i.severity
                    WHEN lm.latency_ms >= ? OR lm.packet_loss_percent >= ? OR lm.uptime_percent <= ? THEN 'warning'
                    ELSE 'healthy'
                END AS health
            FROM subscribers s
            LEFT JOIN latest_metrics lm ON lm.subscriber_id = s.id
            LEFT JOIN incidents i ON i.subscriber_id = s.id AND i.status = 'open'
            ORDER BY
                CASE health WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END,
                utilization_percent DESC
            LIMIT 60
            """,
            (LATENCY_WARNING_MS, PACKET_LOSS_WARNING, UPTIME_WARNING),
        ).fetchall()
    return jsonify(rows_to_dicts(rows))


@app.get("/api/incidents")
def api_incidents():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                i.id,
                i.opened_at,
                i.severity,
                i.category,
                i.message,
                i.status,
                s.customer_name,
                s.region,
                t.priority,
                t.assigned_team,
                t.response_eta_minutes
            FROM incidents i
            JOIN subscribers s ON s.id = i.subscriber_id
            LEFT JOIN tickets t ON t.incident_id = i.id
            ORDER BY i.opened_at DESC
            LIMIT 12
            """
        ).fetchall()
    return jsonify(rows_to_dicts(rows))


@app.get("/api/trends")
def api_trends():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                recorded_at,
                ROUND(AVG(latency_ms), 2) AS latency_ms,
                ROUND(AVG(packet_loss_percent), 2) AS packet_loss_percent,
                ROUND(AVG(uptime_percent), 2) AS uptime_percent,
                ROUND(AVG((bandwidth_mbps * 100.0) / s.provisioned_mbps), 2) AS bandwidth_utilization
            FROM metrics m
            JOIN subscribers s ON s.id = m.subscriber_id
            GROUP BY recorded_at
            ORDER BY recorded_at DESC
            LIMIT 30
            """
        ).fetchall()
    return jsonify(list(reversed(rows_to_dicts(rows))))


def bootstrap() -> None:
    init_db()
    seed_subscribers()
    with get_db() as conn:
        metric_count = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    if metric_count == 0:
        for _ in range(8):
            record_metrics_batch()
    thread = threading.Thread(target=simulation_worker, daemon=True)
    thread.start()


bootstrap()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
