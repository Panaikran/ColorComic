"""Verify packaging-critical dependencies import in a CPU desktop env."""

from __future__ import annotations

import importlib
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.device_detection import detect_device_capabilities


MODULES = (
    ("flask", "Flask"),
    ("dotenv", "python-dotenv"),
    ("webview", "pywebview"),
    ("torch", "torch"),
    ("cv2", "opencv"),
    ("fitz", "PyMuPDF"),
    ("PIL", "Pillow"),
)


def _format_bytes(value) -> str:
    if value is None:
        return "unknown"
    return f"{value / (1024 ** 3):.1f} GiB"


def _print_torch_cuda_info(torch_module) -> None:
    capabilities = detect_device_capabilities(torch_module)
    print(f"torch CUDA build: {capabilities.get('cuda_version') or 'none'}")
    print(f"CUDA available: {capabilities.get('cuda_available')}")
    gpus = capabilities.get("gpus") or []
    if not gpus:
        print("CUDA GPUs: none")
        return
    for gpu in gpus:
        name = gpu.get("name") or f"GPU {gpu.get('index')}"
        vram = _format_bytes(gpu.get("total_memory_bytes"))
        print(f"CUDA GPU {gpu.get('index')}: {name} ({vram})")


def main() -> int:
    for module_name, label in MODULES:
        module = importlib.import_module(module_name)
        version = getattr(module, "__version__", "unknown")
        print(f"{label}: {version}")
        if module_name == "torch":
            _print_torch_cuda_info(module)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
