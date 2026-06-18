"""Verify packaging-critical dependencies import in a CPU desktop env."""

from __future__ import annotations

import importlib


MODULES = (
    ("flask", "Flask"),
    ("dotenv", "python-dotenv"),
    ("webview", "pywebview"),
    ("torch", "torch"),
    ("cv2", "opencv"),
    ("fitz", "PyMuPDF"),
    ("PIL", "Pillow"),
)


def main() -> int:
    for module_name, label in MODULES:
        module = importlib.import_module(module_name)
        version = getattr(module, "__version__", "unknown")
        print(f"{label}: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
