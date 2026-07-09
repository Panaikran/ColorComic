import io
import types
import unittest
from contextlib import redirect_stdout

from scripts.verify_dependency_imports import _print_torch_cuda_info


class VerifyDependencyImportsTests(unittest.TestCase):
    def test_torch_cuda_info_reports_cpu_safe_defaults(self):
        torch = types.SimpleNamespace(
            __version__="2.3.1+cpu",
            version=types.SimpleNamespace(cuda=None),
            cuda=types.SimpleNamespace(is_available=lambda: False),
        )

        output = io.StringIO()
        with redirect_stdout(output):
            _print_torch_cuda_info(torch)

        text = output.getvalue()
        self.assertIn("torch CUDA build: none", text)
        self.assertIn("CUDA available: False", text)
        self.assertIn("CUDA GPUs: none", text)

    def test_torch_cuda_info_reports_gpu_names_and_vram(self):
        torch = types.SimpleNamespace(
            __version__="2.3.1+cu121",
            version=types.SimpleNamespace(cuda="12.1"),
            cuda=types.SimpleNamespace(
                is_available=lambda: True,
                device_count=lambda: 1,
                get_device_properties=lambda index: types.SimpleNamespace(
                    name="NVIDIA Test GPU",
                    total_memory=8 * 1024**3,
                ),
            ),
        )

        output = io.StringIO()
        with redirect_stdout(output):
            _print_torch_cuda_info(torch)

        text = output.getvalue()
        self.assertIn("torch CUDA build: 12.1", text)
        self.assertIn("CUDA available: True", text)
        self.assertIn("CUDA GPU 0: NVIDIA Test GPU (8.0 GiB)", text)


if __name__ == "__main__":
    unittest.main()
