from io import BytesIO
from math import ceil
from pathlib import PurePosixPath

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

INSTAGRAM_FEED_IMAGE_MIN_ASPECT_RATIO = 4 / 5
INSTAGRAM_FEED_IMAGE_MAX_ASPECT_RATIO = 1.91
INSTAGRAM_FEED_IMAGE_MAX_WIDTH = 1080
INSTAGRAM_FEED_IMAGE_MAX_HEIGHT = 1350
INSTAGRAM_FEED_IMAGE_RATIO_ERROR = (
    "Instagram feed images must use an aspect ratio between 4:5 and 1.91:1."
)
INSTAGRAM_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
JPEG_SUFFIXES = {".jpg", ".jpeg"}
JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


def normalize_instagram_feed_image_upload(uploaded_file):
    suffix = PurePosixPath(str(uploaded_file.name).replace("\\", "/")).suffix.lower()
    if suffix not in INSTAGRAM_IMAGE_SUFFIXES:
        return uploaded_file

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image = ImageOps.exif_transpose(image)
            image.load()
    except (UnidentifiedImageError, OSError):
        uploaded_file.seek(0)
        return uploaded_file
    finally:
        uploaded_file.seek(0)

    image = _flatten_to_rgb(image)
    image = _pad_to_instagram_feed_ratio(image)
    image = _resize_to_instagram_feed_bounds(image)

    output = BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    filename = _instagram_jpeg_filename(uploaded_file.name)
    return SimpleUploadedFile(filename, output.getvalue(), content_type="image/jpeg")


def normalize_instagram_feed_image_file(file_obj, filename: str):
    try:
        file_obj.seek(0)
        with Image.open(file_obj) as image:
            image = ImageOps.exif_transpose(image)
            image.load()
    except (UnidentifiedImageError, OSError):
        file_obj.seek(0)
        return None
    finally:
        file_obj.seek(0)

    image = _flatten_to_rgb(image)
    image = _pad_to_instagram_feed_ratio(image)
    image = _resize_to_instagram_feed_bounds(image)

    output = BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return SimpleUploadedFile(
        _instagram_jpeg_filename(filename),
        output.getvalue(),
        content_type="image/jpeg",
    )


def instagram_image_ratio_is_unsupported(dimensions: tuple[int, int] | None) -> bool:
    if dimensions is None:
        return False
    width, height = dimensions
    if not width or not height:
        return False
    aspect_ratio = width / height
    return not (
        INSTAGRAM_FEED_IMAGE_MIN_ASPECT_RATIO
        <= aspect_ratio
        <= INSTAGRAM_FEED_IMAGE_MAX_ASPECT_RATIO
    )


def read_jpeg_dimensions(file_obj) -> tuple[int, int] | None:
    try:
        position = file_obj.tell()
    except (AttributeError, OSError):
        position = None
    data = file_obj.read(1024 * 1024)
    if position is not None:
        file_obj.seek(position)
    return jpeg_dimensions_from_bytes(data)


def jpeg_dimensions_from_bytes(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    while index < len(data) - 3:
        if data[index] != 0xFF:
            index += 1
            continue
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            break
        marker = data[index]
        index += 1
        if marker in {0x00, 0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(data):
            break
        segment_length = int.from_bytes(data[index : index + 2], "big")
        if segment_length < 2:
            break
        segment_start = index + 2
        if marker in JPEG_SOF_MARKERS and segment_start + 5 <= len(data):
            height = int.from_bytes(data[segment_start + 1 : segment_start + 3], "big")
            width = int.from_bytes(data[segment_start + 3 : segment_start + 5], "big")
            return width, height
        index += segment_length
    return None


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        alpha_image = image.convert("RGBA")
        background = Image.new("RGB", alpha_image.size, "white")
        background.paste(alpha_image, mask=alpha_image.getchannel("A"))
        return background
    return image.convert("RGB")


def _pad_to_instagram_feed_ratio(image: Image.Image) -> Image.Image:
    width, height = image.size
    aspect_ratio = width / height
    if aspect_ratio > INSTAGRAM_FEED_IMAGE_MAX_ASPECT_RATIO:
        canvas_width = width
        canvas_height = ceil(width / INSTAGRAM_FEED_IMAGE_MAX_ASPECT_RATIO)
    elif aspect_ratio < INSTAGRAM_FEED_IMAGE_MIN_ASPECT_RATIO:
        canvas_width = ceil(height * INSTAGRAM_FEED_IMAGE_MIN_ASPECT_RATIO)
        canvas_height = height
    else:
        return image

    canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
    left = (canvas_width - width) // 2
    top = (canvas_height - height) // 2
    canvas.paste(image, (left, top))
    return canvas


def _resize_to_instagram_feed_bounds(image: Image.Image) -> Image.Image:
    width, height = image.size
    scale = min(
        1,
        INSTAGRAM_FEED_IMAGE_MAX_WIDTH / width,
        INSTAGRAM_FEED_IMAGE_MAX_HEIGHT / height,
    )
    if scale >= 1:
        return image
    return image.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)


def _instagram_jpeg_filename(filename: str) -> str:
    path = PurePosixPath(str(filename).replace("\\", "/"))
    stem = path.stem.strip(".") or "image"
    return f"{stem}-instagram.jpg"
