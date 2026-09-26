import ctypes
import math
import os
import platform
import re
import subprocess
import threading
import time
from typing import Any, Optional

import psutil
try:
    import pynvml
except ImportError:
    pynvml = None
from multiprocessing.connection import Listener


class _PdhValue(ctypes.Union):
    _fields_ = [("long_value", ctypes.c_long), ("double_value", ctypes.c_double), ("large_value", ctypes.c_longlong)]


class _PdhCounterValue(ctypes.Structure):
    _fields_ = [("status", ctypes.c_ulong), ("value", _PdhValue)]


class _PdhCounterItem(ctypes.Structure):
    _fields_ = [("name", ctypes.c_wchar_p), ("value", _PdhCounterValue)]


class WindowsGpuEngineMonitor:
    """Task-Manager-compatible GPU usage, based on the busiest GPU engine."""

    _PDH_FMT_DOUBLE = 0x200
    _PDH_MORE_DATA = 0x800007D2
    _ADAPTER_RE = re.compile(r"luid_0x[0-9a-f]+_0x[0-9a-f]+_phys_\d+", re.I)

    def __init__(self) -> None:
        self._pdh: Optional[Any] = None
        self._query = ctypes.c_void_p()
        self._counter = ctypes.c_void_p()
        self.available = False
        if os.name != "nt":
            return
        try:
            self._pdh = ctypes.WinDLL("pdh")
            if self._pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query)) != 0:
                return
            if self._pdh.PdhAddEnglishCounterW(
                self._query, r"\GPU Engine(*)\Utilization Percentage", 0, ctypes.byref(self._counter)
            ) != 0:
                self.close()
                return
            # Rate counters require an initial collection before the first real sample.
            self._pdh.PdhCollectQueryData(self._query)
            self.available = True
        except (AttributeError, OSError):
            self.close()

    def read(self) -> Optional[dict[str, Any]]:
        if not self.available or self._pdh is None or self._pdh.PdhCollectQueryData(self._query) != 0:
            return None
        size = ctypes.c_ulong(0)
        count = ctypes.c_ulong(0)
        status = int(self._pdh.PdhGetFormattedCounterArrayW(
            self._counter, self._PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None
        )) & 0xFFFFFFFF
        if status != self._PDH_MORE_DATA or not size.value or not count.value:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if self._pdh.PdhGetFormattedCounterArrayW(
            self._counter, self._PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), buffer
        ) != 0:
            return None
        adapters: dict[str, float] = {}
        items = ctypes.cast(buffer, ctypes.POINTER(_PdhCounterItem))
        for index in range(count.value):
            item = items[index]
            percent = item.value.value.double_value
            if item.value.status != 0 or not math.isfinite(percent) or percent < 0:
                continue
            match = self._ADAPTER_RE.search(item.name or "")
            adapter = match.group(0).lower() if match else "unknown"
            adapters[adapter] = max(adapters.get(adapter, 0.0), percent)
        if not adapters:
            return None
        adapter, percent = max(adapters.items(), key=lambda entry: entry[1])
        return {"percent": max(0.0, min(100.0, percent)), "adapter": adapter, "adapter_count": len(adapters)}

    def close(self) -> None:
        if self._pdh is not None and self._query.value:
            self._pdh.PdhCloseQuery(self._query)
        self._query = ctypes.c_void_p()
        self._counter = ctypes.c_void_p()
        self.available = False


class SystemStatsProvider:
    def __init__(self) -> None:
        # The first non-blocking psutil sample is undefined; prime it so every
        # published CPU percentage covers a real fixed sampling interval.
        psutil.cpu_percent(interval=None)
        self._cpu_name = self._get_cpu_name()
        self._gpu_devices: list[dict[str, Any]] = []
        self._gpu_monitor = WindowsGpuEngineMonitor()
        self._init_gpu()
        self._last_net_io = psutil.net_io_counters()
        self._last_net_time = time.monotonic()
        self._lock = threading.Lock()
        self._snapshot = self._empty_snapshot()

    @staticmethod
    def _empty_snapshot() -> dict[str, Any]:
        return {"cpu": {"percent": 0.0}, "mem": {"percent": 0.0, "used": 0.0, "total": 0.0}, "gpu": {"supported": False}, "net": {"up": 0.0, "down": 0.0}}

    @staticmethod
    def _percent(value: float) -> float:
        return max(0.0, min(100.0, float(value)))

    def _get_cpu_name(self) -> str:
        try:
            if platform.system() == "Windows":
                output = subprocess.check_output(["wmic", "cpu", "get", "Name"], text=True, stderr=subprocess.DEVNULL)
                names = [line.strip() for line in output.splitlines()[1:] if line.strip()]
                name = names[0] if names else "CPU"
            else:
                name = platform.processor() or "CPU"
            for discard in ["Intel", "AMD", "NVIDIA", "GeForce", "Core", "CPU", "(R)", "(TM)", "Processor"]:
                name = name.replace(discard, "")
            return " ".join(name.split()) or "CPU"
        except (OSError, subprocess.SubprocessError):
            return "CPU"

    def _init_gpu(self) -> None:
        if pynvml is None:
            return
        try:
            pynvml.nvmlInit()
            for index in range(pynvml.nvmlDeviceGetCount()):
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                raw_name = pynvml.nvmlDeviceGetName(handle)
                name = raw_name.decode(errors="replace") if isinstance(raw_name, bytes) else str(raw_name)
                self._gpu_devices.append({"handle": handle, "name": name.replace("NVIDIA", "").replace("GeForce", "").strip() or "NVIDIA GPU"})
        except Exception:
            self._gpu_devices = []

    def memory_stats(self) -> dict[str, float]:
        vm = psutil.virtual_memory()
        return {"percent": float(vm.percent), "used": vm.used / (1024**3), "total": vm.total / (1024**3)}

    def _nvml_gpu(self) -> Optional[dict[str, Any]]:
        readings = []
        for device in self._gpu_devices:
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(device["handle"])
                mem = pynvml.nvmlDeviceGetMemoryInfo(device["handle"])
                readings.append({**device, "percent": self._percent(getattr(util, "gpu", 0)), "mem_percent": (mem.used / mem.total) * 100 if mem.total else 0.0, "used": mem.used / (1024**3), "total": mem.total / (1024**3)})
            except Exception:
                continue
        # Percentages from different physical GPUs cannot be added.  Use the
        # active adapter instead of the old, hard-coded NVML device index 0.
        return max(readings, key=lambda reading: reading["percent"]) if readings else None

    def gpu_stats(self) -> dict[str, Any]:
        engine = self._gpu_monitor.read()
        nvml = self._nvml_gpu()
        if engine is None and nvml is None:
            return {"supported": False}
        # Windows does not expose a stable NVML-to-LUID mapping.  On hybrid or
        # multi-GPU PCs, avoid labelling the busiest Windows adapter as an
        # NVIDIA card unless there is only one physical adapter counter.
        name = nvml["name"] if nvml is not None and (engine is None or engine["adapter_count"] == 1) else "Windows GPU"
        result: dict[str, Any] = {"supported": True, "percent": engine["percent"] if engine else nvml["percent"], "source": "windows-gpu-engine" if engine else "nvml", "name": name, "memory_supported": nvml is not None}
        if engine:
            result["adapter_count"] = engine["adapter_count"]
        if nvml:
            result.update(mem_percent=self._percent(nvml["mem_percent"]), used=nvml["used"], total=nvml["total"])
        return result

    def _net_stats(self) -> dict[str, float]:
        now = time.monotonic()
        current = psutil.net_io_counters()
        elapsed = now - self._last_net_time
        if elapsed <= 0:
            return {"up": 0.0, "down": 0.0}
        result = {"up": max(0.0, (current.bytes_sent - self._last_net_io.bytes_sent) / elapsed), "down": max(0.0, (current.bytes_recv - self._last_net_io.bytes_recv) / elapsed)}
        self._last_net_io = current
        self._last_net_time = now
        return result

    def refresh(self) -> None:
        sample = {"cpu": {"percent": self._percent(psutil.cpu_percent(interval=None))}, "mem": self.memory_stats(), "gpu": self.gpu_stats(), "net": self._net_stats()}
        with self._lock:
            self._snapshot = sample

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {key: value.copy() for key, value in self._snapshot.items()}

    def close(self) -> None:
        self._gpu_monitor.close()
        if pynvml is not None and self._gpu_devices:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass

def _sampling_loop(stats: SystemStatsProvider, stop_event: threading.Event, interval: float) -> None:
    """Keep interval-based metrics independent from client/UI timing."""
    next_tick = time.monotonic()
    while not stop_event.is_set():
        try:
            stats.refresh()
        except Exception:
            # Preserve the previous good sample through a short driver reset.
            pass
        next_tick += interval
        stop_event.wait(max(0.0, next_tick - time.monotonic()))


def run_server(address=("localhost", 6000), authkey=b"corepulse", sample_interval: float = 1.0):
    stats = SystemStatsProvider()
    stop_event = threading.Event()
    sampler = threading.Thread(target=_sampling_loop, args=(stats, stop_event, sample_interval), name="metric-sampler", daemon=True)
    sampler.start()
    listener = Listener(address=address, authkey=authkey)
    try:
        while not stop_event.is_set():
            try:
                conn = listener.accept()
            except Exception:
                break
            try:
                while not stop_event.is_set():
                    try:
                        msg = conn.recv()
                    except (EOFError, OSError, ConnectionResetError):
                        break
                    except Exception:
                        continue
                    if msg == "get":
                        try:
                            conn.send(stats.snapshot())
                        except Exception:
                            try:
                                conn.send({"cpu": {"percent": 0}, "mem": {"percent": 0, "used": 0, "total": 0}, "gpu": {"supported": False}, "net": {"up": 0, "down": 0}})
                            except Exception:
                                pass
                    elif msg == "ping":
                        try:
                            conn.send("pong")
                        except Exception:
                            pass
                    elif msg == "quit":
                        stop_event.set()
                        try:
                            conn.send("bye")
                        except Exception:
                            pass
                        break
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    finally:
        stop_event.set()
        sampler.join(timeout=sample_interval + 0.5)
        try:
            listener.close()
        except Exception:
            pass
        stats.close()
