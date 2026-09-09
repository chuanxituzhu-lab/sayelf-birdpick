"""
识别工作流·主流程编排
串联去重分组 -> 主体检测 -> 清晰度/曝光测量 -> 眼部合焦比例 -> 三段式分级，
把结果写入 SQLite 的 photos 表。评价工作流(scorer.mjs)只读这张表，不碰原图。

这是 index.html 点"开始识别"之后，本地 Node 服务实际调用的入口
（Node 通过 child_process 调用 `python -m recognition.pipeline <照片目录> <数据库路径>`）。
"""
import json
import os
import sqlite3
import sys
from typing import Optional

import cv2

from .dedup import build_photo_meta, group_bursts, pick_representative
from .detect import detect_eye_point, detect_subject
from .eye_focus import expand_point_to_bbox, eye_sharpness_ratio
from .quality import exposure_flag, sharpness_score

# 三段式判定阈值——这里给的是冷启动默认值，不是最终数字。
# 上线前必须用群友历史标注数据重新校准这几个数字(见架构文档3.2)。
SHARPNESS_PASS = 500.0
SHARPNESS_REJECT = 100.0
EYE_RATIO_PASS = 0.8
EYE_RATIO_REJECT = 0.5
DETECTION_CONFIDENCE_MIN = 0.3

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "schema.sql")


def decide_tech_grade(
    subject_detected: bool,
    sharpness: float,
    exposure: str,
    eye_ratio: Optional[float],
) -> str:
    """
    三段式分级：pass / pending / reject，只分级不删除。
    判定门槛故意保守——任何拿不准的情况一律落到 pending，
    不能因为一次测量偏差就把好照片判死(见架构文档"防错机制")。
    """
    if not subject_detected:
        return "reject"

    if exposure != "normal":
        return "pending"

    if sharpness <= SHARPNESS_REJECT:
        return "reject"
    if sharpness < SHARPNESS_PASS:
        return "pending"

    if eye_ratio is None:
        return "pending"  # 没检出眼部关键点，不能当成合格处理
    if eye_ratio <= EYE_RATIO_REJECT:
        return "reject"
    if eye_ratio < EYE_RATIO_PASS:
        return "pending"

    return "pass"


def process_photo(
    conn: sqlite3.Connection,
    file_path: str,
    burst_group_id: int,
    is_duplicate_frame: bool,
    capture_time: Optional[str],
) -> None:
    image_bgr = cv2.imread(file_path)
    if image_bgr is None:
        return  # 读取失败的文件跳过，不写入数据库

    detection = detect_subject(file_path, confidence_threshold=DETECTION_CONFIDENCE_MIN)
    subject_detected = detection is not None
    subject_confidence = detection.confidence if detection else None
    subject_bbox = detection.bbox if detection else None

    sharp = sharpness_score(image_bgr, subject_bbox)
    exposure = exposure_flag(image_bgr, subject_bbox)

    eye_point = detect_eye_point(file_path)
    eye_bbox = None
    eye_ratio = None
    if eye_point is not None:
        h, w = image_bgr.shape[:2]
        eye_bbox = expand_point_to_bbox(eye_point[0], eye_point[1], w, h)
        eye_ratio = eye_sharpness_ratio(image_bgr, eye_bbox)

    subject_area_ratio = None
    if subject_bbox is not None:
        h, w = image_bgr.shape[:2]
        subject_area_ratio = (subject_bbox[2] * subject_bbox[3]) / float(w * h)

    tech_grade = decide_tech_grade(subject_detected, sharp, exposure, eye_ratio)

    conn.execute(
        """
        INSERT INTO photos (
            file_path, capture_time, burst_group_id, is_duplicate_frame,
            sharpness_score, exposure_flag, subject_detected, subject_confidence,
            subject_bbox, subject_area_ratio, eye_bbox, eye_sharpness_ratio,
            tech_grade, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(file_path) DO UPDATE SET
            sharpness_score=excluded.sharpness_score,
            exposure_flag=excluded.exposure_flag,
            tech_grade=excluded.tech_grade,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            file_path, capture_time, burst_group_id, int(is_duplicate_frame),
            sharp, exposure, int(subject_detected), subject_confidence,
            json.dumps(subject_bbox) if subject_bbox else None, subject_area_ratio,
            json.dumps(eye_bbox) if eye_bbox else None, eye_ratio,
            tech_grade,
        ),
    )


def run_recognition_pipeline(image_dir: str, db_path: str) -> None:
    """对 image_dir 目录下所有照片跑一遍完整识别流程，结果写入 db_path 的 SQLite 数据库。"""
    conn = sqlite3.connect(db_path)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())

    file_paths = [
        os.path.join(image_dir, name)
        for name in os.listdir(image_dir)
        if name.lower().endswith((".jpg", ".jpeg", ".png", ".tiff"))
    ]

    photo_metas = [build_photo_meta(p) for p in file_paths]

    sharpness_map: dict[int, float] = {}
    for i, meta in enumerate(photo_metas):
        img = cv2.imread(meta.file_path)
        sharpness_map[i] = sharpness_score(img) if img is not None else 0.0

    groups = group_bursts(photo_metas)

    for group_id, group in enumerate(groups):
        representative_idx = pick_representative(photo_metas, group, sharpness_map)
        for idx in group:
            meta = photo_metas[idx]
            is_duplicate = (idx != representative_idx) and len(group) > 1
            capture_time_str = meta.capture_time.isoformat() if meta.capture_time else None
            process_photo(conn, meta.file_path, group_id, is_duplicate, capture_time_str)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python -m recognition.pipeline <照片目录> <数据库路径>")
        sys.exit(1)
    run_recognition_pipeline(sys.argv[1], sys.argv[2])
    print("识别流程完成")
