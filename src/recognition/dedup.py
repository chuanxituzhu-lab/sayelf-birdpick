"""
识别工作流·连拍去重
EXIF拍摄时间戳先圈出候选范围(时间窗口内的照片才可能是连拍)，
再用感知哈希(pHash)精确判断是否是同一组的近似重复帧。

架构文档3.2节最初写的是"CLIP embedding相似度"，这里改用pHash：
连拍帧几乎逐像素相似，pHash足够快、足够准，不需要CLIP这种面向语义相似度
的重型方案——这是刻意的简化，不是遗漏，遵循"负熵"原则，没必要的复杂度不留。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import imagehash
import piexif
from PIL import Image


@dataclass
class PhotoMeta:
    file_path: str
    capture_time: Optional[datetime]
    phash: imagehash.ImageHash


def read_capture_time(file_path: str) -> Optional[datetime]:
    """从EXIF读取拍摄时间，读不到就返回None（此时该照片单独成组，不参与去重分组）。"""
    try:
        exif_dict = piexif.load(file_path)
        dt_bytes = exif_dict.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
        if dt_bytes is None:
            return None
        dt_str = dt_bytes.decode("utf-8") if isinstance(dt_bytes, bytes) else dt_bytes
        return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def compute_phash(file_path: str) -> imagehash.ImageHash:
    with Image.open(file_path) as img:
        return imagehash.phash(img)


def build_photo_meta(file_path: str) -> PhotoMeta:
    return PhotoMeta(
        file_path=file_path,
        capture_time=read_capture_time(file_path),
        phash=compute_phash(file_path),
    )


def group_bursts(
    photos: list[PhotoMeta],
    time_window_seconds: int = 3,
    hash_distance_threshold: int = 8,
) -> list[list[int]]:
    """
    对一批照片分组，返回每组包含的照片索引列表。
    分组规则：拍摄时间在 time_window_seconds 秒内 且 pHash汉明距离低于阈值，
    两个条件都要满足才归为同一组——避免"时间近但不是同一只鸟"
    或"长得像但拍摄时间隔很远"被误分到一组。
    """
    n = len(photos)
    visited = [False] * n
    groups: list[list[int]] = []

    indices_with_time = [i for i in range(n) if photos[i].capture_time is not None]
    indices_without_time = [i for i in range(n) if photos[i].capture_time is None]
    indices_with_time.sort(key=lambda i: photos[i].capture_time)

    for idx in indices_with_time:
        if visited[idx]:
            continue
        current_group = [idx]
        visited[idx] = True
        for other in indices_with_time:
            if visited[other]:
                continue
            time_diff = abs((photos[other].capture_time - photos[idx].capture_time).total_seconds())
            if time_diff > time_window_seconds:
                continue
            hash_diff = photos[idx].phash - photos[other].phash
            if hash_diff <= hash_distance_threshold:
                current_group.append(other)
                visited[other] = True
        groups.append(current_group)

    # 没有EXIF时间的照片单独成组，不参与聚类
    for idx in indices_without_time:
        groups.append([idx])

    return groups


def pick_representative(
    photos: list[PhotoMeta],
    group: list[int],
    sharpness_scores: dict[int, float],
) -> int:
    """组内选一张代表帧——直接选清晰度最高的那张，其余标记为 is_duplicate_frame。"""
    return max(group, key=lambda i: sharpness_scores.get(i, 0.0))
