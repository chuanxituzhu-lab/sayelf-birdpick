"""
识别工作流·主体检测 + 眼部关键点检测
封装 RF-DETR 调用。检测模型默认加载COCO预训练权重(Apache-2.0，可商用起点，
COCO的80个类别里本来就有"bird")；关键点模型(眼部定位)训练完成前，
detect_eye_point 会直接返回 None，对应 photos 表里 eye_bbox 留空，
不做任何猜测性填充。

微调后的权重训练完成后，把对应的环境变量指向 checkpoint 路径即可，
其余调用代码不用改——这也是当初选RF-DETR而不是YOLO的意义所在：
权重文件是否公开完全由你自己决定，不受协议约束。

预测接口(model.predict 返回值的字段名 xyxy/confidence/class_id)
已对照 RF-DETR 官方文档核实；关键点部分(RFDETRKeypointPreview)是
官方标注的 early-access 预览功能，字段名以未来实际安装的版本为准，
如果报错，先看 https://rfdetr.roboflow.com 的最新关键点文档。
"""
import os
from dataclasses import dataclass
from typing import Optional

import cv2
from rfdetr import RFDETRBase

try:
    from rfdetr import RFDETRKeypointPreview
except ImportError:
    RFDETRKeypointPreview = None  # 未安装 rfdetr[train,visual] 时，关键点功能不可用

DETECTION_MODEL_PATH = os.environ.get("SAYELF_BIRD_DETECTION_MODEL_PATH")
KEYPOINT_MODEL_PATH = os.environ.get("SAYELF_BIRD_EYE_MODEL_PATH")

_detection_model = None
_keypoint_model = None


def get_detection_model() -> RFDETRBase:
    global _detection_model
    if _detection_model is None:
        if DETECTION_MODEL_PATH and os.path.exists(DETECTION_MODEL_PATH):
            _detection_model = RFDETRBase(pretrain_weights=DETECTION_MODEL_PATH)
        else:
            _detection_model = RFDETRBase()  # 退回COCO预训练权重
    return _detection_model


def get_keypoint_model():
    global _keypoint_model
    if RFDETRKeypointPreview is None:
        return None
    if _keypoint_model is None:
        if KEYPOINT_MODEL_PATH and os.path.exists(KEYPOINT_MODEL_PATH):
            _keypoint_model = RFDETRKeypointPreview(pretrain_weights=KEYPOINT_MODEL_PATH)
        else:
            return None  # 没有微调过的眼部模型时，不用未针对鸟类训练的通用关键点模型
    return _keypoint_model


@dataclass
class Detection:
    confidence: float
    bbox: tuple[int, int, int, int]  # x, y, w, h
    class_name: str


def detect_subject(image_path: str, confidence_threshold: float = 0.3) -> Optional[Detection]:
    """
    对一张照片跑主体检测，返回置信度最高的一个检测结果。
    confidence_threshold 故意设得比常见的0.5低——鸟是小目标又经常运动模糊，
    漏检的代价(整张照片直接判"无主体")比误检的代价大，宁可放宽(见架构文档3.2)。
    """
    model = get_detection_model()
    detections = model.predict(image_path, threshold=confidence_threshold)

    if len(detections.xyxy) == 0:
        return None

    best_idx = int(detections.confidence.argmax())
    x1, y1, x2, y2 = detections.xyxy[best_idx]
    confidence = float(detections.confidence[best_idx])
    class_id = int(detections.class_id[best_idx])
    class_name = (
        model.class_names[class_id] if hasattr(model, "class_names") else str(class_id)
    )

    return Detection(
        confidence=confidence,
        bbox=(int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
        class_name=str(class_name),
    )


def detect_eye_point(image_path: str) -> Optional[tuple[int, int]]:
    """
    返回眼部关键点坐标 (x, y)。没有微调过的眼部关键点模型时直接返回None，
    对应 photos 表里 eye_bbox 留空——这种情况必须落到"待定"，
    不能被当成"合格"或"不合格"处理(见架构文档 eye_focus.py 设计)。

    假定训练时把"眼睛"标注为关键点索引0——标注群友照片时（CVAT导出COCO
    Keypoints）把眼睛固定标为第一个关键点，这里的索引才会对得上。
    """
    model = get_keypoint_model()
    if model is None:
        return None

    image = cv2.imread(image_path)
    if image is None:
        return None

    key_points = model.predict(image)
    if key_points is None or len(key_points.xy) == 0:
        return None

    eye_x, eye_y = key_points.xy[0][0]
    return (int(eye_x), int(eye_y))
