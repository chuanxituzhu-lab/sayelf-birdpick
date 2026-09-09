"""
识别工作流·技术质量测量
清晰度：拉普拉斯方差。曝光：只统计主体区域，不看全图。
这两个函数只产出数字，不做任何"合格/不合格"的判断——
分级逻辑统一放在 pipeline.py 里，方便以后用历史标注数据整体校准阈值。
"""
from typing import Optional

import cv2
import numpy as np

BBox = tuple[int, int, int, int]  # x, y, w, h


def _crop(image_bgr: np.ndarray, roi: Optional[BBox]) -> np.ndarray:
    if roi is None:
        return image_bgr
    x, y, w, h = roi
    x, y = max(0, x), max(0, y)
    crop = image_bgr[y:y + h, x:x + w]
    return crop if crop.size > 0 else image_bgr


def sharpness_score(image_bgr: np.ndarray, roi: Optional[BBox] = None) -> float:
    """
    拉普拉斯方差，数值越高越清晰。
    roi 提供时只在该区域内计算（比如只测主体框内的清晰度）。
    没有固定的"合格线"——同一批照片内部相对比较，
    或用历史标注数据校准出具体阈值（见架构文档 3.2）。
    """
    crop = _crop(image_bgr, roi)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return float(laplacian.var())


def exposure_flag(
    image_bgr: np.ndarray,
    roi: Optional[BBox] = None,
    dark_thresh: int = 15,
    bright_thresh: int = 240,
    dark_ratio_limit: float = 0.15,
    bright_ratio_limit: float = 0.15,
) -> str:
    """
    只统计主体区域(roi)的死黑/死白像素占比，不看全图——
    背景过曝(比如逆光天空)不算数，这是主动设计，不是遗漏。
    返回 "normal" / "underexposed" / "overexposed"。
    """
    crop = _crop(image_bgr, roi)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    total = gray.size
    dark_ratio = float(np.sum(gray < dark_thresh)) / total
    bright_ratio = float(np.sum(gray > bright_thresh)) / total

    if dark_ratio > dark_ratio_limit:
        return "underexposed"
    if bright_ratio > bright_ratio_limit:
        return "overexposed"
    return "normal"


def full_frame_max_sharpness(image_bgr: np.ndarray, grid: int = 4) -> float:
    """
    把全图切成 grid x grid 个格子，取清晰度最高格子的分数，
    作为"全图最锐点"参考值——eye_focus.py 算眼部合焦比例时会用到。
    """
    h, w = image_bgr.shape[:2]
    cell_h, cell_w = max(1, h // grid), max(1, w // grid)
    best = 0.0
    for i in range(grid):
        for j in range(grid):
            roi = (j * cell_w, i * cell_h, cell_w, cell_h)
            s = sharpness_score(image_bgr, roi)
            if s > best:
                best = s
    return best
