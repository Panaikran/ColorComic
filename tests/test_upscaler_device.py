import unittest

from core import upscaler


class FakeDevice:
    def __init__(self, name):
        self.name = name
        self.type = name

    def __str__(self):
        return self.name


class UpscalerDeviceTests(unittest.TestCase):
    def setUp(self):
        self.original_detect = upscaler.detect_device_capabilities
        self.original_resolve = upscaler.resolve_compute_device
        self.original_is_official_cpu_build = upscaler.is_official_cpu_build
        self.original_torch_device = upscaler.torch.device
        upscaler.torch.device = lambda name: FakeDevice(name)

    def tearDown(self):
        upscaler.detect_device_capabilities = self.original_detect
        upscaler.resolve_compute_device = self.original_resolve
        upscaler.is_official_cpu_build = self.original_is_official_cpu_build
        upscaler.torch.device = self.original_torch_device

    def test_upscaler_uses_centralized_device_resolution(self):
        calls = []

        def fake_detect(torch_module):
            calls.append(("detect", torch_module.__name__))
            return {"cuda_available": True}

        def fake_resolve(requested_device, *, capabilities, official_cpu_build):
            calls.append(("resolve", requested_device, capabilities, official_cpu_build))
            return {"resolved_device": "cpu"}

        upscaler.detect_device_capabilities = fake_detect
        upscaler.resolve_compute_device = fake_resolve
        upscaler.is_official_cpu_build = lambda: True

        instance = upscaler.Upscaler(model_path="weights.pth", model_url="https://example.invalid/model.pth")

        self.assertEqual(str(instance._resolve_device()), "cpu")
        self.assertEqual(calls, [
            ("detect", "torch"),
            ("resolve", "auto", {"cuda_available": True}, True),
        ])

    def test_official_cpu_build_resolves_upscaler_to_cpu(self):
        instance = upscaler.Upscaler(
            model_path="weights.pth",
            model_url="https://example.invalid/model.pth",
            device="cuda",
        )

        self.assertEqual(str(instance._resolve_device()), "cpu")

    def test_cuda_preview_path_can_resolve_explicit_cuda(self):
        upscaler.is_official_cpu_build = lambda: False
        upscaler.detect_device_capabilities = lambda torch_module: {"cuda_available": True}

        instance = upscaler.Upscaler(
            model_path="weights.pth",
            model_url="https://example.invalid/model.pth",
            device="cuda",
        )

        self.assertEqual(str(instance._resolve_device()), "cuda")


if __name__ == "__main__":
    unittest.main()
