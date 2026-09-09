"""sayelf-birdpick 本地 WebUI + 本地识别 API。

只绑定 127.0.0.1：浏览器把当前照片发送给同一台电脑上的 Python 进程，
由现有 RF-DETR/质量测量工作流处理。请求结束后临时文件删除，不提供云端接口。
模型权重仍需用户另行获取，本文件不会把权重打包进仓库。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import os
import posixpath
import tempfile
from email import policy
from email.parser import BytesParser
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
ALLOWED_ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765"}


def json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def configured_weight(path_value: str | None) -> bool:
    return bool(path_value and Path(path_value).is_file())


def health_payload() -> dict[str, Any]:
    has_cv2 = importlib.util.find_spec("cv2") is not None
    has_rfdetr = importlib.util.find_spec("rfdetr") is not None
    detection_weights = os.environ.get("SAYELF_BIRD_DETECTION_MODEL_PATH")
    eye_weights = os.environ.get("SAYELF_BIRD_EYE_MODEL_PATH")
    return {
        "ok": True,
        "localOnly": True,
        "recognitionAvailable": has_cv2 and has_rfdetr,
        "dependencies": {"opencv": has_cv2, "rfdetr": has_rfdetr},
        "weights": {
            "includedInRepository": False,
            "detectionConfigured": configured_weight(detection_weights),
            "eyeConfigured": configured_weight(eye_weights),
        },
        "message": (
            "本地识别服务已就绪"
            if has_cv2 and has_rfdetr
            else "本地识别依赖未安装；请先安装 requirements.txt"
        ),
    }


def analyze_image(image_path: str) -> dict[str, Any]:
    """复用现有识别工作流，对单张临时图片返回可展示结果。"""
    try:
        import cv2

        from src.recognition.detect import detect_eye_point, detect_subject
        from src.recognition.eye_focus import expand_point_to_bbox, eye_sharpness_ratio
        from src.recognition.pipeline import decide_tech_grade
        from src.recognition.quality import exposure_flag, sharpness_score
    except Exception as error:  # 依赖缺失时由 API 返回可理解的本地提示
        return {
            "ok": False,
            "status": 503,
            "code": "LOCAL_MODEL_UNAVAILABLE",
            "message": "本地识别依赖或模型未就绪，请安装 requirements.txt 并准备本地模型权重。",
            "errorType": type(error).__name__,
        }

    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        return {
            "ok": False,
            "status": 400,
            "code": "IMAGE_READ_FAILED",
            "message": "本地服务无法读取这张图片。",
        }

    try:
        detection = detect_subject(image_path, confidence_threshold=0.3)
        subject_bbox = detection.bbox if detection else None
        sharpness = float(sharpness_score(image_bgr, subject_bbox))
        exposure = exposure_flag(image_bgr, subject_bbox)

        eye_point = detect_eye_point(image_path)
        eye_bbox = None
        eye_ratio = None
        if eye_point is not None:
            height, width = image_bgr.shape[:2]
            eye_bbox = expand_point_to_bbox(eye_point[0], eye_point[1], width, height)
            eye_ratio = float(eye_sharpness_ratio(image_bgr, eye_bbox))

        tech_grade = decide_tech_grade(
            subject_detected=detection is not None,
            sharpness=sharpness,
            exposure=exposure,
            eye_ratio=eye_ratio,
        )
    except Exception as error:
        # 不把本地路径或完整堆栈返回给浏览器；详细错误只留在本地服务控制台。
        print(f"local recognition failed: {type(error).__name__}: {error}")
        return {
            "ok": False,
            "status": 503,
            "code": "LOCAL_RECOGNITION_FAILED",
            "message": "本地模型运行失败，请检查依赖、模型权重和显卡/内存状态。",
            "errorType": type(error).__name__,
        }

    height, width = image_bgr.shape[:2]
    eye_weights = os.environ.get("SAYELF_BIRD_EYE_MODEL_PATH")
    return {
        "ok": True,
        "status": 200,
        "localOnly": True,
        "model": {
            "name": "RF-DETR",
            "weightsIncluded": False,
            "detectionWeightsConfigured": configured_weight(
                os.environ.get("SAYELF_BIRD_DETECTION_MODEL_PATH")
            ),
            "eyeWeightsConfigured": configured_weight(eye_weights),
        },
        "image": {"width": width, "height": height},
        "result": {
            "subjectDetected": detection is not None,
            "className": detection.class_name if detection else None,
            "confidence": detection.confidence if detection else None,
            "bbox": list(detection.bbox) if detection else None,
            "sharpness": sharpness,
            "exposure": exposure,
            "eyePoint": list(eye_point) if eye_point else None,
            "eyeSharpnessRatio": eye_ratio,
            "techGrade": tech_grade,
        },
        "note": (
            "检测和质量测量在本机完成；眼部结果需要另行配置眼部模型。"
            if eye_weights
            else "检测和质量测量在本机完成；未配置眼部模型，眼部结果保持待定。"
        ),
    }


class LocalHandler(SimpleHTTPRequestHandler):
    server_version = "sayelf-birdpick-local/0.1"

    @staticmethod
    def is_public_path(request_path: str) -> bool:
        normalized = posixpath.normpath(unquote(urlsplit(request_path).path))
        return normalized in {"/", "/index.html"} or normalized.startswith("/assets/")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        super().end_headers()

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/api/health":
            self.send_json(health_payload())
            return
        if not self.is_public_path(self.path):
            self.send_json({"ok": False, "message": "本地服务不公开该文件"}, status=404)
            return
        if urlsplit(self.path).path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_HEAD(self) -> None:
        if not self.is_public_path(self.path):
            self.send_json({"ok": False, "message": "本地服务不公开该文件"}, status=404)
            return
        if urlsplit(self.path).path == "/":
            self.path = "/index.html"
        super().do_HEAD()

    def read_upload(self) -> tuple[str, bytes]:
        content_length = self.headers.get("Content-Length")
        try:
            length = int(content_length or "0")
        except ValueError as error:
            raise ValueError("请求大小无效") from error
        if length <= 0:
            raise ValueError("没有收到图片")
        if length > MAX_UPLOAD_BYTES:
            raise OverflowError("单张图片不能超过 40 MB")

        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ValueError("请以 multipart/form-data 发送图片")

        body = self.rfile.read(length)
        header = (
            f"Content-Type: {content_type}\r\n"
            "MIME-Version: 1.0\r\n\r\n"
        ).encode("utf-8")
        message = BytesParser(policy=policy.default).parsebytes(header + body)
        for part in message.iter_attachments():
            filename = part.get_filename()
            if not filename or not part.get_content_type().startswith("image/"):
                continue
            data = part.get_payload(decode=True)
            if data:
                return Path(filename).name, data
        raise ValueError("没有收到可识别的图片文件")

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/api/recognize":
            self.send_json({"ok": False, "message": "本地 API 路径不存在"}, status=404)
            return

        try:
            filename, data = self.read_upload()
        except OverflowError as error:
            self.send_json({"ok": False, "code": "UPLOAD_TOO_LARGE", "message": str(error)}, status=413)
            return
        except ValueError as error:
            self.send_json({"ok": False, "code": "BAD_UPLOAD", "message": str(error)}, status=400)
            return

        suffix = Path(filename).suffix.lower()
        if not suffix:
            suffix = mimetypes.guess_extension(self.headers.get("Content-Type", "")) or ".jpg"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="sayelf-birdpick-", suffix=suffix, delete=False) as handle:
                handle.write(data)
                temporary_path = handle.name
            result = analyze_image(temporary_path)
            status = int(result.pop("status", 200))
            self.send_json(result, status=status)
        finally:
            if temporary_path:
                try:
                    Path(temporary_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[local] {self.address_string()} - {format_string % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="sayelf-birdpick 本地 WebUI 与识别服务")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    args = parser.parse_args()

    handler = partial(LocalHandler, directory=str(ROOT))
    host = "127.0.0.1"
    server = HTTPServer((host, args.port), handler)
    print(f"sayelf-birdpick local UI: http://{host}:{args.port}/index.html")
    print(json.dumps(health_payload(), ensure_ascii=False))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n本地识别服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
