import json
import types
import unittest

from core.device_detection import (
    CUDA_PREVIEW_ENV,
    detect_device_capabilities,
    is_official_cpu_build,
    resolve_compute_device,
)


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

    def test_cuda_available_reports_multiple_gpus(self):
        props = [
            types.SimpleNamespace(name="GPU 0", total_memory=8 * 1024**3),
            types.SimpleNamespace(name="GPU 1", total_memory=12 * 1024**3),
        ]
        torch = types.SimpleNamespace(
            __version__="2.5.1+cu121",
            version=types.SimpleNamespace(cuda="12.1"),
            cuda=types.SimpleNamespace(
                is_available=lambda: True,
                device_count=lambda: 2,
                get_device_properties=lambda index: props[index],
            ),
        )

        capabilities = detect_device_capabilities(torch)

        self.assertEqual([gpu["name"] for gpu in capabilities["gpus"]], ["GPU 0", "GPU 1"])
        self.assertEqual(
            [gpu["total_memory_bytes"] for gpu in capabilities["gpus"]],
            [8 * 1024**3, 12 * 1024**3],
        )

    def test_cuda_available_handles_missing_cuda_version(self):
        props = types.SimpleNamespace(name="NVIDIA Test GPU", total_memory=8 * 1024**3)
        torch = types.SimpleNamespace(
            __version__="2.5.1",
            version=types.SimpleNamespace(),
            cuda=types.SimpleNamespace(
                is_available=lambda: True,
                device_count=lambda: 1,
                get_device_properties=lambda index: props,
            ),
        )

        capabilities = detect_device_capabilities(torch)

        self.assertTrue(capabilities["cuda_available"])
        self.assertIsNone(capabilities["cuda_version"])
        self.assertEqual(capabilities["gpus"][0]["name"], "NVIDIA Test GPU")

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

    def test_gpu_memory_query_failure_is_non_fatal(self):
        class BrokenProps:
            name = "Broken GPU"

            @property
            def total_memory(self):
                raise RuntimeError("memory query failed")

        torch = types.SimpleNamespace(
            __version__="2.5.1+cu121",
            version=types.SimpleNamespace(cuda="12.1"),
            cuda=types.SimpleNamespace(
                is_available=lambda: True,
                device_count=lambda: 1,
                get_device_properties=lambda index: BrokenProps(),
            ),
        )

        capabilities = detect_device_capabilities(torch)

        self.assertTrue(capabilities["cuda_available"])
        self.assertEqual(capabilities["gpus"], [])
        self.assertIn("memory query failed", capabilities["cuda_error"])

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

    def test_resolver_never_raises_and_returns_supported_device(self):
        capability_sets = [
            {},
            {"cuda_available": False},
            {"cuda_available": True},
            {"cuda_available": False, "cuda_error": "runtime unavailable"},
        ]

        for capabilities in capability_sets:
            for requested in (None, "auto", "cpu", "cuda", "bogus"):
                with self.subTest(capabilities=capabilities, requested=requested):
                    result = resolve_compute_device(
                        requested,
                        capabilities=capabilities,
                        official_cpu_build=False,
                    )
                    self.assertIn(result["resolved_device"], {"cpu", "cuda"})

    def test_official_cpu_build_never_resolves_to_cuda(self):
        for requested in (None, "auto", "cpu", "cuda", "bogus"):
            with self.subTest(requested=requested):
                result = resolve_compute_device(
                    requested,
                    capabilities={"cuda_available": True},
                    official_cpu_build=True,
                )
                self.assertEqual(result["resolved_device"], "cpu")
                self.assertEqual(result["fallback_reason"], "official_cpu_build")

    def test_runtime_switch_defaults_to_official_cpu_build(self):
        self.assertTrue(is_official_cpu_build({}))

    def test_runtime_switch_accepts_cuda_preview_values(self):
        for value in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(value=value):
                self.assertFalse(is_official_cpu_build({CUDA_PREVIEW_ENV: value}))

    def test_runtime_switch_keeps_cpu_build_for_disabled_values(self):
        for value in ("", "0", "false", "no", "off"):
            with self.subTest(value=value):
                self.assertTrue(is_official_cpu_build({CUDA_PREVIEW_ENV: value}))


if __name__ == "__main__":
    unittest.main()
