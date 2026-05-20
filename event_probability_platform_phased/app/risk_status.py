from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, text

from config import get_settings

ROOT = Path(__file__).resolve().parent.parent


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def age_seconds(value: str | datetime | None) -> float | None:
    dt = parse_dt(value)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def encode_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def pid_status(name: str, relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    if not path.exists():
        return {"name": name, "pid_file": relative_path, "running": False, "reason": "pid_file_missing"}
    raw = path.read_text(encoding="utf-8").strip()
    try:
        pid = int(raw)
    except ValueError:
        return {"name": name, "pid_file": relative_path, "running": False, "reason": "invalid_pid", "pid": raw}
    running = Path(f"/proc/{pid}").exists()
    return {"name": name, "pid_file": relative_path, "pid": pid, "running": running}


def http_status(name: str, url: str, timeout: float = 2.0) -> dict[str, Any]:
    try:
        response = httpx.get(url, timeout=timeout)
        return {
            "name": name,
            "url": url,
            "reachable": response.status_code < 500,
            "status_code": response.status_code,
        }
    except Exception as exc:
        return {"name": name, "url": url, "reachable": False, "error": str(exc)}


def db_status() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        row = conn.execute(text("""
            select
              count(*) as tick_count,
              count(distinct event_id) as unique_events,
              count(distinct source) as unique_sources,
              max(ingested_at) as latest_ingested_at
            from event_ticks
        """)).one()
    data = {key: encode_value(value) for key, value in row._mapping.items()}
    data["latest_tick_age_seconds"] = age_seconds(data.get("latest_ingested_at"))
    return data


def signal_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path.relative_to(ROOT))}
    report = json.loads(path.read_text(encoding="utf-8"))
    signals = report.get("signals", [])
    candidates = [item for item in signals if item.get("signal") == "paper_trade_candidate"]
    ages = [item.get("latest_age_seconds") for item in signals if item.get("latest_age_seconds") is not None]
    return {
        "exists": True,
        "path": str(path.relative_to(ROOT)),
        "generated_at": report.get("generated_at"),
        "report_age_seconds": age_seconds(report.get("generated_at")),
        "status": report.get("status"),
        "events_seen": report.get("events_seen"),
        "signals_count": len(signals),
        "paper_trade_candidates": len(candidates),
        "max_signal_tick_age_seconds": max(ages) if ages else None,
    }


def alerts_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path.relative_to(ROOT)), "line_count": 0}
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest = json.loads(lines[-1]) if lines else None
    return {
        "exists": True,
        "path": str(path.relative_to(ROOT)),
        "line_count": len(lines),
        "latest_alert_at": latest.get("created_at") if latest else None,
        "latest_alert_age_seconds": age_seconds(latest.get("created_at")) if latest else None,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    worker_checks = [
        pid_status("api", "pids/api.pid"),
        pid_status("dashboard", "pids/dashboard.pid"),
        pid_status("ingest_odds", "pids/ingest_odds.pid"),
        pid_status("live_signal_monitor", "pids/live_signal_monitor.pid"),
    ]
    service_checks = [
        http_status("api_health", f"http://127.0.0.1:{args.api_port}/health"),
        http_status("dashboard", f"http://127.0.0.1:{args.dashboard_port}"),
    ]
    db = db_status()
    signals = signal_status(ROOT / "data" / "reports" / "live_hedge_signals.json")
    alerts = alerts_status(ROOT / "data" / "alerts" / "hedge_signal_alerts.jsonl")

    def add_check(name: str, ok: bool, severity: str, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "severity": severity, "detail": detail})

    for worker in worker_checks:
        severity = "block" if worker["name"] in {"ingest_odds", "live_signal_monitor"} else "warn"
        add_check(f"worker_{worker['name']}", bool(worker.get("running")), severity, json.dumps(worker, ensure_ascii=False))

    for service in service_checks:
        add_check(f"service_{service['name']}", bool(service.get("reachable")), "warn", json.dumps(service, ensure_ascii=False))

    add_check("event_ticks_non_empty", int(db.get("tick_count") or 0) > 0, "block", f"tick_count={db.get('tick_count')}")
    tick_age = db.get("latest_tick_age_seconds")
    add_check(
        "event_ticks_fresh",
        tick_age is not None and tick_age <= args.max_tick_age_seconds,
        "block",
        f"latest_tick_age_seconds={tick_age}",
    )
    add_check("signals_file_exists", bool(signals.get("exists")), "block", json.dumps(signals, ensure_ascii=False))
    signal_age = signals.get("report_age_seconds")
    add_check(
        "signals_report_fresh",
        signal_age is not None and signal_age <= args.max_signal_age_seconds,
        "block",
        f"report_age_seconds={signal_age}",
    )
    add_check(
        "signals_have_rows",
        int(signals.get("signals_count") or 0) > 0,
        "warn",
        f"signals_count={signals.get('signals_count')}",
    )

    blocked = [check for check in checks if not check["ok"] and check["severity"] == "block"]
    warnings = [check for check in checks if not check["ok"] and check["severity"] == "warn"]
    status = "ok"
    if warnings:
        status = "warn"
    if blocked:
        status = "blocked"

    return {
        "status": status,
        "generated_at": utc_now(),
        "thresholds": {
            "max_tick_age_seconds": args.max_tick_age_seconds,
            "max_signal_age_seconds": args.max_signal_age_seconds,
        },
        "database": db,
        "signals": signals,
        "alerts": alerts,
        "workers": worker_checks,
        "services": service_checks,
        "checks": checks,
        "blocked_checks": blocked,
        "warning_checks": warnings,
        "mode": "paper_trade_only",
        "auto_trading_enabled": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate realtime platform risk status.")
    parser.add_argument("--json-out", default="data/reports/risk_status.json")
    parser.add_argument("--api-port", type=int, default=int(os.getenv("API_PORT", "8000")))
    parser.add_argument("--dashboard-port", type=int, default=int(os.getenv("DASHBOARD_PORT", "8501")))
    parser.add_argument("--max-tick-age-seconds", type=float, default=float(os.getenv("RISK_MAX_TICK_AGE_SECONDS", "30")))
    parser.add_argument("--max-signal-age-seconds", type=float, default=float(os.getenv("RISK_MAX_SIGNAL_AGE_SECONDS", "20")))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_report(args)
    path = Path(args.json_out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_blocked and report["status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
