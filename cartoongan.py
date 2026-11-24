"""CartoonGAN generator (Chen, Lai & Liu, CVPR 2018).

Encoder -> 8 residual blocks -> decoder, matching the layer names in the authors' released
weights (converted to PyTorch by Yijunmaverick/CartoonGAN-Test-Pytorch-Torch).
"""
from __future__ import annotations

from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

RES_BLOCKS = range(4, 12)  # layer names in the checkpoint run from conv04 to conv11


class InstanceNorm(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.scale = nn.Parameter(torch.ones(channels))
        self.shift = nn.Parameter(torch.zeros(channels))

    def forward(self, x):
        return F.instance_norm(x, weight=self.scale, bias=self.shift, eps=1e-9)


class CartoonGANGenerator(nn.Module):
    def __init__(self):
        super().__init__()
        # encoder: full -> 1/2 -> 1/4 resolution
        self.conv01_1 = nn.Conv2d(3, 64, 7, padding=3, padding_mode="reflect")
        self.in01_1 = InstanceNorm(64)
        self.conv02_1 = nn.Conv2d(64, 128, 3, 2, 1)
        self.conv02_2 = nn.Conv2d(128, 128, 3, 1, 1)
        self.in02_1 = InstanceNorm(128)
        self.conv03_1 = nn.Conv2d(128, 256, 3, 2, 1)
        self.conv03_2 = nn.Conv2d(256, 256, 3, 1, 1)
        self.in03_1 = InstanceNorm(256)
        # residual blocks
        for i in RES_BLOCKS:
            for j in (1, 2):
                setattr(self, f"conv{i:02d}_{j}", nn.Conv2d(256, 256, 3, padding=1, padding_mode="reflect"))
                setattr(self, f"in{i:02d}_{j}", InstanceNorm(256))
        # decoder: back to full resolution
        self.deconv01_1 = nn.ConvTranspose2d(256, 128, 3, 2, 1, 1)
        self.deconv01_2 = nn.Conv2d(128, 128, 3, 1, 1)
        self.in12_1 = InstanceNorm(128)
        self.deconv02_1 = nn.ConvTranspose2d(128, 64, 3, 2, 1, 1)
        self.deconv02_2 = nn.Conv2d(64, 64, 3, 1, 1)
        self.in13_1 = InstanceNorm(64)
        self.deconv03_1 = nn.Conv2d(64, 3, 7, padding=3, padding_mode="reflect")

    def forward(self, x):
        y = F.relu(self.in01_1(self.conv01_1(x)))
        y = F.relu(self.in02_1(self.conv02_2(self.conv02_1(y))))
        y = F.relu(self.in03_1(self.conv03_2(self.conv03_1(y))))
        for i in RES_BLOCKS:
            r = F.relu(getattr(self, f"in{i:02d}_1")(getattr(self, f"conv{i:02d}_1")(y)))
            y = getattr(self, f"in{i:02d}_2")(getattr(self, f"conv{i:02d}_2")(r)) + y
        y = F.relu(self.in12_1(self.deconv01_2(self.deconv01_1(y))))
        y = F.relu(self.in13_1(self.deconv02_2(self.deconv02_1(y))))
        return torch.tanh(self.deconv03_1(y))


def load_cartoongan(path: Path, device: torch.device) -> CartoonGANGenerator:
    net = CartoonGANGenerator()
    net.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    return net.to(device).eval()
