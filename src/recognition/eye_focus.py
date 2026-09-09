"""
识别工作流·眼部合焦比例（核心价值层）
用"眼部清晰度 / 全图最锐点清晰度"的比例，而不是眼部清晰度的绝对值——
这是摄影评审圈的真实共识标准，规避了拍摄条件差异带来的阈值漂移（见架构文档）。
"""
from typing import Optional

import numpy as np

from .quality import sharpness_score, full_frame_max_sharpness

BBox = tuple[int, int, int, int]


def eye_sharpness_ratio(image_bgr: np.ndarray, eye_bbox: Optional[BBox]) -> Optional[float]:
    """
    eye_bbox 来自 detect.py 的眼部关键点外扩框。
    没检出眼部时返回 None，不做任何猜测性填充——
    这种情况必须落到"待定"，不能被当成"合格"或"不合格"处理。
    """
    if eye_bbox is None:
        return None

    eye_sharp = sharpness_score(image_bgr, eye_bbox)
    frame_max_sharp = full_frame_max_sharpness(image_bgr)

    if frame_max_sharp <= 0:
        return None

    ratio = eye_sharp / frame_max_sharp
    return float(min(ratio, 1.0))


def expand_point_to_bbox(x: int, y: int, image_w: int, image_h: int, box_frac: float = 0.03) -> BBox:
    """
    把关键点坐标(眼睛的一个点)外扩成一个正方形小框，用于清晰度测量。
    box_frac：框边长占图像短边的比例，默认3%——对大多数鸟类特写照片够用，
    画面里鸟很小的情况下可以调大这个值。
    """
    side = max(int(min(image_w, image_h) * box_frac), 8)  # 至少8像素，避免框太小导致计算失真
    half = side // 2
    box_x = max(0, x - half)
    box_y = max(0, y - half)
    return (box_x, box_y, side, side)
