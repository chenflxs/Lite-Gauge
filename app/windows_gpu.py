"""Resolve Windows GPU performance-counter LUIDs to hardware names via DXGI."""

import ctypes
import os
import uuid


class _Luid(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_int32)]


class _AdapterDesc(ctypes.Structure):
    _fields_ = [
        ("description", ctypes.c_wchar * 128),
        ("vendor_id", ctypes.c_uint32),
        ("device_id", ctypes.c_uint32),
        ("subsys_id", ctypes.c_uint32),
        ("revision", ctypes.c_uint32),
        ("dedicated_video_memory", ctypes.c_size_t),
        ("dedicated_system_memory", ctypes.c_size_t),
        ("shared_system_memory", ctypes.c_size_t),
        ("luid", _Luid),
    ]


def _com_method(instance, slot, result_type, *arg_types):
    vtable = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *arg_types)(vtable[slot])


def windows_gpu_names() -> dict[tuple[int, int], str]:
    """Return names keyed by (LUID high, LUID low), independent of GPU ordering."""
    names = {}
    if os.name != "nt":
        return names
    factory = ctypes.c_void_p()
    try:
        dxgi = ctypes.WinDLL("dxgi")
        create_factory = dxgi.CreateDXGIFactory
        create_factory.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        create_factory.restype = ctypes.c_int32
        # IID_IDXGIFactory; GUID bytes use Windows' little-endian field layout.
        iid = (ctypes.c_ubyte * 16).from_buffer_copy(
            uuid.UUID("7b7166ec-21c7-44ae-b21a-c9ae321ae369").bytes_le
        )
        if create_factory(iid, ctypes.byref(factory)) < 0:
            return names
        # IDXGIFactory::EnumAdapters follows IUnknown and IDXGIObject (slot 7).
        enum_adapters = _com_method(factory, 7, ctypes.c_int32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p))
        index = 0
        while True:
            adapter = ctypes.c_void_p()
            if enum_adapters(factory, index, ctypes.byref(adapter)) < 0:
                break
            try:
                desc = _AdapterDesc()
                get_desc = _com_method(adapter, 8, ctypes.c_int32, ctypes.POINTER(_AdapterDesc))
                if get_desc(adapter, ctypes.byref(desc)) >= 0:
                    name = desc.description.strip()
                    if name:
                        names[(desc.luid.high & 0xFFFFFFFF, desc.luid.low)] = name
            finally:
                _com_method(adapter, 2, ctypes.c_uint32)(adapter)  # IUnknown::Release
            index += 1
    except (AttributeError, OSError):
        # Missing DXGI/driver support must not prevent usage sampling or NVML fallback.
        pass
    finally:
        if factory.value:
            _com_method(factory, 2, ctypes.c_uint32)(factory)
    return names
