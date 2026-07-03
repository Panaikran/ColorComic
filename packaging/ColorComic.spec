# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-folder build spec for ColorComic Windows CPU desktop."""

from pathlib import Path
import os

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


PROJECT_ROOT = Path(SPECPATH).parent
APP_ICON = PROJECT_ROOT / "static" / "img" / "colorcomic.ico"
BUILD_CACHE = PROJECT_ROOT / "build" / "hf-cache"
BUILD_CACHE.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(BUILD_CACHE)
os.environ["HF_HUB_CACHE"] = str(BUILD_CACHE / "hub")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(BUILD_CACHE / "hub")
os.environ["TRANSFORMERS_CACHE"] = str(BUILD_CACHE / "transformers")
os.environ["DIFFUSERS_CACHE"] = str(BUILD_CACHE / "diffusers")


def include_tree(path: str, dest: str):
    source_root = PROJECT_ROOT / path
    entries = []
    if not source_root.exists():
        return entries
    for source in source_root.rglob("*"):
        if source.is_file():
            relative_parent = source.parent.relative_to(source_root)
            entries.append((str(source), str(Path(dest) / relative_parent)))
    return entries


def existing_file(path: str, dest: str):
    source = PROJECT_ROOT / path
    if source.exists():
        return [(str(source), dest)]
    return []


datas = []
datas += include_tree("templates", "templates")
datas += include_tree("static", "static")
datas += include_tree("vendor", "vendor")
datas += existing_file("LICENSE", ".")
datas += existing_file("README.md", ".")
datas += existing_file("THIRD_PARTY_NOTICES.md", ".")
datas += existing_file("NOTICE", ".")

for package_name in (
    "flask",
    "webview",
    "torch",
    "torchvision",
    "transformers",
    "diffusers",
    "huggingface_hub",
    "cv2",
    "fitz",
    "PIL",
    "numpy",
    "scipy",
    "skimage",
    "kornia",
):
    datas += collect_data_files(package_name, include_py_files=False)

for distribution_name in (
    "Flask",
    "pywebview",
    "torch",
    "torchvision",
    "transformers",
    "diffusers",
    "huggingface-hub",
    "opencv-contrib-python",
    "PyMuPDF",
    "Pillow",
    "numpy",
    "scipy",
    "scikit-image",
    "kornia",
    "pydantic",
):
    try:
        datas += copy_metadata(distribution_name)
    except Exception:
        pass

binaries = []
for package_name in ("torch", "torchvision", "cv2", "numpy", "scipy"):
    binaries += collect_dynamic_libs(package_name)

hiddenimports = [
    "flask",
    "webview",
    "torch",
    "torch.nn",
    "torch.nn.functional",
    "torchvision",
    "torchvision.transforms",
    "torchvision.models",
    "transformers",
    "diffusers",
    "huggingface_hub",
    "cv2",
    "fitz",
    "PIL",
    "PIL.Image",
    "numpy",
    "scipy",
    "scipy.io",
    "skimage",
    "skimage.io",
    "kornia",
    "accelerate",
    "omegaconf",
    "einops",
    "gdown",
    "app",
    "config",
    "desktop",
    "models.schemas",
    "core.color_consistency",
    "core.ml_colorizer",
    "core.manga_ninja_colorizer",
    "core.model_downloader",
    "core.model_manager",
    "core.panel_detector",
    "core.paths",
    "core.pdf_handler",
    "core.postprocessor",
    "core.upscaler",
    "vendor.manga_colorization_v2.colorizator",
    "vendor.manganinja.pipeline",
    "vendor.manganinja.annotator.lineart",
]

hiddenimports += collect_submodules(
    "core",
    filter=lambda name: ".tests" not in name and not name.endswith(".tests"),
)
hiddenimports += collect_submodules(
    "models",
    filter=lambda name: ".tests" not in name and not name.endswith(".tests"),
)
hiddenimports += collect_submodules(
    "vendor",
    filter=lambda name: ".tests" not in name and not name.endswith(".tests"),
)


a = Analysis(
    [str(PROJECT_ROOT / "desktop.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tensorflow",
        "matplotlib",
        "IPython",
        "jupyter",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ColorComic",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(APP_ICON),
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ColorComic",
)
