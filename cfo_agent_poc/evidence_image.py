"""账单截图留底：原图只给 OCR 用，长期保存的是转好的 WebP。

手机直传的截屏 PNG 一张动辄 1–3MB，识别完以后只剩「网页里对照查看」这一个用途，
没必要一直留着原图。这里把原图转成同分辨率的有损 WebP：截图大面积纯色 + 文字，
q82 下肉眼看不出差别，体积通常只剩一到两成。

Pillow 只在真正转图时才 import：没装或者图片解不开都不挡记账，原样复制一份留底。
"""

from __future__ import annotations

import shutil
from pathlib import Path


WEBP_QUALITY = 82
# 常规 iPhone 截图（≤1320 宽）不缩放；只有 iPad 之类的大图才等比缩到这个宽度
MAX_WIDTH = 1440


def archive(raw: Path, dest_dir: Path) -> Path:
    """把原图存成留底用的证据图，返回证据图路径。原图不动，删不删由调用方决定。

    同名 WebP 已经存在就直接复用：文件名带原图哈希，内容一定一样（重试、重传同图都走这里）。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{raw.stem}.webp"
    if target.is_file():
        return target
    try:
        _write_webp(raw, target)
        return target
    except Exception as exc:  # 缺 Pillow、坏图、超出 WebP 尺寸上限都在这里兜住
        print(f"[CFO] 截图转 WebP 失败，保留原图：{type(exc).__name__}: {str(exc)[:200]}")
        target.with_suffix(target.suffix + ".part").unlink(missing_ok=True)
    fallback = dest_dir / raw.name
    if fallback.resolve() != raw.resolve():
        temp = fallback.with_suffix(fallback.suffix + ".part")
        shutil.copyfile(raw, temp)
        temp.replace(fallback)
    return fallback


def _write_webp(raw: Path, target: Path) -> None:
    from PIL import Image, ImageOps

    with Image.open(raw) as source:
        # iPhone 截图带 Display P3 色彩配置，丢了颜色会发灰，原样带过去
        icc_profile = source.info.get("icc_profile")
        image = ImageOps.exif_transpose(source)
        if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
            # 截图的透明通道没有意义，铺白底省掉 alpha
            rgba = image.convert("RGBA")
            image = Image.new("RGB", rgba.size, "white")
            image.paste(rgba, mask=rgba.getchannel("A"))
        elif image.mode != "RGB":
            image = image.convert("RGB")
        if image.width > MAX_WIDTH:
            height = round(image.height * MAX_WIDTH / image.width)
            image = image.resize((MAX_WIDTH, height), Image.Resampling.LANCZOS)
        temp = target.with_suffix(target.suffix + ".part")
        options = {"quality": WEBP_QUALITY, "method": 4}
        if icc_profile:
            options["icc_profile"] = icc_profile
        image.save(temp, "WEBP", **options)
    temp.replace(target)
