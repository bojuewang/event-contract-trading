from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "phase_manifest.json"
STATE_PATH = ROOT / ".phase_state.json"
LOG_DIR = ROOT / "logs"

VALID_STATUSES = {"pending", "running", "completed", "confirmed", "failed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_manifest() -> list[dict[str, Any]]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        phases = json.load(f)
    ids = [p["id"] for p in phases]
    if len(ids) != len(set(ids)):
        raise RuntimeError("phase_manifest.json has duplicate phase ids")
    return phases


def load_state(phases: list[dict[str, Any]]) -> dict[str, Any]:
    if STATE_PATH.exists():
        with STATE_PATH.open("r", encoding="utf-8") as f:
            state = json.load(f)
    else:
        state = {"created_at": utc_now(), "phases": {}}
    state.setdefault("phases", {})
    for p in phases:
        rec = state["phases"].setdefault(p["id"], {})
        rec.setdefault("status", "pending")
        rec.setdefault("name", p["name"])
    return state


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(STATE_PATH)


def phase_index(phases: list[dict[str, Any]], phase_id: str) -> int:
    for i, p in enumerate(phases):
        if p["id"] == phase_id:
            return i
    raise SystemExit(f"未知阶段：{phase_id}. 先运行 python phase_runner.py list")


def print_phase_table(phases: list[dict[str, Any]], state: dict[str, Any]) -> None:
    print("\n阶段清单 / 当前状态")
    print("-" * 98)
    print(f"{'阶段':<28} {'状态':<12} {'名称':<28} {'说明'}")
    print("-" * 98)
    for p in phases:
        rec = state["phases"].get(p["id"], {})
        print(f"{p['id']:<28} {rec.get('status','pending'):<12} {p['name']:<28} {p['description']}")
    print("-" * 98)


def previous_unconfirmed(phases: list[dict[str, Any]], state: dict[str, Any], idx: int) -> list[str]:
    missing: list[str] = []
    for p in phases[:idx]:
        if state["phases"].get(p["id"], {}).get("status") != "confirmed":
            missing.append(p["id"])
    return missing


def next_runnable_phase(phases: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any] | None:
    for p in phases:
        status = state["phases"][p["id"]].get("status", "pending")
        if status != "confirmed":
            return p
    return None


def run_phase(phases: list[dict[str, Any]], state: dict[str, Any], phase_id: str, rerun: bool = False) -> None:
    idx = phase_index(phases, phase_id)
    phase = phases[idx]
    rec = state["phases"][phase_id]
    status = rec.get("status", "pending")

    missing = previous_unconfirmed(phases, state, idx)
    if missing:
        print("上一阶段尚未确认，不能继续。")
        print("请先确认：")
        for m in missing:
            mrec = state["phases"].get(m, {})
            token = mrec.get("confirmation_token")
            if token:
                print(f"  python phase_runner.py confirm {m} --token {token}")
            else:
                print(f"  先运行或完成 {m}")
        raise SystemExit(2)

    if status == "completed" and not rerun:
        token = rec.get("confirmation_token")
        print(f"阶段 {phase_id} 已执行完成，但尚未确认。")
        print(f"检查日志后执行：python phase_runner.py confirm {phase_id} --token {token}")
        raise SystemExit(2)

    if status == "confirmed" and not rerun:
        print(f"阶段 {phase_id} 已确认完成。若要重跑，使用 --rerun。")
        return

    script_path = ROOT / phase["script"]
    if not script_path.exists():
        raise SystemExit(f"找不到阶段脚本：{script_path}")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{phase_id}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    rec.update({
        "status": "running",
        "last_started_at": utc_now(),
        "last_log": str(log_path.relative_to(ROOT)),
        "confirmation_token": None,
        "last_error": None,
    })
    save_state(state)

    env = os.environ.copy()
    env["PHASE_ID"] = phase_id
    env["PROJECT_ROOT"] = str(ROOT)
    env["PYTHONUNBUFFERED"] = "1"

    print(f"\n开始执行：{phase_id} - {phase['name']}")
    print(f"日志文件：{log_path.relative_to(ROOT)}")
    print("-" * 88)

    start = time.time()
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"# {phase_id} {phase['name']}\n# started_at={utc_now()}\n\n")
        process = subprocess.Popen(
            ["bash", str(script_path)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
        returncode = process.wait()
        elapsed = time.time() - start
        log.write(f"\n# finished_at={utc_now()} returncode={returncode} elapsed_seconds={elapsed:.2f}\n")

    if returncode != 0:
        rec.update({
            "status": "failed",
            "last_finished_at": utc_now(),
            "last_returncode": returncode,
            "last_error": f"阶段脚本退出码 {returncode}",
        })
        save_state(state)
        print("-" * 88)
        print(f"阶段 {phase_id} 失败。请查看日志：{log_path.relative_to(ROOT)}")
        raise SystemExit(returncode)

    token = f"CONFIRM-{phase_id}-{secrets.token_hex(4)}"
    rec.update({
        "status": "completed",
        "last_finished_at": utc_now(),
        "last_returncode": 0,
        "confirmation_token": token,
    })
    save_state(state)

    print("-" * 88)
    print(f"阶段 {phase_id} 已执行完成，但尚未进入下一阶段。")
    print("请检查终端输出和日志，确认通过后执行：")
    print(f"  python phase_runner.py confirm {phase_id} --token {token}")
    print("确认后再执行：")
    print("  python phase_runner.py run-next")


def confirm_phase(phases: list[dict[str, Any]], state: dict[str, Any], phase_id: str, token: str) -> None:
    phase_index(phases, phase_id)
    rec = state["phases"][phase_id]
    status = rec.get("status", "pending")
    if status != "completed":
        print(f"阶段 {phase_id} 当前状态是 {status}，不能确认。必须先完成执行。")
        raise SystemExit(2)
    expected = rec.get("confirmation_token")
    if not expected or token != expected:
        print("确认 token 不匹配，确认失败。")
        print(f"当前阶段 token：{expected}")
        raise SystemExit(2)
    rec.update({
        "status": "confirmed",
        "confirmed_at": utc_now(),
        "confirmed_token": token,
    })
    save_state(state)
    print(f"阶段 {phase_id} 已确认通过。")
    nxt = next_runnable_phase(phases, state)
    if nxt:
        print(f"下一阶段：{nxt['id']} - {nxt['name']}")
        print("运行：python phase_runner.py run-next")
    else:
        print("所有阶段均已确认完成。")


def reset_phase(phases: list[dict[str, Any]], state: dict[str, Any], phase_id: str | None, all_phases: bool) -> None:
    if all_phases:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
        print("已删除 .phase_state.json。")
        return
    if not phase_id:
        raise SystemExit("请指定 --phase 或 --all")
    phase_index(phases, phase_id)
    state["phases"][phase_id] = {"status": "pending", "name": state["phases"][phase_id].get("name", phase_id)}
    save_state(state)
    print(f"已重置阶段 {phase_id}。")


def main() -> None:
    phases = load_manifest()
    state = load_state(phases)
    save_state(state)

    parser = argparse.ArgumentParser(description="阶段化执行门控器：上一阶段 confirmed 后才允许下一阶段。")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="显示阶段清单")
    sub.add_parser("status", help="显示当前状态")

    run_p = sub.add_parser("run", help="运行指定阶段")
    run_p.add_argument("phase_id")
    run_p.add_argument("--rerun", action="store_true")

    next_p = sub.add_parser("run-next", help="运行下一个未确认阶段")
    next_p.add_argument("--rerun", action="store_true")

    confirm_p = sub.add_parser("confirm", help="确认一个已完成阶段，允许进入下一阶段")
    confirm_p.add_argument("phase_id")
    confirm_p.add_argument("--token", required=True)

    reset_p = sub.add_parser("reset", help="重置阶段状态")
    reset_p.add_argument("--phase")
    reset_p.add_argument("--all", action="store_true")

    args = parser.parse_args()

    if args.cmd in {"list", "status"}:
        print_phase_table(phases, state)
    elif args.cmd == "run":
        run_phase(phases, state, args.phase_id, rerun=args.rerun)
    elif args.cmd == "run-next":
        nxt = next_runnable_phase(phases, state)
        if not nxt:
            print("所有阶段均已 confirmed。")
            return
        status = state["phases"][nxt["id"]].get("status", "pending")
        if status == "completed" and not args.rerun:
            token = state["phases"][nxt["id"]].get("confirmation_token")
            print(f"阶段 {nxt['id']} 已完成但尚未确认。")
            print(f"请执行：python phase_runner.py confirm {nxt['id']} --token {token}")
            return
        run_phase(phases, state, nxt["id"], rerun=args.rerun)
    elif args.cmd == "confirm":
        confirm_phase(phases, state, args.phase_id, args.token)
    elif args.cmd == "reset":
        reset_phase(phases, state, args.phase, args.all)


if __name__ == "__main__":
    main()
