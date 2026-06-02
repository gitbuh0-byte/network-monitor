from __future__ import annotations

import argparse
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


ENDPOINTS = ["/api/summary", "/api/connections", "/api/incidents", "/api/trends"]


def fetch(base_url: str, path: str) -> tuple[float, bool]:
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(f"{base_url}{path}", timeout=8) as response:
            response.read()
            ok = 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError):
        ok = False
    return (time.perf_counter() - start) * 1000, ok


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((percent / 100) * (len(ordered) - 1)))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load test the ISP monitoring dashboard APIs.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()

    started = time.perf_counter()
    latencies: list[float] = []
    failures = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(fetch, args.base_url.rstrip("/"), ENDPOINTS[index % len(ENDPOINTS)])
            for index in range(args.requests)
        ]
        for future in as_completed(futures):
            latency, ok = future.result()
            latencies.append(latency)
            failures += 0 if ok else 1

    elapsed = time.perf_counter() - started
    throughput = args.requests / elapsed if elapsed else 0

    print("Load test complete")
    print(f"Requests: {args.requests}")
    print(f"Workers: {args.workers}")
    print(f"Failures: {failures}")
    print(f"Throughput: {throughput:.2f} req/sec")
    print(f"Average latency: {statistics.mean(latencies):.2f} ms")
    print(f"P50 latency: {percentile(latencies, 50):.2f} ms")
    print(f"P95 latency: {percentile(latencies, 95):.2f} ms")
    print(f"P99 latency: {percentile(latencies, 99):.2f} ms")


if __name__ == "__main__":
    main()
