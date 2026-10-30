"""
Reproducible ingestion benchmark.

Compares three ingestion strategies against the same live targets:
  (a) sequential_playwright  - headless Chromium for every URL, one after another
  (b) sequential_curl_cffi   - curl_cffi Chrome TLS impersonation, one after another
  (c) concurrent_two_tier    - asyncio.gather + curl_cffi, Playwright only on HTTP 403
                               (the production path used by main.py)

Metrics per run:
  - wall time (time.perf_counter)
  - peak RSS of this Python process + all child processes (Chromium), sampled every 50 ms
  - peak RSS delta over the pre-run baseline

Usage:
    python scripts/benchmark_ingestion.py --runs 5
Results are written to benchmarks/ingestion.json.
"""
import argparse
import asyncio
import json
import logging
import platform
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curl_cffi.requests import AsyncSession  # noqa: E402

from app.services.ingestion import (  # noqa: E402
    BROWSER_HEADERS,
    fetch_with_playwright,
    ingest_single_target,
)

logging.basicConfig(level=logging.WARNING)

TARGETS = [
    {"name": "Allbirds", "url": "https://www.allbirds.com/products.json?limit=10"},
    {"name": "Red Bull Shop", "url": "https://www.redbullshopus.com/products.json?limit=10"},
    {"name": "Gymshark US", "url": "https://us.shop.gymshark.com/products.json?limit=10"},
]


class PeakRSSSampler:
    """Samples total RSS (process + children) in a background thread."""

    def __init__(self, interval: float = 0.05):
        self.interval = interval
        self.proc = psutil.Process()
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _total_rss(self) -> int:
        total = 0
        try:
            total += self.proc.memory_info().rss
            for child in self.proc.children(recursive=True):
                try:
                    total += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except psutil.NoSuchProcess:
            pass
        return total

    def _run(self):
        while not self._stop.is_set():
            self.peak = max(self.peak, self._total_rss())
            time.sleep(self.interval)

    def __enter__(self):
        self.baseline = self._total_rss()
        self.peak = self.baseline
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()


async def sequential_playwright():
    for t in TARGETS:
        await fetch_with_playwright(t["url"])


async def sequential_curl_cffi():
    async with AsyncSession(impersonate="chrome120") as session:
        for t in TARGETS:
            r = await session.get(t["url"], headers=BROWSER_HEADERS, timeout=20)
            r.raise_for_status()
            r.json()


async def concurrent_two_tier():
    results = await asyncio.gather(*(ingest_single_target(t) for t in TARGETS), return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    if errors:
        raise errors[0]


MODES = {
    "sequential_playwright": sequential_playwright,
    "sequential_curl_cffi": sequential_curl_cffi,
    "concurrent_two_tier": concurrent_two_tier,
}


def run_once(fn):
    with PeakRSSSampler() as sampler:
        t0 = time.perf_counter()
        asyncio.run(fn())
        elapsed = time.perf_counter() - t0
    return {
        "seconds": round(elapsed, 3),
        "peak_rss_mb": round(sampler.peak / 1024**2, 1),
        "peak_rss_delta_mb": round((sampler.peak - sampler.baseline) / 1024**2, 1),
    }


def summarize(runs):
    secs = sorted(r["seconds"] for r in runs)
    deltas = sorted(r["peak_rss_delta_mb"] for r in runs)
    return {
        "median_seconds": round(statistics.median(secs), 3),
        "max_seconds": secs[-1],
        "median_peak_rss_delta_mb": round(statistics.median(deltas), 1),
        "max_peak_rss_delta_mb": deltas[-1],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    # Warm-up: DNS / TLS session caches, imports
    asyncio.run(sequential_curl_cffi())

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "machine": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "cpu_logical_cores": psutil.cpu_count(logical=True),
            "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
        },
        "targets": [t["url"] for t in TARGETS],
        "runs_per_mode": args.runs,
        "modes": {},
    }

    for name, fn in MODES.items():
        runs = []
        for i in range(args.runs):
            res = run_once(fn)
            runs.append(res)
            print(f"{name:<24} run {i + 1}/{args.runs}: {res}")
        report["modes"][name] = {"runs": runs, "summary": summarize(runs)}

    base = report["modes"]["sequential_playwright"]["summary"]
    ours = report["modes"]["concurrent_two_tier"]["summary"]
    report["speedup_vs_playwright"] = round(base["median_seconds"] / ours["median_seconds"], 1)

    out_dir = Path(__file__).resolve().parent.parent / "benchmarks"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "ingestion.json"
    out_file.write_text(json.dumps(report, indent=2))

    print("\n=== SUMMARY (median of runs) ===")
    print(f"{'Mode':<24} | {'Time (s)':>9} | {'Peak RSS delta (MB)':>20}")
    for name, data in report["modes"].items():
        s = data["summary"]
        print(f"{name:<24} | {s['median_seconds']:>9} | {s['median_peak_rss_delta_mb']:>20}")
    print(f"Speedup (concurrent_two_tier vs sequential_playwright): {report['speedup_vs_playwright']}x")
    print(f"Saved -> {out_file}")


if __name__ == "__main__":
    main()
