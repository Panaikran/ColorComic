"""Investigation coverage for supported mc-v2 Auto-mode page inputs."""

import os
import tempfile
import threading
import unittest

import cv2
import fitz
import numpy as np
import torch

from core.ml_colorizer import MangaColorizer
from core.pdf_handler import extract_pages
from vendor.manga_colorization_v2.colorizator import MangaColorizator
from vendor.manga_colorization_v2.denoising.denoiser import FFDNetDenoiser


class RecordingColorizator:
    def set_image(self, image, size, apply_denoise):
        self.image = image
        self.size = size
        self.apply_denoise = apply_denoise

    def colorize(self):
        return np.full((576, 576, 3), 0.5, dtype=np.float32)


class RecordingDenoiser:
    def get_denoised_image(self, image, sigma):
        self.image = image
        self.sigma = sigma
        return image


class ZeroNoiseModel:
    def __call__(self, image, sigma):
        return torch.zeros_like(image)


class McV2NormalizationInvestigationTests(unittest.TestCase):
    def test_rendered_pdf_page_loads_as_uint8_bgr_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "input.pdf")
            pages_dir = os.path.join(temp_dir, "pages")
            document = fitz.open()
            page = document.new_page(width=72, height=72)
            page.draw_rect(page.rect, color=(1, 0, 0), fill=(1, 0, 0))
            document.save(pdf_path)
            document.close()

            page_path = extract_pages(pdf_path, pages_dir, dpi=72)[0]
            image = cv2.imread(page_path)

        self.assertEqual(image.dtype, np.uint8)
        self.assertEqual(image.ndim, 3)
        self.assertEqual(image.shape[2], 3)

    def test_manga_colorizer_converts_supported_bgr_uint8_page_to_rgb(self):
        model = RecordingColorizator()
        colorizer = object.__new__(MangaColorizer)
        colorizer._lock = threading.Lock()
        colorizer._model = model
        colorizer.device_name = "cpu"
        bgr = np.array([[[1, 2, 3]]], dtype=np.uint8)

        result = colorizer.colorize(bgr)

        self.assertEqual(model.image.dtype, np.uint8)
        self.assertEqual(model.image.shape, bgr.shape)
        self.assertEqual(model.image[0, 0].tolist(), [3, 2, 1])
        self.assertEqual(model.size, 576)
        self.assertTrue(model.apply_denoise)
        self.assertEqual(result.shape, bgr.shape)
        self.assertEqual(result.dtype, np.uint8)

    def test_set_image_denoises_supported_rgb_page_before_model_resize(self):
        colorizator = object.__new__(MangaColorizator)
        colorizator.device = "cpu"
        colorizator.denoiser = RecordingDenoiser()
        image = np.full((800, 1600, 3), 200, dtype=np.uint8)

        colorizator.set_image(image, size=576, apply_denoise=True)

        self.assertEqual(colorizator.denoiser.image.shape, image.shape)
        self.assertEqual(colorizator.denoiser.image.dtype, np.uint8)
        self.assertEqual(colorizator.denoiser.image.shape[2], 3)
        self.assertEqual(colorizator.current_image.dtype, torch.float32)
        self.assertEqual(colorizator.current_image.shape[1], 1)
        self.assertEqual(colorizator.current_hint.shape[1], 4)

    def test_ffdnet_preprocessing_preserves_supported_uint8_shape_without_axes_error(self):
        denoiser = object.__new__(FFDNetDenoiser)
        denoiser.device = "cpu"
        denoiser.sigma = 25 / 255
        denoiser.model = ZeroNoiseModel()
        image = np.full((33, 35, 3), 200, dtype=np.uint8)

        result = denoiser.get_denoised_image(image)

        self.assertEqual(result.shape, image.shape)
        self.assertEqual(result.dtype, np.uint8)


if __name__ == "__main__":
    unittest.main()
