import importlib
import os
import sys
import types
import unittest


_MISSING = object()
_MODULES = (
    "cv2",
    "numpy",
    "torch",
    "vendor.manga_colorization_v2.colorizator",
    "core.ml_colorizer",
)


class FakeDevice:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


class FakeInferenceMode:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeImage:
    shape = (8, 8, 3)

    def __mul__(self, other):
        return self

    def astype(self, dtype):
        return self


class FakeMangaColorizator:
    responses = []
    devices = []

    def __init__(self, **kwargs):
        self.device = kwargs["device"]
        FakeMangaColorizator.devices.append(str(self.device))

    def set_image(self, image, size, apply_denoise):
        self.image = image

    def colorize(self):
        response = FakeMangaColorizator.responses.pop(0) if FakeMangaColorizator.responses else FakeImage()
        if isinstance(response, Exception):
            raise response
        return response


class MlColorizerDeviceTests(unittest.TestCase):
    def setUp(self):
        self.original_modules = {name: sys.modules.get(name, _MISSING) for name in _MODULES}
        self.original_cuda_preview = os.environ.get("COLORCOMIC_CUDA_PREVIEW")
        os.environ.pop("COLORCOMIC_CUDA_PREVIEW", None)

        fake_cv2 = types.ModuleType("cv2")
        fake_cv2.COLOR_BGR2RGB = 1
        fake_cv2.COLOR_RGB2BGR = 2
        fake_cv2.INTER_AREA = 3
        fake_cv2.INTER_LANCZOS4 = 4
        fake_cv2.cvtColor = lambda image, code: image
        fake_cv2.resize = lambda image, size, interpolation=None: image
        fake_numpy = types.ModuleType("numpy")
        fake_numpy.ndarray = object
        fake_numpy.uint8 = object
        fake_numpy.clip = lambda value, min_value, max_value: value

        fake_torch = types.ModuleType("torch")
        fake_torch.__version__ = "2.5.1+cu121"
        fake_torch.version = types.SimpleNamespace(cuda="12.1")
        fake_torch.device = lambda name: FakeDevice(name)
        self.empty_cache_calls = 0

        def empty_cache():
            self.empty_cache_calls += 1

        fake_torch.cuda = types.SimpleNamespace(
            is_available=lambda: True,
            device_count=lambda: 1,
            get_device_properties=lambda index: types.SimpleNamespace(
                name="NVIDIA Test GPU",
                total_memory=8 * 1024**3,
            ),
            empty_cache=empty_cache,
        )
        fake_torch.inference_mode = lambda: FakeInferenceMode()

        fake_colorizator = types.ModuleType("vendor.manga_colorization_v2.colorizator")
        FakeMangaColorizator.responses = []
        FakeMangaColorizator.devices = []
        fake_colorizator.MangaColorizator = FakeMangaColorizator

        sys.modules["cv2"] = fake_cv2
        sys.modules["numpy"] = fake_numpy
        sys.modules["torch"] = fake_torch
        sys.modules["vendor.manga_colorization_v2.colorizator"] = fake_colorizator
        sys.modules.pop("core.ml_colorizer", None)
        self.ml_colorizer = importlib.import_module("core.ml_colorizer")

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

    def test_auto_colorizer_uses_centralized_device_resolution(self):
        calls = []

        def fake_detect(torch_module):
            calls.append(("detect", torch_module.__name__))
            return {"cuda_available": True}

        def fake_resolve(requested_device, *, capabilities, official_cpu_build):
            calls.append(("resolve", requested_device, capabilities, official_cpu_build))
            return {"resolved_device": "cpu", "cuda_available": True}

        self.ml_colorizer.detect_device_capabilities = fake_detect
        self.ml_colorizer.is_official_cpu_build = lambda: True
        self.ml_colorizer.resolve_compute_device = fake_resolve

        colorizer = self.ml_colorizer.MangaColorizer(device="auto")

        self.assertEqual(colorizer.device_name, "cpu")
        self.assertTrue(colorizer.cuda_available)
        self.assertEqual(calls, [
            ("detect", "torch"),
            ("resolve", "auto", {"cuda_available": True}, True),
        ])

    def test_official_cpu_build_resolves_auto_to_cpu(self):
        colorizer = self.ml_colorizer.MangaColorizer(device="auto")

        self.assertEqual(colorizer.device_name, "cpu")
        self.assertTrue(colorizer.cuda_available)

    def test_cuda_preview_path_uses_helper_without_changing_auto_default(self):
        os.environ["COLORCOMIC_CUDA_PREVIEW"] = "1"

        auto_colorizer = self.ml_colorizer.MangaColorizer(device="auto")
        explicit_cuda = self.ml_colorizer.MangaColorizer(device="cuda")

        self.assertEqual(auto_colorizer.device_name, "cpu")
        self.assertEqual(explicit_cuda.device_name, "cuda")

    def test_cuda_oom_falls_back_to_cpu_and_records_reason(self):
        os.environ["COLORCOMIC_CUDA_PREVIEW"] = "1"
        FakeMangaColorizator.responses = [
            RuntimeError("CUDA out of memory"),
            FakeImage(),
        ]
        colorizer = self.ml_colorizer.MangaColorizer(device="cuda")

        result = colorizer.colorize(FakeImage())

        self.assertIsInstance(result, FakeImage)
        self.assertEqual(colorizer.device_name, "cpu")
        self.assertEqual(colorizer.fallback_reason, "cuda_out_of_memory")
        self.assertEqual(FakeMangaColorizator.devices, ["cuda", "cpu"])
        self.assertEqual(self.empty_cache_calls, 1)

    def test_cuda_runtime_failure_falls_back_to_cpu_and_records_reason(self):
        os.environ["COLORCOMIC_CUDA_PREVIEW"] = "1"
        FakeMangaColorizator.responses = [
            RuntimeError("CUDA runtime error: driver shutting down"),
            FakeImage(),
        ]
        colorizer = self.ml_colorizer.MangaColorizer(device="cuda")

        result = colorizer.colorize(FakeImage())

        self.assertIsInstance(result, FakeImage)
        self.assertEqual(colorizer.device_name, "cpu")
        self.assertEqual(colorizer.fallback_reason, "cuda_runtime_failure")
        self.assertEqual(FakeMangaColorizator.devices, ["cuda", "cpu"])

    def test_official_cpu_mode_does_not_use_cuda_fallback(self):
        FakeMangaColorizator.responses = [RuntimeError("CUDA out of memory")]
        colorizer = self.ml_colorizer.MangaColorizer(device="cuda")

        with self.assertRaises(RuntimeError):
            colorizer.colorize(FakeImage())

        self.assertEqual(colorizer.device_name, "cpu")
        self.assertIsNone(colorizer.fallback_reason)
        self.assertEqual(FakeMangaColorizator.devices, ["cpu"])

    def test_switch_device_clears_stale_fallback_reason(self):
        os.environ["COLORCOMIC_CUDA_PREVIEW"] = "1"
        colorizer = self.ml_colorizer.MangaColorizer(device="cpu")
        colorizer.fallback_reason = "cuda_out_of_memory"

        colorizer.switch_device("cuda")

        self.assertEqual(colorizer.device_name, "cuda")
        self.assertIsNone(colorizer.fallback_reason)
        self.assertEqual(FakeMangaColorizator.devices, ["cpu", "cuda"])


if __name__ == "__main__":
    unittest.main()
