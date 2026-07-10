import importlib
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import core.paths


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


class ConfigEnvironmentTests(unittest.TestCase):
    config_names = (
        "SECRET_KEY",
        "COLORCOMIC_DEVICE",
        "COLOR_TRANSFER_STRENGTH",
    )

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = os.path.join(self.temp_dir.name, "project")
        self.runtime_dir = os.path.join(self.temp_dir.name, "runtime", "ColorComic")
        self.original_environment = {
            name: os.environ.get(name)
            for name in (*self.config_names, "HF_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE", "DIFFUSERS_CACHE")
        }
        self.original_config = sys.modules.get("config")
        os.makedirs(os.path.join(self.runtime_dir, "config"))
        os.makedirs(self.base_dir)
        for name in self.config_names:
            os.environ.pop(name, None)

    def tearDown(self):
        sys.modules.pop("config", None)
        if self.original_config is not None:
            sys.modules["config"] = self.original_config
        for name, value in self.original_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.temp_dir.cleanup()

    def write_env(self, path, **values):
        with open(path, "w", encoding="utf-8") as handle:
            for name, value in values.items():
                handle.write(f"{name}={value}\n")

    def import_config(self):
        sys.modules.pop("config", None)
        with mock.patch.object(core.paths, "get_app_base_dir", return_value=self.base_dir), mock.patch.object(
            core.paths, "get_runtime_dir", return_value=self.runtime_dir
        ):
            return importlib.import_module("config")

    def test_runtime_config_loads_before_config_values_and_overrides_project_fallback(self):
        self.write_env(
            os.path.join(self.base_dir, ".env"),
            SECRET_KEY="project-secret",
            COLORCOMIC_DEVICE="auto",
            COLOR_TRANSFER_STRENGTH="0.1",
        )
        self.write_env(
            os.path.join(self.runtime_dir, "config", ".env"),
            SECRET_KEY="runtime-secret",
            COLORCOMIC_DEVICE="cpu",
            COLOR_TRANSFER_STRENGTH="0.2",
        )

        config = self.import_config()

        self.assertEqual(config.Config.RUNTIME_DIR, self.runtime_dir)
        self.assertEqual(config.Config.SECRET_KEY, "runtime-secret")
        self.assertEqual(config.Config.ML_DEVICE, "cpu")
        self.assertEqual(config.Config.COLOR_TRANSFER_STRENGTH, 0.2)

    def test_explicit_environment_values_override_dotenv_files(self):
        self.write_env(
            os.path.join(self.base_dir, ".env"),
            SECRET_KEY="project-secret",
            COLORCOMIC_DEVICE="auto",
            COLOR_TRANSFER_STRENGTH="0.1",
        )
        self.write_env(
            os.path.join(self.runtime_dir, "config", ".env"),
            SECRET_KEY="runtime-secret",
            COLORCOMIC_DEVICE="cpu",
            COLOR_TRANSFER_STRENGTH="0.2",
        )
        os.environ["SECRET_KEY"] = "environment-secret"
        os.environ["COLORCOMIC_DEVICE"] = "cuda"
        os.environ["COLOR_TRANSFER_STRENGTH"] = "0.3"

        config = self.import_config()

        self.assertEqual(config.Config.SECRET_KEY, "environment-secret")
        self.assertEqual(config.Config.ML_DEVICE, "cuda")
        self.assertEqual(config.Config.COLOR_TRANSFER_STRENGTH, 0.3)
