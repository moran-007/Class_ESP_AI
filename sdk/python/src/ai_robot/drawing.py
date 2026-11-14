"""Capture a standard Turtle canvas and stream fitted RGB565 screen images.

Importing this module does not open Tk, a serial port, or a screenshot.
"""
from __future__ import annotations

from pathlib import Path
import sys

from .errors import UnsupportedCapability

MAX_SOURCE_PIXELS = 16_000_000
MAX_BITMAP_PIXELS = 384


def _pillow():
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise UnsupportedCapability("图片/Turtle功能需要drawing依赖：安装 ai-maker-robot[drawing]") from error
    return Image, ImageOps


def load_image(image_or_path):
    """Return an owned RGBA copy after checking dimensions before decoding."""
    Image, ImageOps = _pillow()
    opened = None
    if isinstance(image_or_path, (str, Path)):
        opened = Image.open(image_or_path)
        source = opened
    elif isinstance(image_or_path, Image.Image):
        source = image_or_path
    else:
        raise ValueError("图像须为Pillow Image对象或本地图片文件路径")
    try:
        width, height = source.size
        if width <= 0 or height <= 0 or width * height > MAX_SOURCE_PIXELS:
            raise ValueError("源图像尺寸必须为正且不超过1600万像素")
        # Respect JPEG/phone rotation without modifying the caller's image.
        return ImageOps.exif_transpose(source).convert("RGBA")
    finally:
        if opened is not None:
            opened.close()


def fit_image(source, size, fit="contain", background=(0, 0, 0)):
    """Return RGB pixels for a panel. contain letterboxes; cover center-crops."""
    Image, ImageOps = _pillow()
    if fit not in ("contain", "cover"):
        raise ValueError("fit须为contain或cover")
    width, height = size
    if type(width) is not int or type(height) is not int or not 1 <= width <= 320 or not 1 <= height <= 320:
        raise ValueError("目标屏幕尺寸须为1～320的整数")
    background_image = Image.new("RGBA", source.size, (*background, 255))
    background_image.alpha_composite(source)
    flattened = background_image.convert("RGB")
    if fit == "cover":
        return ImageOps.fit(flattened, size, method=Image.Resampling.LANCZOS, centering=(.5, .5))
    thumbnail = ImageOps.contain(flattened, size, method=Image.Resampling.LANCZOS)
    result = Image.new("RGB", size, background)
    result.paste(thumbnail, ((width - thumbnail.width) // 2, (height - thumbnail.height) // 2))
    return result


def rgb565_strips(image):
    """Yield y,height,RGB565BE bytes, each bounded to 384 pixels."""
    width, height = image.size
    if not 1 <= width <= 320 or not 1 <= height <= 320:
        raise ValueError("目标屏幕尺寸须为1～320")
    raw = image.convert("RGB").tobytes()
    strip_rows = max(1, MAX_BITMAP_PIXELS // width)
    for y in range(0, height, strip_rows):
        rows = min(strip_rows, height - y)
        source = raw[y * width * 3:(y + rows) * width * 3]
        pixels = bytearray(width * rows * 2)
        for index in range(0, len(source), 3):
            red, green, blue = source[index:index + 3]
            color = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
            target = index // 3 * 2
            pixels[target] = color >> 8
            pixels[target + 1] = color & 255
        yield y, rows, bytes(pixels)


def capture_turtle(screen):
    """Capture only the visible inner Tk canvas of a real standard Turtle screen."""
    _pillow()
    from PIL import ImageGrab
    try:
        canvas = screen.getcanvas()
        canvas = getattr(canvas, "_canvas", canvas)  # Turtle ScrolledCanvas wrapper.
        screen.update()
        canvas.update_idletasks()
        root = canvas.winfo_toplevel()
        if not canvas.winfo_exists() or not canvas.winfo_ismapped() or not canvas.winfo_viewable() or root.state() in ("iconic", "withdrawn"):
            raise ValueError("Turtle窗口必须可见，不能最小化或关闭")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width <= 1 or height <= 1 or width * height > MAX_SOURCE_PIXELS:
            raise ValueError("Turtle画布尺寸无效或超过1600万像素")
        if sys.platform == "win32":
            # Never fall back to grabbing the desktop: the Canvas HWND excludes
            # toolbar, window chrome, other apps, and Turtle scrollbars.
            image = ImageGrab.grab(window=int(canvas.winfo_id()))
        else:
            left, top = canvas.winfo_rootx(), canvas.winfo_rooty()
            image = ImageGrab.grab(bbox=(left, top, left + width, top + height))
        if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_SOURCE_PIXELS:
            raise ValueError("Turtle截图尺寸无效")
        return image.convert("RGB")
    except ValueError:
        raise
    except Exception as error:
        raise RuntimeError("无法捕获Turtle画布；请保持窗口可见并确认drawing依赖已安装") from error


def send_turtle(robot, screen, **fit_options):
    """Capture standard Turtle drawing and send it; no code translation involved."""
    image = capture_turtle(screen)
    try:
        return robot.display.image(image, **fit_options)
    finally:
        image.close()
