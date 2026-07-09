import json
import types
import unittest

from core.device_detection import detect_device_capabilities, resolve_compute_device


class DeviceDetectionTests(unittest.TestCase):
    def test_cpu_only_torch_reports_cpu_defaults(self):
        torch = types.SimpleNamespace(
            __version__="2.5.1+cpu",
            version=types.SimpleNamespace(cuda=None),
            cuda=types.SimpleNamespace(is_available=lambda: False),
        )

        capabilities = detect_device_capabilities(torch)

        self.assertEqual(capabilities["current_default_device"], "cpu")
        self.assertTrue(capabilities["cpu_available"])
        self.assertFalse(capabilities["cuda_available"])
        self.assertIsNone(capabilities["cuda_version"])
        self.assertEqual(capabilities["gpus"], [])
        self.assertEqual(capabilities["torch_version"], "2.5.1+cpu")

    def test_cuda_available_reports_gpu_details(self):
        props = types.SimpleNamespace(name="NVIDIA Test GPU", total_memory=8 * 1024**3)
        torch = types.SimpleNamespace(
            __version__="2.5.1+cu121",
            version=types.SimpleNamespace(cuda="12.1"),
            cuda=types.SimpleNamespace(
                is_available=lambda: True,
                device_count=lambda: 1,
                get_device_properties=lambda index: props,
            ),
        )

        capabilities = detect_device_capabilities(torch)

        self.assertTrue(capabilities["cuda_available"])
        self.assertEqual(capabilities["cuda_version"], "12.1")
        self.assertEqual(
            capabilities["gpus"],
            [{
                "index": 0,
                "name": "NVIDIA Test GPU",
                "total_memory_bytes": 8 * 1024**3,
            }],
        )

    def test_cuda_query_failure_is_non_fatal(self):
        def fail_is_available():
            raise RuntimeError("CUDA runtime unavailable")

        torch = types.SimpleNamespace(
            __version__="2.5.1",
            version=types.SimpleNamespace(cuda="12.1"),
            cuda=types.SimpleNamespace(is_available=fail_is_available),
        )

        capabilities = detect_device_capabilities(torch)

        self.assertFalse(capabilities["cuda_available"])
        self.assertEqual(capabilities["gpus"], [])
        self.assertIn("CUDA runtime unavailable", capabilities["cuda_error"])

    def test_capabilities_are_json_serializable(self):
        torch = types.SimpleNamespace(
            __version__="2.5.1+cpu",
            version=types.SimpleNamespace(cuda=None),
            cuda=types.SimpleNamespace(is_available=lambda: False),
        )

        json.dumps(detect_device_capabilities(torch))

    def test_resolver_keeps_official_cpu_build_on_cpu(self):
        result = resolve_compute_device(
            "cpu",
            capabilities={"cuda_available": True},
            official_cpu_build=True,
        )

        self.assertEqual(result["requested_device"], "cpu")
        self.assertEqual(result["resolved_device"], "cpu")
        self.assertEqual(result["fallback_reason"], "official_cpu_build")

    def test_resolver_auto_currently_resolves_to_cpu(self):
        result = resolve_compute_device(
            "auto",
            capabilities={"cuda_available": True},
            official_cpu_build=False,
        )

        self.assertEqual(result["resolved_device"], "cpu")
        self.assertEqual(result["fallback_reason"], "auto_defaults_to_cpu")

    def test_resolver_explicit_cuda_falls_back_on_cpu_build(self):
        result = resolve_compute_device(
            "cuda",
            capabilities={"cuda_available": True},
            official_cpu_build=True,
        )

        self.assertEqual(result["resolved_device"], "cpu")
        self.assertEqual(result["fallback_reason"], "official_cpu_build")

    def test_resolver_explicit_cuda_falls_back_when_unavailable(self):
        result = resolve_compute_device(
            "cuda",
            capabilities={"cuda_available": False},
            official_cpu_build=False,
        )

        self.assertEqual(result["resolved_device"], "cpu")
        self.assertEqual(result["fallback_reason"], "cuda_unavailable")

    def test_resolver_allows_future_cuda_build_when_available(self):
        result = resolve_compute_device(
            "cuda",
            capabilities={"cuda_available": True},
            official_cpu_build=False,
        )

        self.assertEqual(result["resolved_device"], "cuda")
        self.assertIsNone(result["fallback_reason"])

    def test_resolver_result_is_json_serializable(self):
        result = resolve_compute_device(
            "cuda",
            capabilities={"cuda_available": False},
        )

        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
