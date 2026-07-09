import importlib
import os
import sys
import types
import unittest


_MISSING = object()
_MODULES = (
    "torch",
    "config",
    "core.ml_colorizer",
    "core.model_downloader",
    "core.model_manager",
)


class FakeDevice:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


class ModelManagerDeviceTests(unittest.TestCase):
    def setUp(self):
        self.original_modules = {name: sys.modules.get(name, _MISSING) for name in _MODULES}
        self.original_cuda_preview = os.environ.get("COLORCOMIC_CUDA_PREVIEW")
        os.environ.pop("COLORCOMIC_CUDA_PREVIEW", None)

        fake_torch = types.ModuleType("torch")
        fake_torch.__version__ = "2.5.1+cu121"
        fake_torch.version = types.SimpleNamespace(cuda="12.1")
        fake_torch.device = lambda name: FakeDevice(name)
        fake_torch.cuda = types.SimpleNamespace(
            is_available=lambda: True,
            device_count=lambda: 1,
            get_device_properties=lambda index: types.SimpleNamespace(
                name="NVIDIA Test GPU",
                total_memory=8 * 1024**3,
            ),
            empty_cache=lambda: None,
        )

        fake_config = types.ModuleType("config")
        fake_config.Config = types.SimpleNamespace(
            WEIGHTS_DIR="weights",
            GENERATOR_WEIGHTS_PATH="generator.pth",
            EXTRACTOR_WEIGHTS_PATH="extractor.pth",
            DENOISER_WEIGHTS_DIR="denoiser",
        )

        fake_ml_colorizer = types.ModuleType("core.ml_colorizer")
        fake_ml_colorizer.MangaColorizer = self._make_colorizer_class()

        fake_downloader = types.ModuleType("core.model_downloader")
        fake_downloader.ensure_models_downloaded = lambda *args, **kwargs: None

        sys.modules["torch"] = fake_torch
        sys.modules["config"] = fake_config
        sys.modules["core.ml_colorizer"] = fake_ml_colorizer
        sys.modules["core.model_downloader"] = fake_downloader
        sys.modules.pop("core.model_manager", None)
        self.model_manager_module = importlib.import_module("core.model_manager")

    def tearDown(self):
        for name, module in self.original_modules.items():
            if module is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        if self.original_cuda_preview is None:
            os.environ.pop("COLORCOMIC_CUDA_PREVIEW", None)
        else:
            os.environ["COLORCOMIC_CUDA_PREVIEW"] = self.original_cuda_preview

    @staticmethod
    def _make_colorizer_class(captured=None):
        class FakeMangaColorizer:
            def __init__(self, **kwargs):
                self.device_name = kwargs["device"]
                if captured is not None:
                    captured["device"] = kwargs["device"]

        return FakeMangaColorizer

    def test_official_cpu_build_resolves_model_manager_to_cpu(self):
        manager = self.model_manager_module.ModelManager(device="cuda")

        self.assertEqual(str(manager._resolve_device()), "cpu")
        self.assertTrue(manager.cuda_available)

    def test_model_manager_uses_centralized_device_resolution(self):
        calls = []

        def fake_detect():
            calls.append(("detect",))
            return {"cuda_available": True}

        def fake_resolve(requested_device, *, capabilities, official_cpu_build):
            calls.append(("resolve", requested_device, capabilities, official_cpu_build))
            return {
                "resolved_device": "cpu",
                "cuda_available": True,
                "official_cpu_build": official_cpu_build,
                "fallback_reason": "official_cpu_build",
            }

        self.model_manager_module.detect_device_capabilities = fake_detect
        self.model_manager_module.is_official_cpu_build = lambda: True
        self.model_manager_module.resolve_compute_device = fake_resolve

        manager = self.model_manager_module.ModelManager(device="cuda")

        self.assertEqual(str(manager._resolve_device()), "cpu")
        self.assertEqual(calls, [
            ("detect",),
            ("resolve", "cuda", {"cuda_available": True}, True),
        ])

    def test_auto_colorizer_receives_resolved_cpu_device(self):
        captured = {}
        self.model_manager_module.MangaColorizer = self._make_colorizer_class(captured)

        manager = self.model_manager_module.ModelManager(device="cuda")

        manager._load_mcv2()

        self.assertEqual(captured["device"], "cpu")


if __name__ == "__main__":
    unittest.main()
