# Network Monitoring Dashboard for ISP Simulation

Personal Project | GitHub: `gitbuh0-byte/network-monitor` | 2025

A real-time ISP operations dashboard built with Python, Flask, SQLite, and Chart.js. It simulates subscriber service health for 50+ user connections, tracks uptime, latency, packet loss, bandwidth utilization, and automatically creates incidents and tickets when service quality falls below operational thresholds.

## Features

- Simulates 60 ISP subscriber connections across fiber, cable, fixed wireless, and DSL service tiers.
- Tracks live uptime, latency, packet loss, bandwidth utilization, and downtime trends.
- Creates alert incidents and support tickets automatically when thresholds are breached.
- Logs simulated email and SMS notifications for high-priority service issues.
- Displays real-time charts using Chart.js with polling APIs.
- Includes a lightweight performance test script for high-load API scenarios.

## Quick Start

```powershell
cd network-monitor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Project Structure

```text
network-monitor/
  app.py
  requirements.txt
  data/
  docs/
    performance-findings.md
  scripts/
    load_test.py
  static/
    styles.css
    dashboard.js
  templates/
    dashboard.html
```

## Operational Thresholds

| Metric | Warning | Critical |
| --- | ---: | ---: |
| Latency | 120 ms | 180 ms |
| Packet loss | 2.5% | 5% |
| Uptime | 98.5% | 96% |
| Bandwidth utilization | 85% | 95% |

## Performance Testing

Run the included load test while the Flask app is running:

```powershell
python scripts/load_test.py --requests 1000 --workers 25
```

The script exercises the dashboard API endpoints concurrently and prints latency percentiles, request throughput, and error counts.
