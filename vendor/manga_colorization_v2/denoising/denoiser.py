"""
Denoise an image with the FFDNet denoising method

Copyright (C) 2018, Matias Tassano <matias.tassano@parisdescartes.fr>

This program is free software: you can use, modify and/or
redistribute it under the terms of the GNU General Public
License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later
version. You should have received a copy of this license along
this program. If not, see <http://www.gnu.org/licenses/>.
"""
import os

import numpy as np
import cv2
import torch
from .models import FFDNet
from .utils import normalize, variable_to_cv2_image, remove_dataparallel_wrapper, is_rgb


class FFDNetDenoiser:
    def __init__(self, _device, _sigma=25, _weights_dir='denoising/models/', _in_ch=3):
        self.sigma = _sigma / 255
        self.weights_dir = _weights_dir
        self.channels = _in_ch
        self.device = torch.device(_device) if isinstance(_device, str) else _device

        self.model = FFDNet(num_input_channels=_in_ch)
        self.load_weights()
        self.model.eval()

    def load_weights(self):
        weights_name = 'net_rgb.pth' if self.channels == 3 else 'net_gray.pth'
        weights_path = os.path.join(self.weights_dir, weights_name)
        state_dict = torch.load(weights_path, map_location='cpu',
                                weights_only=False)
        # Weights were saved wrapped in DataParallel; load into the bare model
        # (no DataParallel — it only adds scatter/gather overhead on 1 GPU).
        state_dict = remove_dataparallel_wrapper(state_dict)
        self.model.load_state_dict(state_dict)
        self.model = self.model.to(self.device)

    def to(self, device):
        """Move the denoiser between devices (used for CPU parking)."""
        self.device = torch.device(device) if isinstance(device, str) else device
        self.model = self.model.to(self.device)
        return self

    @torch.no_grad()
    def get_denoised_image(self, imorig, sigma=None, max_edge=1200):

        if sigma is not None:
            cur_sigma = sigma / 255
        else:
            cur_sigma = self.sigma

        if len(imorig.shape) < 3 or imorig.shape[2] == 1:
            imorig = np.repeat(np.expand_dims(imorig, 2), 3, 2)

        imorig = imorig[..., :3]

        if max_edge and max(imorig.shape[0], imorig.shape[1]) > max_edge:
            ratio = max(imorig.shape[0], imorig.shape[1]) / max_edge
            imorig = cv2.resize(imorig, (int(imorig.shape[1] / ratio), int(imorig.shape[0] / ratio)),
                                interpolation=cv2.INTER_AREA)

        imorig = imorig.transpose(2, 0, 1)

        if (imorig.max() > 1.2):
            imorig = normalize(imorig)
        imorig = np.expand_dims(imorig, 0)

        # Handle odd sizes
        expanded_h = False
        expanded_w = False
        sh_im = imorig.shape
        if sh_im[2] % 2 == 1:
            expanded_h = True
            imorig = np.concatenate((imorig, imorig[:, :, -1, :][:, :, np.newaxis, :]), axis=2)

        if sh_im[3] % 2 == 1:
            expanded_w = True
            imorig = np.concatenate((imorig, imorig[:, :, :, -1][:, :, :, np.newaxis]), axis=3)

        imnoisy = torch.from_numpy(np.ascontiguousarray(imorig)).float().to(self.device)
        nsigma = torch.tensor([cur_sigma], dtype=torch.float32, device=self.device)

        # Estimate noise and subtract it from the input image
        im_noise_estim = self.model(imnoisy, nsigma)
        outim = torch.clamp(imnoisy - im_noise_estim, 0., 1.)

        if expanded_h:
            outim = outim[:, :, :-1, :]

        if expanded_w:
            outim = outim[:, :, :, :-1]

        return variable_to_cv2_image(outim)
