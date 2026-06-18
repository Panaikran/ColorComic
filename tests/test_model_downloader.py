import os
import sys
import tempfile
import types
import unittest


class MangaNinjaDownloadTests(unittest.TestCase):
    def test_reference_mode_download_uses_correct_huggingface_repo_id(self):
        from core.model_downloader import ensure_manganinja_downloaded

        calls = []

        def fake_hf_hub_download(repo_id, filename, local_dir):
            calls.append(
                {
                    "repo_id": repo_id,
                    "filename": filename,
                    "local_dir": local_dir,
                }
            )
            path = os.path.join(local_dir, filename)
            with open(path, "wb") as handle:
                handle.write(b"test")
            return path

        fake_huggingface_hub = types.SimpleNamespace(hf_hub_download=fake_hf_hub_download)
        original_huggingface_hub = sys.modules.get("huggingface_hub")

        with tempfile.TemporaryDirectory() as temp_dir:
            class TestConfig:
                MANGANINJA_WEIGHTS_DIR = temp_dir
                MANGANINJA_DENOISING_UNET = os.path.join(temp_dir, "denoising_unet.pth")
                MANGANINJA_REFERENCE_UNET = os.path.join(temp_dir, "reference_unet.pth")
                MANGANINJA_POINTNET = os.path.join(temp_dir, "point_net.pth")
                MANGANINJA_CONTROLNET = os.path.join(temp_dir, "controlnet.pth")
                MANGANINJA_HF_REPO = "Johanan0528/MangaNinjia"

            try:
                sys.modules["huggingface_hub"] = fake_huggingface_hub
                ensure_manganinja_downloaded(TestConfig)
            finally:
                if original_huggingface_hub is None:
                    sys.modules.pop("huggingface_hub", None)
                else:
                    sys.modules["huggingface_hub"] = original_huggingface_hub

        self.assertEqual(len(calls), 4)
        self.assertEqual(
            {call["repo_id"] for call in calls},
            {"Johanan0528/MangaNinjia"},
        )
        self.assertEqual(
            [call["filename"] for call in calls],
            [
                "denoising_unet.pth",
                "reference_unet.pth",
                "point_net.pth",
                "controlnet.pth",
            ],
        )


if __name__ == "__main__":
    unittest.main()
