"""
Container-aware system statistics collector for the admin System tab.

Reads cgroup v2 (memory.max, cpu.max) with cgroup v1 fallbacks so the 512 MB /
0.1 CPU Render free-tier limits are reported correctly instead of host numbers.
Everything else comes from psutil. Collection is cached for 1 second and never
spawns subprocesses. A bounded ring buffer (15 minutes @ 5 s resolution) keeps
sparkline history in memory only — never written to the database.
"""

import os
import sys
import time
import math
import json
import shutil
import logging
import threading
import subprocess
from pathlib import Path
from collections import deque
from datetime import datetime
from typing import Any, Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None

from backend.app.core.config import settings

logger = logging.getLogger("system_stats")

# ---------------------------------------------------------------------------
# Cgroup limit readers (container-aware). Every path is optional: on Windows /
# bare metal these files do not exist and we fall back to host values.
# ---------------------------------------------------------------------------

CGROUP_V2_MEM = "/sys/fs/cgroup/memory.max"
CGROUP_V1_MEM = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
CGROUP_V2_CPU = "/sys/fs/cgroup/cpu.max"
CGROUP_V1_CPU_QUOTA = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
CGROUP_V1_CPU_PERIOD = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"


def _read_int_file(path: str) -> Optional[int]:
    """Reads an integer from a cgroup file; returns None for 'max', missing files, or errors."""
    try:
        raw = open(path, "r", encoding="utf-8").read().strip()
    except OSError:
        return None
    if not raw or raw == "max" or raw == "-1":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def get_memory_limit_bytes() -> Optional[int]:
    """Returns the container memory limit in bytes, or None when unlimited / not containerized."""
    # Sanity ceiling (~256 TB): cgroup "unlimited" sentinels are huge ints, not real limits
    MAX_PLAUSIBLE = 1 << 48
    v2 = _read_int_file(CGROUP_V2_MEM)
    if v2 is not None and 0 < v2 < MAX_PLAUSIBLE:
        return v2
    v1 = _read_int_file(CGROUP_V1_MEM)
    # v1 reports an absurdly large number (near x86 max) when unlimited
    if v1 is not None and 0 < v1 < MAX_PLAUSIBLE:
        return v1
    return None


def get_cpu_limit() -> Optional[float]:
    """Returns the container CPU quota in cores (e.g. 0.1), or None when unlimited."""
    # cgroup v2: single file "quota period", e.g. "10000 100000" or "max 100000"
    try:
        raw = open(CGROUP_V2_CPU, "r", encoding="utf-8").read().split()
        if len(raw) == 2 and raw[0] != "max":
            quota, period = int(raw[0]), int(raw[1])
            if quota > 0 and period > 0:
                return quota / period
    except (OSError, ValueError, IndexError):
        pass
    # cgroup v1: two files
    quota = _read_int_file(CGROUP_V1_CPU_QUOTA)
    period = _read_int_file(CGROUP_V1_CPU_PERIOD)
    if quota is not None and period and quota > 0 and period > 0:
        return quota / period
    return None


def get_effective_core_count() -> int:
    """Minimum of host core count and the container CPU quota, rounded up (>= 1)."""
    host = os.cpu_count() or 1
    limit = get_cpu_limit()
    if limit is None:
        return host
    return max(1, min(host, math.ceil(limit)))


# ---------------------------------------------------------------------------
# Ring buffer history (15 min @ 5 s => 180 samples, bounded)
# ---------------------------------------------------------------------------

HISTORY_SECONDS = 15 * 60
HISTORY_RESOLUTION = 5
HISTORY_MAXLEN = HISTORY_SECONDS // HISTORY_RESOLUTION

_history: deque = deque(maxlen=HISTORY_MAXLEN)
_hist_lock = threading.Lock()
_sampler_thread: Optional[threading.Thread] = None
_sampler_stop = threading.Event()

# Stats cache (1 s TTL) so concurrent dashboard + SSE clients cost near zero
_cache_lock = threading.Lock()
_cache: Dict[str, Any] = {"stats": None, "at": 0.0}
_CACHE_TTL = 1.0

# Mongo ping cached separately (10 s) — a ping per stats call is wasteful
_mongo_cache: Dict[str, Any] = {"latency_ms": None, "state": "unknown", "at": 0.0}
_MONGO_TTL = 10.0

# ---------------------------------------------------------------------------
# GPU telemetry collector (NVIDIA CUDA, Windows DirectX/D3D, and Linux DRM).
# Probe is cached so subprocesses are only called periodically in the background
# sampler thread — never on synchronous request paths.
# ---------------------------------------------------------------------------

_gpu_static: Dict[str, Any] = {
    "available": False,
    "name": None,
    "driver_version": None,
    "memory_total_mb": None,
    "engine_type": "None",
    "at": 0.0,
}
_gpu_telemetry: Dict[str, Any] = {
    "utilization_percent": 0.0,
    "memory_used_mb": None,
    "memory_percent": None,
    "temperature_c": None,
    "at": 0.0,
}
_gpu_lock = threading.Lock()


def _probe_gpu_static() -> Dict[str, Any]:
    """Discovers GPU hardware presence once (refreshes every 5 minutes in background)."""
    global _gpu_static
    now = time.time()
    with _gpu_lock:
        if _gpu_static["at"] > 0 and now - _gpu_static["at"] < 300.0:
            return dict(_gpu_static)

    # 1. NVIDIA (nvidia-smi)
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            p = subprocess.run(
                [
                    smi,
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if p.returncode == 0 and p.stdout.strip():
                parts = [x.strip() for x in p.stdout.strip().split(",")]
                res = {
                    "available": True,
                    "name": parts[0],
                    "driver_version": parts[1] if len(parts) > 1 else None,
                    "memory_total_mb": float(parts[2]) if len(parts) > 2 else None,
                    "engine_type": "NVIDIA CUDA / NVENC",
                    "at": now,
                }
                with _gpu_lock:
                    _gpu_static = res
                return res
        except Exception as e:
            logger.debug(f"nvidia-smi probe notice: {e}")

    # 2. Windows DirectX / WMI (AMD Radeon, Intel Arc/Iris, NVIDIA)
    if sys.platform == "win32":
        try:
            ps_probe = "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion | ConvertTo-Json"
            p = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_probe],
                capture_output=True,
                text=True,
                timeout=4,
            )
            if p.returncode == 0 and p.stdout.strip():
                data = json.loads(p.stdout)
                if isinstance(data, list):
                    data = data[0]
                name = data.get("Name") or "Windows GPU"
                ram_b = int(data.get("AdapterRAM") or 0)
                ram_mb = round(ram_b / (1024 * 1024), 1) if ram_b > 0 else None
                drv = data.get("DriverVersion")
                res = {
                    "available": True,
                    "name": name,
                    "driver_version": drv,
                    "memory_total_mb": ram_mb,
                    "engine_type": "DirectX / Windows D3D Acceleration",
                    "at": now,
                }
                with _gpu_lock:
                    _gpu_static = res
                return res
        except Exception as e:
            logger.debug(f"Windows GPU probe notice: {e}")

    # 3. Linux DRM / card0
    if sys.platform.startswith("linux"):
        try:
            card_dir = Path("/sys/class/drm/card0/device")
            if card_dir.exists():
                res = {
                    "available": True,
                    "name": "Linux DRM GPU Device",
                    "driver_version": None,
                    "memory_total_mb": None,
                    "engine_type": "Linux DRM / Mesa",
                    "at": now,
                }
                with _gpu_lock:
                    _gpu_static = res
                return res
        except Exception:
            pass

    # No GPU detected
    res = {
        "available": False,
        "name": None,
        "driver_version": None,
        "memory_total_mb": None,
        "engine_type": "None",
        "at": now,
    }
    with _gpu_lock:
        _gpu_static = res
    return res


def _sample_gpu_telemetry() -> Dict[str, Any]:
    """Periodically samples GPU load in background thread."""
    global _gpu_telemetry
    static_gpu = _probe_gpu_static()
    if not static_gpu.get("available"):
        return _gpu_telemetry

    now = time.time()
    # 1. NVIDIA
    smi = shutil.which("nvidia-smi")
    if smi and "NVIDIA" in static_gpu.get("engine_type", ""):
        try:
            p = subprocess.run(
                [
                    smi,
                    "--query-gpu=utilization.gpu,memory.used,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if p.returncode == 0 and p.stdout.strip():
                parts = [x.strip() for x in p.stdout.strip().split(",")]
                u = float(parts[0])
                mu = float(parts[1])
                mt = static_gpu.get("memory_total_mb") or 0
                res = {
                    "utilization_percent": round(u, 1),
                    "memory_used_mb": round(mu, 1),
                    "memory_percent": round((mu / mt) * 100, 1) if mt > 0 else 0.0,
                    "temperature_c": float(parts[2]) if len(parts) > 2 else None,
                    "at": now,
                }
                with _gpu_lock:
                    _gpu_telemetry = res
                return res
        except Exception:
            pass

    # 2. Windows 3D counter
    if sys.platform == "win32":
        try:
            u_cmd = r"(Get-Counter -Counter '\GPU Engine(*engtype_3D)\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples | Measure-Object -Property CookedValue -Sum | Select-Object -ExpandProperty Sum"
            pu = subprocess.run(
                ["powershell", "-NoProfile", "-Command", u_cmd],
                capture_output=True,
                text=True,
                timeout=4,
            )
            if pu.returncode == 0 and pu.stdout.strip():
                util = round(min(100.0, max(0.0, float(pu.stdout.strip()))), 1)
                res = {
                    "utilization_percent": util,
                    "memory_used_mb": None,
                    "memory_percent": None,
                    "temperature_c": None,
                    "at": now,
                }
                with _gpu_lock:
                    _gpu_telemetry = res
                return res
        except Exception:
            pass

    # 3. Linux DRM
    if sys.platform.startswith("linux"):
        try:
            busy_file = Path("/sys/class/drm/card0/device/gpu_busy_percent")
            if busy_file.exists():
                raw = busy_file.read_text().strip()
                res = {
                    "utilization_percent": float(raw),
                    "memory_used_mb": None,
                    "memory_percent": None,
                    "temperature_c": None,
                    "at": now,
                }
                with _gpu_lock:
                    _gpu_telemetry = res
                return res
        except Exception:
            pass

    return _gpu_telemetry


def get_history() -> list:
    """Returns a snapshot list of the ring buffer (oldest first)."""
    with _hist_lock:
        return list(_history)


def _sample_history_point() -> None:
    try:
        try:
            _sample_gpu_telemetry()
        except Exception:
            pass

        stats = collect_stats(force=True)
        point = {
            "ts": stats["timestamp"],
            "cpu_percent": stats["cpu"]["process_percent"],
            "mem_percent": stats["memory"]["process_percent"],
            "gpu_percent": (
                stats["gpu"]["utilization_percent"]
                if stats.get("gpu", {}).get("available")
                else None
            ),
        }
        with _hist_lock:
            _history.append(point)
    except Exception as e:
        logger.debug(f"History sampler skipped a tick: {e}")


def _history_sampler_loop() -> None:
    while not _sampler_stop.is_set():
        _sample_history_point()
        _sampler_stop.wait(HISTORY_RESOLUTION)


def start_history_sampler() -> None:
    """Starts the 5 s background sampler (idempotent)."""
    global _sampler_thread
    # Probe GPU in background upon startup
    threading.Thread(target=_probe_gpu_static, daemon=True, name="GPUProbe").start()

    if _sampler_thread is not None and _sampler_thread.is_alive():
        return
    _sampler_stop.clear()
    _sampler_thread = threading.Thread(
        target=_history_sampler_loop, daemon=True, name="StatsHistorySampler"
    )
    _sampler_thread.start()


def stop_history_sampler() -> None:
    _sampler_stop.set()


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------


def _mongo_probe() -> Dict[str, Any]:
    now = time.time()
    cached = dict(_mongo_cache)
    if now - cached["at"] < _MONGO_TTL:
        return cached
    state, latency = "local_store", None
    try:
        from backend.app.db.mongo import get_db

        db = get_db()
        if db is not None:
            start = time.perf_counter()
            db.command("ping")
            latency = round((time.perf_counter() - start) * 1000, 1)
            state = "connected"
    except Exception:
        state = "error"
        latency = None
    result = {"state": state, "latency_ms": latency, "at": now}
    with _cache_lock:
        _mongo_cache.update(result)
    return result


def _engine_snapshot() -> Dict[str, int]:
    """Running bot workers and open browser instances (cheap, in-memory state)."""
    workers = 0
    try:
        from common.engine_manager import engine_manager

        for st in engine_manager.get_status().values():
            if st.get("status") in ("Running", "Waiting"):
                workers += 1
    except Exception:
        pass
    browsers = workers  # each running engine holds one browser instance
    try:
        from backend.app.services.session_manager import stream_manager

        if stream_manager.is_active:
            browsers += 1
    except Exception:
        pass
    return {"workers_running": workers, "browsers_open": browsers}


def collect_stats(force: bool = False) -> Dict[str, Any]:
    """Collects one stats snapshot; cached for 1 second unless force=True."""
    now = time.time()
    with _cache_lock:
        if (
            not force
            and _cache["stats"] is not None
            and now - _cache["at"] < _CACHE_TTL
        ):
            return _cache["stats"]

    proc = psutil.Process(os.getpid())
    host_mem = psutil.virtual_memory()
    mem_limit = get_memory_limit_bytes()

    rss_bytes = proc.memory_info().rss
    # Container-aware memory %: against cgroup limit when present, else host total
    mem_reference = mem_limit if mem_limit else host_mem.total
    process_mem_pct = (
        round(rss_bytes / mem_reference * 100, 1) if mem_reference else 0.0
    )

    data_dir = settings.DATA_DIR
    try:
        disk_data = psutil.disk_usage(str(data_dir))
        disk_used, disk_total = disk_data.used, disk_data.total
    except Exception:
        disk_used, disk_total = 0, 0

    try:
        temp_dir = os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp"
        disk_temp = psutil.disk_usage(temp_dir)
        temp_used, temp_total = disk_temp.used, disk_temp.total
    except Exception:
        temp_used, temp_total = disk_used, disk_total

    # Prime the cpu_percent counters on first call (returns 0.0 before an interval)
    proc.cpu_percent(interval=None)
    psutil.cpu_percent(interval=None)

    try:
        fds = proc.num_fds()  # Unix only
    except (AttributeError, psutil.AccessDenied):
        try:
            fds = proc.num_handles()  # Windows equivalent
        except Exception:
            fds = None

    mongo = _mongo_probe()
    engines = _engine_snapshot()

    with _cache_lock:
        _mongo_cache.update(mongo)

    with _gpu_lock:
        gpu_stat = dict(_gpu_static)
        gpu_tel = dict(_gpu_telemetry)

    stats = {
        "timestamp": datetime.now().isoformat(),
        "cpu": {
            "process_percent": round(proc.cpu_percent(interval=None), 1),
            "host_percent": round(psutil.cpu_percent(interval=None), 1),
            "core_count_effective": get_effective_core_count(),
            "core_count_host": os.cpu_count(),
            "cpu_limit_cores": get_cpu_limit(),
        },
        "gpu": {
            "available": gpu_stat.get("available", False),
            "name": gpu_stat.get("name"),
            "engine_type": gpu_stat.get("engine_type"),
            "driver_version": gpu_stat.get("driver_version"),
            "memory_total_mb": gpu_stat.get("memory_total_mb"),
            "memory_used_mb": gpu_tel.get("memory_used_mb"),
            "memory_percent": gpu_tel.get("memory_percent"),
            "utilization_percent": gpu_tel.get("utilization_percent", 0.0),
            "temperature_c": gpu_tel.get("temperature_c"),
        },
        "memory": {
            "process_rss_mb": round(rss_bytes / (1024 * 1024), 1),
            "process_percent": process_mem_pct,
            "host_used_mb": round(host_mem.used / (1024 * 1024), 1),
            "host_total_mb": round(host_mem.total / (1024 * 1024), 1),
            "host_percent": host_mem.percent,
            "limit_mb": round(mem_limit / (1024 * 1024), 1) if mem_limit else None,
            "containerized": mem_limit is not None,
        },
        "disk": {
            "data_used_mb": round(disk_used / (1024 * 1024), 1),
            "data_total_mb": round(disk_total / (1024 * 1024), 1),
            "data_percent": (
                round(disk_used / disk_total * 100, 1) if disk_total else 0.0
            ),
            "temp_used_mb": round(temp_used / (1024 * 1024), 1),
            "temp_total_mb": round(temp_total / (1024 * 1024), 1),
            "temp_percent": (
                round(temp_used / temp_total * 100, 1) if temp_total else 0.0
            ),
        },
        "process": {
            "uptime_seconds": int(time.time() - proc.create_time()),
            "thread_count": proc.num_threads(),
            "open_fds": fds,
            "pid": proc.pid,
        },
        "workers": {
            "running": engines["workers_running"],
            "browsers_open": engines["browsers_open"],
        },
        "mongodb": {
            "state": mongo["state"],
            "latency_ms": mongo["latency_ms"],
        },
        "history": get_history(),
    }

    with _cache_lock:
        _cache["stats"] = stats
        _cache["at"] = now
    return stats
