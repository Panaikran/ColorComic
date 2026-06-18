import importlib
import os
import shutil
import sys
import unittest


class RuntimePathTests(unittest.TestCase):
    def test_config_uses_local_app_data_for_writable_paths(self):
        temp_dir = os.path.join(os.getcwd(), "tests")
        app_data = os.path.join(temp_dir, "ColorComic")
        original_local_app_data = os.environ.get("LOCALAPPDATA")
        cache_env_names = (
            "HF_HOME",
            "HF_HUB_CACHE",
            "HUGGINGFACE_HUB_CACHE",
            "TRANSFORMERS_CACHE",
            "DIFFUSERS_CACHE",
        )
        original_cache_env = {name: os.environ.get(name) for name in cache_env_names}
        try:
            shutil.rmtree(app_data, ignore_errors=True)
            os.environ["LOCALAPPDATA"] = temp_dir
            sys.modules.pop("core.paths", None)
            sys.modules.pop("config", None)
            config = importlib.import_module("config")

            self.assertEqual(config.Config.RUNTIME_DIR, app_data)
            self.assertEqual(config.Config.UPLOAD_FOLDER, os.path.join(app_data, "uploads"))
            self.assertEqual(config.Config.OUTPUT_FOLDER, os.path.join(app_data, "output"))
            self.assertEqual(
                config.Config.WEIGHTS_DIR,
                os.path.join(app_data, "models", "weights"),
            )
            self.assertEqual(
                config.Config.MANGANINJA_WEIGHTS_DIR,
                os.path.join(app_data, "models", "weights", "manganinja"),
            )
            self.assertEqual(
                config.Config.HF_HOME,
                os.path.join(app_data, "cache", "huggingface"),
            )
            self.assertEqual(
                config.Config.HF_HUB_CACHE,
                os.path.join(app_data, "cache", "huggingface", "hub"),
            )
            self.assertEqual(config.Config.LOG_DIR, os.path.join(app_data, "logs"))
            self.assertEqual(config.Config.CONFIG_FILE, os.path.join(app_data, "config", ".env"))
            self.assertEqual(os.environ["HF_HOME"], config.Config.HF_HOME)
            self.assertEqual(os.environ["HF_HUB_CACHE"], config.Config.HF_HUB_CACHE)

            for directory in (
                config.Config.UPLOAD_FOLDER,
                config.Config.OUTPUT_FOLDER,
                config.Config.WEIGHTS_DIR,
                config.Config.MANGANINJA_WEIGHTS_DIR,
                config.Config.HF_HOME,
                config.Config.LOG_DIR,
                config.Config.CONFIG_DIR,
            ):
                self.assertTrue(os.path.isdir(directory), directory)
        finally:
            if original_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = original_local_app_data
            for name, value in original_cache_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            sys.modules.pop("config", None)
            sys.modules.pop("core.paths", None)
            shutil.rmtree(app_data, ignore_errors=True)
