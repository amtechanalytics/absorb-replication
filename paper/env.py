"""Paths, the SQL engine (dbt + DuckDB installed from pinned wheels), the Java runtime and command helpers."""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("RH_ROOT", os.getcwd())).resolve()
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "manifest"
# The working directory (generated data, databases, the installed engine) lives beside the repository, never inside
# it: the harness unit tests, the self-check and the repair step copy the whole repository tree, some of them many
# times, and several gigabytes of working data inside it fill the disk.
def _work_dir(root: Path) -> Path:
    if os.environ.get("ABSORB_WORK"):
        return Path(os.environ["ABSORB_WORK"]).resolve()
    name = root.name + "-work"
    for base in (root.parent, Path("/var/tmp"), Path.home()):     # the folder above the repository may be read-only
        cand = base / name
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / f".probe-{os.getpid()}"
            probe.write_text("")
            probe.unlink()
            return cand.resolve()
        except OSError:
            continue
    raise RuntimeError("no writable place for the working directory; set ABSORB_WORK")


WORK = _work_dir(ROOT)
ENGINE_SITE = WORK / "engine" / "site"
_ENGINE_READY = False


class EngineMissing(RuntimeError):
    pass


def asset(name: str) -> Path:
    """A pinned download. ABSORB_ASSET_<NAME> overrides the location (development only)."""
    ov = os.environ.get("ABSORB_ASSET_" + name.upper())
    if ov:
        return Path(ov)
    from rh import datapins
    return Path(datapins.path(name))


def touch(hb) -> None:
    if hb is not None:
        try:
            hb.touch()
        except Exception:  # noqa: BLE001
            pass


def run_cmd(cmd, *, cwd=None, env=None, timeout=3600, hb=None, log: Path | None = None) -> tuple[int, str]:
    """Run a command, keep the heartbeat moving while it runs, return (exit code, combined output)."""
    out_path = log or (WORK / "logs" / f"cmd-{os.getpid()}-{time.time_ns()}.log")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        p = subprocess.Popen([str(c) for c in cmd], cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
        t0 = time.time()
        while True:
            try:
                p.wait(timeout=15)
                break
            except subprocess.TimeoutExpired:
                touch(hb)
                if time.time() - t0 > timeout:
                    p.kill()
                    p.wait()
                    return 124, f"timeout after {timeout}s\n" + out_path.read_text(errors="replace")[-4000:]
    text = out_path.read_text(errors="replace")
    if log is None:
        out_path.unlink(missing_ok=True)
    return p.returncode, text


def clean_env(extra: dict | None = None) -> dict:
    """Environment for child processes that run SQL: no keys, no cloud or harness variables."""
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": str(WORK / "home"),
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1",
           "DBT_SEND_ANONYMOUS_USAGE_STATS": "false", "DO_NOT_TRACK": "1"}
    (WORK / "home").mkdir(parents=True, exist_ok=True)
    if engine_mode() == "installed":
        env["PYTHONPATH"] = str(ENGINE_SITE)
    env.update(extra or {})
    return env


# ---------------------------------------------------------------- engine
def engine_mode() -> str:
    """'installed' = pinned wheels under work/engine/site; 'system' = already importable; 'none'."""
    if (ENGINE_SITE / "duckdb").exists() and (ENGINE_SITE / "dbt").exists():
        return "installed"
    if os.environ.get("ABSORB_ENGINE") == "system":
        return "system"
    return "none"


def engine_available() -> bool:
    return engine_mode() != "none"


def install_engine(hb=None) -> dict:
    """Install the pinned wheels with the pinned pip wheel (no pip on the instance's virtual environment)."""
    if engine_mode() != "none":
        return {"mode": engine_mode(), "installed_now": False}
    pip_whl = asset("pip_wheel")
    ENGINE_SITE.mkdir(parents=True, exist_ok=True)
    req = MANIFEST / "engine-requirements.txt"
    cmd = [sys.executable, f"{pip_whl}/pip", "install", "--no-deps", "--only-binary=:all:", "--require-hashes", "--no-input",
           "--disable-pip-version-check", "--no-cache-dir", "--target", str(ENGINE_SITE), "-r", str(req)]
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(WORK / "home"), "LANG": "C.UTF-8"}
    (WORK / "home").mkdir(parents=True, exist_ok=True)
    code, out = run_cmd(cmd, env=env, timeout=1800, hb=hb, log=WORK / "logs" / "engine-install.log")
    if code != 0 or engine_mode() != "installed":
        raise RuntimeError(f"engine install failed (exit {code}): {out[-1500:]}")
    return {"mode": "installed", "installed_now": True}


def duck():
    """The duckdb module from the engine."""
    global _ENGINE_READY
    mode = engine_mode()
    if mode == "none":
        raise EngineMissing("SQL engine not installed")
    if mode == "installed" and not _ENGINE_READY and str(ENGINE_SITE) not in sys.path:
        sys.path.append(str(ENGINE_SITE))
    _ENGINE_READY = True
    import duckdb
    return duckdb


def connect(path, read_only=False, external=True):
    d = duck()
    con = d.connect(str(path), read_only=read_only)
    con.execute("SET TimeZone='UTC'")
    con.execute("SET threads=4")
    if not external:
        con.execute("SET enable_external_access=false")
    return con


def versions() -> dict:
    code, out = run_cmd([sys.executable, "-c",
                         "import duckdb, dbt.version as v; import dbt.adapters.duckdb.__version__ as a; "
                         "print(duckdb.__version__, v.__version__, a.version)"], env=clean_env(), timeout=300)
    parts = out.strip().split()[-3:] if code == 0 else []
    return {"duckdb": parts[0], "dbt_core": parts[1], "dbt_duckdb": parts[2]} if len(parts) == 3 else {"error": out[-500:]}


# ---------------------------------------------------------------- java
def java() -> str:
    ov = os.environ.get("ABSORB_JAVA")
    if ov:
        return ov
    base = asset("jre")
    hits = sorted(glob.glob(str(base / "**" / "bin" / "java"), recursive=True))
    if not hits:
        raise RuntimeError(f"no bin/java under {base}")
    os.chmod(hits[0], 0o755)
    return hits[0]


# ---------------------------------------------------------------- dbt
def dbt(args, project: Path, *, timeout=3600, hb=None, log: Path | None = None, threads=4) -> tuple[int, str]:
    cmd = [sys.executable, "-c", "import sys; from dbt.cli.main import cli; cli()", *args,
           "--project-dir", str(project), "--profiles-dir", str(project / "prof"), "--threads", str(threads),
           "--no-use-colors", "--no-version-check", "--no-partial-parse"]
    return run_cmd(cmd, cwd=project, env=clean_env(), timeout=timeout, hb=hb, log=log)
