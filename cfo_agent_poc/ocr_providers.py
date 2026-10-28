"""可插拔的 OCR 后端。

对外只暴露 `ocr_image(image_path) -> str`，返回按阅读顺序排好的纯文本，
每个识别条目一行。下游 `bill_store.parse_bill_text` 依赖这个形状：
它的字段抽取正则要求标签独占一行、值在下一行（见 bill_store.py 的 extract_field），
所以**同一视觉行的左右两块必须各自成行，不能拼接**。

- rapidocr：默认后端。RapidOCR（PP-OCR 模型 + ONNX Runtime），本机 CPU 推理，
  免费、离线、截图不出服务器，macOS 和 Linux 一样用，本地调好的解析规则上线不走样。
- vision：macOS 上调 Apple Vision（ocr_image.swift），需要时手动指定。
- aliyun：阿里云通用文字识别，按次计费，只在显式指定时作为后备。
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
OCR_SCRIPT = PROJECT_DIR / "ocr_image.swift"

# RapidOCR 参数由真实账单回归选定（见 eval_ocr_backends.py），目标是 2 核小内存服务器。
# 用包里自带的 PP-OCRv6 small 检测 + 识别模型，部署不用另外下载模型。
RAPIDOCR_PARAMS: dict[str, Any] = {
    # 截图不会倒着放，方向分类整步跳过
    "Global.use_cls": False,
    "Global.log_level": "error",
    # 找文字框不需要原分辨率：长边缩到 960 再检测，识别仍从原图裁字。
    # 默认是「短边不足 736 就放大」，1206 宽的直传截图会按 920×2000 去检测，又慢又吃内存
    "Det.limit_type": "max",
    "Det.limit_side_len": 960,
    # 一行一推：批处理会把一批文字条补齐到最宽那条，账单里短标签多，补齐纯属浪费，逐条反而快一倍
    "Rec.rec_batch_num": 1,
    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
}

DEFAULT_REGION = "cn-hangzhou"
DEFAULT_TIMEOUT_SECONDS = 20.0

# 阿里云 OCR 支持的图片格式；HEIC/HEIF 明确不在其中。
ALIYUN_SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".tif", ".webp"}
HEIC_SUFFIXES = {".heic", ".heif"}

# 同一视觉行的容差：条目中心 y 相差不到图片高度的 1%，视为同一行。
# 与 ocr_image.swift 里归一化坐标下的 0.01 阈值对齐。
ROW_TOLERANCE_RATIO = 0.01


class OCRError(RuntimeError):
    """OCR 失败。消息会经截图上传接口透出到快捷指令通知和网页，所以写成人话。"""


def _provider_name() -> str:
    configured = os.environ.get("CFO_OCR_PROVIDER", "").strip().lower()
    if configured and configured != "auto":
        return configured
    return "rapidocr"


def ocr_image(image_path: str) -> str:
    provider = _provider_name()
    if provider == "rapidocr":
        return _ocr_rapidocr(image_path)
    if provider == "vision":
        return _ocr_vision(image_path)
    if provider == "aliyun":
        return _ocr_aliyun(image_path)
    raise OCRError(f"未知的 OCR 后端 {provider!r}，CFO_OCR_PROVIDER 只支持 auto / rapidocr / vision / aliyun。")


def warm_up() -> bool:
    """服务启动时预热：提前加载模型、跑一次小图，第一张上传的截图就不用等。

    只有 rapidocr 需要预热，其它后端直接返回 False。"""
    if _provider_name() != "rapidocr":
        return False
    import cv2
    import numpy as np

    # 要有字：检测到文字框才会顺带加载识别模型
    sample = np.full((64, 320, 3), 255, dtype=np.uint8)
    cv2.putText(sample, "CFO -12.00", (10, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    with _rapidocr_lock:
        _rapidocr_engine()(sample)
    return True


# --------------------------------------------------------------------------
# RapidOCR（默认）
# --------------------------------------------------------------------------

_rapidocr_lock = threading.Lock()
_rapidocr: Any = None


def _rapidocr_threads() -> int:
    raw = os.environ.get("CFO_OCR_THREADS", "").strip()
    try:
        threads = int(raw) if raw else 0
    except ValueError:
        threads = 0
    return threads if threads > 0 else (os.cpu_count() or 1)


def _rapidocr_engine() -> Any:
    """懒加载单例，调用方须持有 ``_rapidocr_lock``。模型只加载一份，常驻内存。"""
    global _rapidocr
    if _rapidocr is None:
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise OCRError("缺少 RapidOCR。请先执行：pip install -r cfo_agent_poc/requirements.txt") from exc
        _lean_session_options()
        params = dict(RAPIDOCR_PARAMS)
        params["EngineConfig.onnxruntime.intra_op_num_threads"] = _rapidocr_threads()
        _rapidocr = RapidOCR(params=params)
    return _rapidocr


def _lean_session_options() -> None:
    """ONNX 会话关掉 mem_pattern。

    文字条宽度张张不同，mem_pattern 会给每种输入形状各缓存一套内存规划，常驻内存越跑越大；
    关掉后速度基本不变。RapidOCR 没开放这个选项，只能包一层它生成会话选项的方法。
    版本锁在 requirements.txt 里；哪天内部结构变了就跳过，只是多占些内存，不影响识别。"""
    try:
        from rapidocr.inference_engine.onnxruntime.main import OrtInferSession

        original = OrtInferSession._init_sess_opts
    except (ImportError, AttributeError):
        return
    if getattr(original, "_cfo_lean", False):
        return

    def init_sess_opts(cfg: Any) -> Any:
        options = original(cfg)
        options.enable_mem_pattern = False
        return options

    init_sess_opts._cfo_lean = True  # type: ignore[attr-defined]
    OrtInferSession._init_sess_opts = staticmethod(init_sess_opts)


def _ocr_rapidocr(image_path: str) -> str:
    if not Path(image_path).is_file():
        raise OCRError(f"图片不存在：{image_path}")
    # 推理串行：小核数机器上两张图并行只会互相抢 CPU，单张用满线程反而最快
    with _rapidocr_lock:
        engine = _rapidocr_engine()
        try:
            result = engine(image_path)
        except Exception as exc:  # 坏图、解码失败
            raise OCRError(f"RapidOCR 识别失败：{type(exc).__name__}: {str(exc)[:200]}") from exc
    return text_from_rapidocr(result)


def text_from_rapidocr(result: Any) -> str:
    """把 RapidOCR 的 boxes / txts 还原成阅读顺序的文本。

    boxes 是像素四角点，原点左上、y 向下，和阿里云同一个坐标系，排序逻辑共用。"""
    boxes = getattr(result, "boxes", None)
    txts = getattr(result, "txts", None)
    if boxes is None or not txts:
        return ""
    entries: list[tuple[float, float, str]] = []
    for box, raw_text in zip(boxes, txts):
        text = str(raw_text or "").strip()
        if not text:
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        entries.append((sum(ys) / len(ys), min(xs), text))
    if not entries:
        return ""
    image = getattr(result, "img", None)
    height = float(image.shape[0]) if image is not None else 0.0
    return "\n".join(_ordered_lines(entries, height)).strip()


# --------------------------------------------------------------------------
# Apple Vision（macOS）
# --------------------------------------------------------------------------


def _ocr_vision(image_path: str) -> str:
    try:
        result = subprocess.run(
            ["swift", str(OCR_SCRIPT), image_path],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise OCRError(
            "找不到 swift 命令。Apple Vision OCR 只能在装了 Xcode 命令行工具的 macOS 上跑；"
            "在 Linux 上请设置 CFO_OCR_PROVIDER=aliyun。"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or f"退出码 {exc.returncode}"
        raise OCRError(f"Apple Vision OCR 失败：{detail}") from exc
    return result.stdout.strip()


# --------------------------------------------------------------------------
# 阿里云通用文字识别
# --------------------------------------------------------------------------

_client_lock = threading.Lock()
_client: Any = None


def _aliyun_client() -> Any:
    """懒加载单例。截图是一张张陆续上传的，没必要每张图重建 client。"""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client

        access_key_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "").strip()
        access_key_secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "").strip()
        if not access_key_id or not access_key_secret:
            raise OCRError(
                "未配置阿里云 AccessKey。请在 cfo_agent_poc/.env 里设置 "
                "ALIBABA_CLOUD_ACCESS_KEY_ID 和 ALIBABA_CLOUD_ACCESS_KEY_SECRET。"
            )

        # SDK 只在真正要用阿里云时才 import：Mac 上走 vision 分支不必安装它，
        # 测试也不用被迫拉这套依赖。
        try:
            from alibabacloud_ocr_api20210707.client import Client as OcrClient
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError as exc:
            raise OCRError(
                "缺少阿里云 OCR SDK。请先执行：pip install -r cfo_agent_poc/requirements.txt"
            ) from exc

        region = os.environ.get("CFO_OCR_REGION", "").strip() or DEFAULT_REGION
        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
        )
        config.endpoint = f"ocr-api.{region}.aliyuncs.com"
        _client = OcrClient(config)
    return _client


def _timeout_ms() -> int:
    raw = os.environ.get("CFO_OCR_TIMEOUT_SECONDS", "").strip()
    try:
        seconds = float(raw) if raw else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        seconds = DEFAULT_TIMEOUT_SECONDS
    return int(max(seconds, 1.0) * 1000)


def _check_supported_format(image_path: str) -> None:
    suffix = Path(image_path).suffix.lower()
    if suffix in HEIC_SUFFIXES:
        raise OCRError(
            "阿里云 OCR 不支持 HEIC/HEIF 格式。请把 iPhone 快捷指令的输出改成 PNG 或 JPEG。"
        )
    if suffix and suffix not in ALIYUN_SUPPORTED_SUFFIXES:
        raise OCRError(
            f"阿里云 OCR 不支持 {suffix} 格式，仅支持 "
            f"{'、'.join(sorted(ALIYUN_SUPPORTED_SUFFIXES))}。"
        )


def _ocr_aliyun(image_path: str) -> str:
    _check_supported_format(image_path)
    client = _aliyun_client()

    from alibabacloud_ocr_api20210707 import models as ocr_models
    from alibabacloud_tea_util import models as util_models

    timeout_ms = _timeout_ms()
    runtime = util_models.RuntimeOptions(connect_timeout=timeout_ms, read_timeout=timeout_ms)

    try:
        with open(image_path, "rb") as stream:
            request = ocr_models.RecognizeGeneralRequest(body=stream)
            response = client.recognize_general_with_options(request, runtime)
    except FileNotFoundError as exc:
        raise OCRError(f"图片不存在：{image_path}") from exc
    except OCRError:
        raise
    except Exception as exc:  # SDK 的异常类型不稳定，统一转成人话
        raise OCRError(_aliyun_error_message(exc)) from exc

    body = getattr(response, "body", None)
    return text_from_recognize_data(getattr(body, "data", None))


def _aliyun_error_message(exc: Exception) -> str:
    code = str(getattr(exc, "code", "") or "")
    message = str(getattr(exc, "message", "") or "") or str(exc)
    lowered = f"{code} {message}".lower()

    if "servicenotopen" in lowered or "not activated" in lowered:
        hint = "该阿里云账号尚未开通文字识别（OCR）服务，去 OCR 控制台开通后即可调用（有免费额度）。"
    elif "invalidaccesskeyid" in lowered or "signaturedoesnotmatch" in lowered:
        hint = "AccessKey 无效或签名不匹配，检查 .env 里的 ID/Secret 是否配对、有没有多余空格。"
    elif "forbidden" in lowered or "nopermission" in lowered or "denied" in lowered:
        hint = "鉴权通过但没有权限，确认该 RAM 用户已授予 OCR 调用权限、且服务已开通。"
    elif "timeout" in lowered or "timed out" in lowered:
        hint = "调用超时，可调大 CFO_OCR_TIMEOUT_SECONDS，或检查服务器到 aliyuncs.com 的出网。"
    elif "throttl" in lowered or "qps" in lowered or "limitexceeded" in lowered:
        hint = "触发限流或额度用尽，检查 OCR 资源包余量。"
    else:
        hint = message or "未知错误"

    prefix = f"[{code}] " if code else ""
    return f"阿里云 OCR 调用失败：{prefix}{hint}"


# --------------------------------------------------------------------------
# 响应解析
# --------------------------------------------------------------------------


def text_from_recognize_data(raw: Any) -> str:
    """把 RecognizeGeneral 的 Data 还原成阅读顺序的文本。

    Data 通常是 JSON 字符串，也可能已经被反序列化成 dict。
    """
    data = _coerce_data(raw)
    if data is None:
        raise OCRError("阿里云 OCR 返回内容为空。")
    return lines_from_prism(data)


def _coerce_data(raw: Any) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise OCRError(f"阿里云 OCR 返回的 Data 不是合法 JSON：{text[:120]}") from exc
        return parsed if isinstance(parsed, dict) else None
    to_map = getattr(raw, "to_map", None)
    if callable(to_map):
        mapped = to_map()
        return mapped if isinstance(mapped, dict) else None
    return None


def lines_from_prism(data: dict) -> str:
    """按阅读顺序重排 prism_wordsInfo。

    坐标系差异是这里最容易翻车的地方：
    - Apple Vision 用归一化坐标，原点左下、y 向上，所以 ocr_image.swift 按 y 降序排。
    - 阿里云用像素坐标，原点左上、y 向下，所以这里按 y 升序排。
    两者都表示"从页面顶部往下"。

    容差只用来决定**顺序**（同一视觉行内左块排在右块前面），
    绝不把同一行的多个条目拼成一行文本——微信/支付宝详情页是左标签右值的布局，
    拼起来会让 bill_store 那条要求"标签独占一行"的正则彻底失配。
    """
    words = data.get("prism_wordsInfo") or []
    entries: list[tuple[float, float, str]] = []
    for item in words:
        if not isinstance(item, dict):
            continue
        text = str(item.get("word") or "").strip()
        if not text:
            continue
        y_mid, x_min = _entry_position(item)
        if y_mid is None or x_min is None:
            continue
        entries.append((y_mid, x_min, text))

    if not entries:
        return str(data.get("content") or "").strip()

    height = data.get("height") or data.get("orgHeight")
    try:
        height_value = float(height or 0)
    except (TypeError, ValueError):
        height_value = 0.0
    return "\n".join(_ordered_lines(entries, height_value)).strip()


def _ordered_lines(entries: list[tuple[float, float, str]], height: float) -> list[str]:
    """(y 中心, x 最左, 文本) 条目按阅读顺序排好，每个条目一行。阿里云和 RapidOCR 共用。"""
    entries = sorted(entries, key=lambda entry: (entry[0], entry[1]))
    tolerance = _row_tolerance(height, entries)
    ordered: list[str] = []
    row: list[tuple[float, float, str]] = [entries[0]]
    for entry in entries[1:]:
        # 与本行锚点（第一个条目）比较，避免逐个比较导致的行高漂移。
        if entry[0] - row[0][0] < tolerance:
            row.append(entry)
        else:
            ordered.extend(_flush_row(row))
            row = [entry]
    ordered.extend(_flush_row(row))
    return ordered


def _flush_row(row: list[tuple[float, float, str]]) -> list[str]:
    return [text for _, _, text in sorted(row, key=lambda entry: entry[1])]


def _entry_position(item: dict) -> tuple[float | None, float | None]:
    """优先用 pos 四角点；缺失时退回 x/y/height/width 字段。"""
    pos = item.get("pos")
    if isinstance(pos, list) and pos:
        ys = [float(p["y"]) for p in pos if isinstance(p, dict) and p.get("y") is not None]
        xs = [float(p["x"]) for p in pos if isinstance(p, dict) and p.get("x") is not None]
        if ys and xs:
            return sum(ys) / len(ys), min(xs)

    x = item.get("x")
    y = item.get("y")
    if x is None or y is None:
        return None, None
    height = item.get("height") or 0
    return float(y) + float(height) / 2, float(x)


def _row_tolerance(height_value: float, entries: list[tuple[float, float, str]]) -> float:
    if height_value <= 0:
        # 返回里没有图片高度时，用条目 y 的跨度兜底，保证容差仍与图片尺度相关。
        height_value = max(entry[0] for entry in entries) - min(entry[0] for entry in entries)
    return max(height_value * ROW_TOLERANCE_RATIO, 1.0)
