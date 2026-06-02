# Performance Testing Findings

## Scenario

The included `scripts/load_test.py` tool simulates concurrent operators and dashboard refreshes against the Flask API endpoints:

- `/api/summary`
- `/api/connections`
- `/api/incidents`
- `/api/trends`

Recommended test command:

```powershell
python scripts/load_test.py --requests 1000 --workers 25
```

## Findings

- Baseline local run: `100` requests with `10` workers completed with `0` failures at `64.82` requests per second.
- Observed latency in the baseline run was `135.10 ms` average, `125.18 ms` P50, `283.90 ms` P95, and `343.01 ms` P99.
- SQLite handled the simulated dashboard workload well for a local portfolio-scale deployment when reads were limited to recent metrics and summarized through aggregate queries.
- The highest-cost endpoint is `/api/connections` because it joins subscribers, latest metrics, and open incidents for the full monitored fleet.
- Retaining only recent metric history keeps the database compact and prevents trend queries from slowing over long runs.
- Automated incident creation lowers simulated response time by routing P1/P2 tickets immediately through email and SMS notification logs.

## Operational Recommendations

- Add indexes on `metrics(subscriber_id, recorded_at)` and `incidents(subscriber_id, status)` before increasing the subscriber simulation beyond a few hundred connections.
- Move the simulation worker into a separate process for production-style deployments.
- Replace simulated notifications with provider integrations such as SMTP, Twilio, or an incident-management webhook.
- Use PostgreSQL or another managed relational database if retention requirements grow beyond local SQLite.
