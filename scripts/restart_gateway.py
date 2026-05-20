"""Restart Earl gateway in-place, preserving env from the running process.

Usage (run INSIDE the sandbox):
  python3 restart_gateway.py
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HOME = Path(os.environ["HOME"])
EARL_HOME = HOME / "earl"
LOG = EARL_HOME / "logs" / "gateway.log"
PID_FILE = EARL_HOME / "gateway.pid"
VENV_PY = EARL_HOME / "venv" / "bin" / "python"
REPO_DIR = EARL_HOME / "repo"


def find_gateway_pid() -> int | None:
    try:
        out = subprocess.run(
            ["pgrep", "-f", "python -m gateway.run"],
            capture_output=True,
            text=True,
            check=False,
        )
        pids = [int(p) for p in out.stdout.split() if p.strip()]
        return pids[0] if pids else None
    except Exception:
        return None


def read_environ(pid: int) -> dict[str, str]:
    """Read NUL-separated env from /proc/<pid>/environ."""
    raw = Path(f"/proc/{pid}/environ").read_bytes()
    env: dict[str, str] = {}
    for entry in raw.split(b"\x00"):
        if not entry or b"=" not in entry:
            continue
        k, _, v = entry.partition(b"=")
        env[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
    return env


def main() -> int:
    old_pid = find_gateway_pid()
    if old_pid is None:
        print("✗ no running gateway found", file=sys.stderr)
        return 1
    print(f"old gateway pid={old_pid}")

    env = read_environ(old_pid)
    relevant_keys = [
        k for k in env if k.startswith("EARL_") or k in {
            "TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "GATEWAY_ALLOW_ALL_USERS",
            "PATH", "HOME", "VIRTUAL_ENV", "LANG", "LC_ALL", "USER",
        }
    ]
    print(f"captured {len(relevant_keys)} env vars")

    # Build the env dict for the new process. Inherit minimal os.environ then
    # overlay everything we captured (so the new gateway is bit-for-bit
    # identical to the old one — same workspace, same Pipedream creds, same
    # bot token).
    new_env = dict(os.environ)
    for k in relevant_keys:
        new_env[k] = env[k]
    # Ensure venv binary is on PATH
    new_env["PATH"] = f"{EARL_HOME}/venv/bin:{new_env.get('PATH', '')}"
    new_env["VIRTUAL_ENV"] = str(EARL_HOME / "venv")

    # Kill old gateway
    try:
        os.kill(old_pid, signal.SIGTERM)
        time.sleep(1)
        os.kill(old_pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    subprocess.run(["pkill", "-f", "python -m gateway.run"], check=False)
    time.sleep(1)
    print("killed old gateway")

    # Start new gateway. Detach (setsid) so it survives this script exiting.
    log_fp = open(LOG, "ab")
    log_fp.write(b"\n=== gateway restart ===\n")
    log_fp.flush()
    proc = subprocess.Popen(
        [str(VENV_PY), "-m", "gateway.run"],
        cwd=str(REPO_DIR),
        env=new_env,
        stdout=log_fp,
        stderr=log_fp,
        start_new_session=True,
        close_fds=True,
    )
    PID_FILE.write_text(str(proc.pid))
    print(f"started new gateway pid={proc.pid}")

    # Wait a few seconds, then verify it's still alive
    time.sleep(5)
    actual = find_gateway_pid()
    if actual is None:
        print("✗ gateway crashed during boot. Tail of gateway.log:", file=sys.stderr)
        sys.stderr.write(LOG.read_text(errors="replace")[-2000:])
        return 3
    PID_FILE.write_text(str(actual))
    print(f"✓ gateway alive — pid={actual}")
    print()
    print("--- new gateway EARL_* env (first 12) ---")
    new_env_from_proc = read_environ(actual)
    for k in sorted(k for k in new_env_from_proc if k.startswith("EARL_"))[:12]:
        v = new_env_from_proc[k]
        print(f"  {k}={v[:8]}...")
    print()
    print("--- last 20 gateway.log lines ---")
    print("\n".join(LOG.read_text(errors="replace").splitlines()[-20:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
