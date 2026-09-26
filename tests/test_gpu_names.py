import ctypes
import time
import unittest
from unittest.mock import Mock, patch

from app.stats_service import SystemStatsProvider, WindowsGpuEngineMonitor, _PdhCounterItem


class GpuNamesTest(unittest.TestCase):
    def setUp(self):
        self.provider = SystemStatsProvider.__new__(SystemStatsProvider)
        self.provider._gpu_monitor = Mock()
        self.provider._nvml_gpu = Mock(return_value={
            "name": "RTX 3060 Laptop GPU", "percent": 12,
            "mem_percent": 40, "used": 2.4, "total": 6,
        })

    def engine(self, name, count=3):
        self.provider._gpu_monitor.read.return_value = {
            "name": name, "percent": 42, "adapter_count": count,
        }

    def test_hybrid_gpu_shows_windows_adapter_model(self):
        self.engine("NVIDIA GeForce RTX 3060 Laptop GPU")
        result = self.provider.gpu_stats()
        self.assertEqual(result["name"], "RTX 3060 Laptop GPU")
        self.assertEqual(result["percent"], 42)

    def test_integrated_gpu_is_not_named_after_nvml_card(self):
        self.engine("Intel(R) UHD Graphics", count=1)
        self.assertEqual(self.provider.gpu_stats()["name"], "Intel(R) UHD Graphics")

    def test_windows_model_does_not_require_nvml(self):
        self.engine("AMD Radeon RX 7600")
        self.provider._nvml_gpu.return_value = None
        result = self.provider.gpu_stats()
        self.assertEqual(result["name"], "AMD Radeon RX 7600")
        self.assertFalse(result["memory_supported"])

    def test_unknown_windows_adapter_is_not_mislabelled(self):
        self.engine(None, count=1)
        self.assertEqual(self.provider.gpu_stats()["name"], "Windows GPU")

    def test_nvml_only_fallback(self):
        self.provider._gpu_monitor.read.return_value = None
        result = self.provider.gpu_stats()
        self.assertEqual(result["name"], "RTX 3060 Laptop GPU")
        self.assertEqual(result["percent"], 12)

    def test_no_gpu(self):
        self.provider._gpu_monitor.read.return_value = None
        self.provider._nvml_gpu.return_value = None
        self.assertEqual(self.provider.gpu_stats(), {"supported": False})

    def test_counter_luid_matches_model_when_busiest_gpu_changes(self):
        monitor = WindowsGpuEngineMonitor.__new__(WindowsGpuEngineMonitor)
        monitor.available = True
        monitor._query = ctypes.c_void_p()
        monitor._counter = ctypes.c_void_p()
        monitor._adapter_names = {(0, 10): "Intel GPU", (0xFFFFFFFF, 11): "NVIDIA GPU"}
        monitor._last_name_refresh = time.monotonic()
        monitor._pdh = Mock()
        monitor._pdh.PdhCollectQueryData.return_value = 0
        items = (_PdhCounterItem * 2)()
        items[0].name = "pid_1_luid_0x00000000_0x0000000a_phys_0_eng_0_engtype_3D"
        items[1].name = "pid_2_luid_0xFFFFFFFF_0xB_phys_1_eng_0_engtype_3D"
        items[0].value.value.double_value = 15
        items[1].value.value.double_value = 65

        def formatted_array(counter, flags, size, count, buffer):
            ctypes.cast(size, ctypes.POINTER(ctypes.c_ulong))[0] = ctypes.sizeof(items)
            ctypes.cast(count, ctypes.POINTER(ctypes.c_ulong))[0] = len(items)
            if buffer is None:
                return monitor._PDH_MORE_DATA
            ctypes.memmove(buffer, items, ctypes.sizeof(items))
            return 0

        monitor._pdh.PdhGetFormattedCounterArrayW.side_effect = formatted_array
        first = monitor.read()
        self.assertEqual((first["name"], first["percent"]), ("NVIDIA GPU", 65))
        items[0].value.value.double_value = 90
        second = monitor.read()
        self.assertEqual((second["name"], second["percent"]), ("Intel GPU", 90))
        self.assertEqual(second["adapter_count"], 2)

        # A driver reset changes LUIDs: retry discovery at most every 30 seconds.
        monitor._adapter_names = {}
        with patch("app.stats_service.windows_gpu_names", return_value={(0, 10): "Intel GPU"}) as discover:
            self.assertIsNone(monitor.read()["name"])
            discover.assert_not_called()
            monitor._last_name_refresh -= 31
            self.assertEqual(monitor.read()["name"], "Intel GPU")
            discover.assert_called_once()


if __name__ == "__main__":
    unittest.main()
