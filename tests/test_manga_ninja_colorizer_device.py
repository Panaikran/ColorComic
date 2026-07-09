import importlib
import os
import sys
import types
import unittest


_MISSING = object()
_MODULES = (
    "cv2",
    "numpy",
    "PIL",
    "PIL.Image",
    "torch",
    "core.manga_ninja_colorizer",
)


class FakeDevice:
    def __init__(self, name):
        self.name = name
        self.type = name

    def __str__(self):
        return self.name


class FakeInferenceMode:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeImage:
    shape = (8, 8, 3)

    def __getitem__(self, key):
        return self


class FakePipeline:
    def __init__(self, response):
        self.response = response

    def __call__(self, **kwargs):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class MangaNinjaColorizerDeviceTests(unittest.TestCase):
    def setUp(self):
        self.original_modules = {name: sys.modules.get(name, _MISSING) for name in _MODULES}
        self.original_cuda_preview = os.environ.get("COLORCOMIC_CUDA_PREVIEW")
        os.environ.pop("COLORCOMIC_CUDA_PREVIEW", None)

        fake_cv2 = types.ModuleType("cv2")
        fake_cv2.COLOR_RGB2BGR = 1
        fake_cv2.INTER_AREA = 2
        fake_cv2.INTER_LANCZOS4 = 3
        fake_cv2.cvtColor = lambda image, code: image
        fake_cv2.resize = lambda image, size, interpolation=None: image
        fake_numpy = types.ModuleType("numpy")
        fake_numpy.ndarray = object
        fake_pil = types.ModuleType("PIL")
        fake_pil_image = types.ModuleType("PIL.Image")
        fake_pil_image.fromarray = lambda image: image
        fake_pil.Image = fake_pil_image

        fake_torch = types.ModuleType("torch")
        fake_torch.__version__ = "2.5.1+cu121"
        fake_torch.version = types.SimpleNamespace(cuda="12.1")
        fake_torch.device = lambda name: FakeDevice(name)
        fake_torch.inference_mode = lambda: FakeInferenceMode()
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

        sys.modules["cv2"] = fake_cv2
        sys.modules["numpy"] = fake_numpy
        sys.modules["PIL"] = fake_pil
        sys.modules["PIL.Image"] = fake_pil_image
        sys.modules["torch"] = fake_torch
        sys.modules.pop("core.manga_ninja_colorizer", None)
        self.colorizer_module = importlib.import_module("core.manga_ninja_colorizer")
        self.colorizer_module.MangaNinjaColorizer._load_pipeline = lambda instance: None

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

    def test_reference_colorizer_uses_centralized_device_resolution(self):
        calls = []

        def fake_detect(torch_module):
            calls.append(("detect", torch_module.__name__))
            return {"cuda_available": True}

        def fake_resolve(requested_device, *, capabilities, official_cpu_build):
            calls.append(("resolve", requested_device, capabilities, official_cpu_build))
            return {"resolved_device": "cpu", "cuda_available": True}

        self.colorizer_module.detect_device_capabilities = fake_detect
        self.colorizer_module.is_official_cpu_build = lambda: True
        self.colorizer_module.resolve_compute_device = fake_resolve

        colorizer = self.colorizer_module.MangaNinjaColorizer(device="auto")

        self.assertEqual(colorizer.device_name, "cpu")
        self.assertTrue(colorizer.cuda_available)
        self.assertEqual(calls, [
            ("detect", "torch"),
            ("resolve", "auto", {"cuda_available": True}, True),
        ])

    def test_official_cpu_build_resolves_reference_mode_to_cpu(self):
        colorizer = self.colorizer_module.MangaNinjaColorizer(device="cuda")

        self.assertEqual(colorizer.device_name, "cpu")
        self.assertTrue(colorizer.cuda_available)

    def test_cuda_preview_path_uses_helper_without_changing_auto_default(self):
        os.environ["COLORCOMIC_CUDA_PREVIEW"] = "1"

        auto_colorizer = self.colorizer_module.MangaNinjaColorizer(device="auto")
        explicit_cuda = self.colorizer_module.MangaNinjaColorizer(device="cuda")

        self.assertEqual(auto_colorizer.device_name, "cpu")
        self.assertEqual(explicit_cuda.device_name, "cuda")

    def test_cuda_oom_during_reference_model_load_records_failure_and_cleans_up(self):
        os.environ["COLORCOMIC_CUDA_PREVIEW"] = "1"
        captured = {}

        def fail_load(instance):
            captured["instance"] = instance
            instance._pipeline = object()
            raise RuntimeError("CUDA out of memory")

        self.colorizer_module.MangaNinjaColorizer._load_pipeline = fail_load

        with self.assertRaises(RuntimeError):
            self.colorizer_module.MangaNinjaColorizer(device="cuda")

        colorizer = captured["instance"]
        self.assertEqual(colorizer.failure_reason, "cuda_out_of_memory")
        self.assertIsNone(colorizer._pipeline)
        self.assertEqual(self.empty_cache_calls, 1)

    def test_cuda_runtime_failure_during_reference_inference_records_failure_without_retry(self):
        os.environ["COLORCOMIC_CUDA_PREVIEW"] = "1"
        colorizer = self.colorizer_module.MangaNinjaColorizer(
            device="cuda",
            config=types.SimpleNamespace(MANGANINJA_DENOISE_STEPS=1),
        )
        colorizer._pipeline = FakePipeline(RuntimeError("CUDA runtime error: launch failed"))

        with self.assertRaises(RuntimeError):
            colorizer.colorize(FakeImage(), reference_image=FakeImage())

        self.assertEqual(colorizer.device_name, "cuda")
        self.assertEqual(colorizer.failure_reason, "cuda_runtime_failure")
        self.assertEqual(self.empty_cache_calls, 1)

    def test_cpu_reference_mode_is_unaffected(self):
        colorizer = self.colorizer_module.MangaNinjaColorizer(device="cpu")

        self.assertEqual(colorizer.device_name, "cpu")
        self.assertIsNone(colorizer.failure_reason)
        self.assertEqual(self.empty_cache_calls, 0)


if __name__ == "__main__":
    unittest.main()
