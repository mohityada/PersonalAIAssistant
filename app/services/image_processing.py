"""Image processing: EXIF extraction, BLIP-2 captioning, and YOLO object detection."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

logger = logging.getLogger(__name__)

# Maximum dimension (width or height) before we resize for captioning.
# Larger images waste memory without improving caption quality.
_MAX_CAPTION_DIM = 768


@dataclass
class ImageMetadata:
    """Extracted metadata and analysis results for an image."""
    caption: str = ""
    objects: list[str] = field(default_factory=list)
    location: str | None = None
    timestamp: datetime | None = None
    width: int = 0
    height: int = 0


# ── EXIF helpers ──────────────────────────────────────


def _dms_to_decimal(dms_tuple, ref: str) -> float | None:
    """Convert EXIF GPS DMS (degrees, minutes, seconds) to decimal degrees."""
    try:
        degrees, minutes, seconds = dms_tuple
        decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except Exception:
        return None


def _extract_exif(img: PILImage) -> dict:
    """Extract useful EXIF data from a PIL Image."""
    from PIL.ExifTags import GPSTAGS, TAGS

    exif_data: dict = {}
    raw_exif = img.getexif()
    if not raw_exif:
        return exif_data

    for tag_id, value in raw_exif.items():
        tag_name = TAGS.get(tag_id, str(tag_id))
        exif_data[tag_name] = value

    # Decode GPS info if present
    gps_info_raw = raw_exif.get(0x8825)  # GPSInfo tag
    if gps_info_raw:
        gps = {}
        for gps_tag_id, gps_value in gps_info_raw.items():
            gps_tag_name = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
            gps[gps_tag_name] = gps_value
        exif_data["GPSInfo"] = gps

    return exif_data


def _parse_location_from_exif(exif: dict) -> str | None:
    """Try to extract lat/lon from EXIF GPS data and return as a string."""
    gps = exif.get("GPSInfo")
    if not gps:
        return None

    lat = _dms_to_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef", "N"))
    lon = _dms_to_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef", "E"))

    if lat is not None and lon is not None:
        return f"{lat:.6f},{lon:.6f}"
    return None


def _parse_datetime_from_exif(exif: dict) -> datetime | None:
    """Try to extract datetime from EXIF data."""
    dt_str = exif.get("DateTimeOriginal") or exif.get("DateTime")
    if dt_str:
        try:
            return datetime.strptime(str(dt_str), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            pass
    return None


# ── Image pre-processing ─────────────────────────────


def _resize_for_captioning(img: PILImage) -> PILImage:
    """Down-scale the image so the longest side is at most _MAX_CAPTION_DIM.

    Keeps aspect ratio. Returns the original image if already small enough.
    This prevents excessive memory usage in the captioning model without
    degrading caption quality (BLIP-2 internally resizes to 364px anyway).
    """
    w, h = img.size
    if max(w, h) <= _MAX_CAPTION_DIM:
        return img

    from PIL import Image as PILImageModule

    scale = _MAX_CAPTION_DIM / max(w, h)
    new_size = (int(w * scale), int(h * scale))
    return img.resize(new_size, PILImageModule.LANCZOS)


# ── BLIP-2 image captioning ──────────────────────────

_blip_processor = None
_blip_model = None


def _get_blip_model():
    """Lazy-load the BLIP-2 image-captioning model (OPT-2.7B backbone).

    BLIP-2 produces significantly more accurate and descriptive captions
    compared to the original BLIP-base model.
    """
    global _blip_processor, _blip_model
    if _blip_model is None:
        try:
            from transformers import Blip2ForConditionalGeneration, Blip2Processor
        except ImportError as exc:
            raise ImportError(
                "The 'transformers' package is required for image captioning. "
                "Install it with: pip install transformers"
            ) from exc

        import torch

        model_name = "Salesforce/blip2-opt-2.7b"
        logger.info("Loading BLIP-2 captioning model: %s ...", model_name)

        _blip_processor = Blip2Processor.from_pretrained(model_name)

        # Use float16 when CUDA is available, otherwise float32 on CPU
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        device = "cuda" if torch.cuda.is_available() else "cpu"

        _blip_model = Blip2ForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=dtype,
        ).to(device)

        logger.info("BLIP-2 model loaded on %s (dtype=%s)", device, dtype)
    return _blip_processor, _blip_model


def _generate_blip_caption(img: PILImage) -> str:
    """Generate a natural-language caption using BLIP-2.

    Uses beam search with a conditional prompt for higher quality output.
    """
    try:
        import torch

        processor, model = _get_blip_model()
        device = next(model.parameters()).device

        # Convert to RGB (BLIP-2 requires RGB input)
        rgb_img = img.convert("RGB") if img.mode != "RGB" else img

        # Resize to avoid excessive memory usage
        rgb_img = _resize_for_captioning(rgb_img)

        # Conditional prompt guides the model toward descriptive captions
        inputs = processor(
            images=rgb_img,
            text="a photograph of",
            return_tensors="pt",
        ).to(device, dtype=torch.float16 if device.type == "cuda" else torch.float32)

        output_ids = model.generate(
            **inputs,
            max_new_tokens=80,
            num_beams=5,
            length_penalty=1.2,
            repetition_penalty=1.5,
            early_stopping=True,
        )
        caption = processor.decode(output_ids[0], skip_special_tokens=True).strip()

        # Remove the prompt prefix if the model echoed it back
        prefix = "a photograph of"
        if caption.lower().startswith(prefix):
            caption = caption[len(prefix):].strip()

        # Capitalize first letter
        if caption:
            caption = caption[0].upper() + caption[1:]

        logger.info("BLIP-2 caption: %s", caption)
        return caption
    except ImportError:
        logger.error(
            "transformers package not installed — skipping BLIP-2 captioning"
        )
        return ""
    except Exception:
        logger.exception("BLIP-2 captioning failed, falling back to YOLO-only")
        return ""


# ── YOLO object detection ─────────────────────────────

_yolo_model = None


def _get_yolo_model():
    """Lazy-load YOLOv8 nano model."""
    global _yolo_model
    if _yolo_model is None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "The 'ultralytics' package is required for object detection. "
                "Install it with: pip install ultralytics"
            ) from exc

        logger.info("Loading YOLOv8n model...")
        _yolo_model = YOLO("yolov8n.pt")
        logger.info("YOLOv8n model loaded")
    return _yolo_model


def _detect_objects(img: PILImage, confidence: float = 0.35) -> list[str]:
    """Run YOLOv8 on an image and return unique detected class names."""
    try:
        model = _get_yolo_model()
    except ImportError:
        logger.error("ultralytics package not installed — skipping object detection")
        return []

    try:
        results = model.predict(source=img, conf=confidence, verbose=False)
        detected: set[str] = set()
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                cls_name = result.names[cls_id]
                detected.add(cls_name)
        logger.info("YOLO detected %d unique objects", len(detected))
        return sorted(detected)
    except Exception:
        logger.exception("YOLO object detection failed")
        return []


def _generate_caption_from_objects(objects: list[str], image_size: tuple[int, int]) -> str:
    """Fallback caption from YOLO objects when BLIP captioning fails."""
    if not objects:
        return "An image that could not be automatically described."

    w, h = image_size
    orientation = "landscape" if w > h else "portrait" if h > w else "square"

    if len(objects) == 1:
        return f"A {orientation} image containing a {objects[0]}."
    elif len(objects) == 2:
        return f"A {orientation} image containing a {objects[0]} and a {objects[1]}."
    else:
        items = ", ".join(objects[:-1]) + f", and {objects[-1]}"
        return f"A {orientation} image containing {items}."


# ── public API ──────────────────────────────────────


async def process_image(file_bytes: bytes) -> ImageMetadata:
    """Full image processing pipeline.

    Steps:
        1. Open the image and extract EXIF metadata (GPS → location, datetime).
        2. Run YOLO object detection for supplementary object tags.
        3. Generate a natural-language caption using BLIP-2.
        4. If BLIP-2 caption is empty, fall back to YOLO-based caption.

    Returns:
        ``ImageMetadata`` with caption, detected objects, location, and timestamp.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(file_bytes))
    width, height = img.size

    # 1) EXIF
    exif = _extract_exif(img)
    location = _parse_location_from_exif(exif)
    timestamp = _parse_datetime_from_exif(exif)

    # 2) YOLO object detection (always run — objects enrich RAG payloads)
    objects = _detect_objects(img)

    # 3) BLIP-2 captioning (primary)
    caption = _generate_blip_caption(img)

    # 4) Fallback: if BLIP-2 failed, build caption from YOLO objects
    if not caption:
        caption = _generate_caption_from_objects(objects, (width, height))

    metadata = ImageMetadata(
        caption=caption,
        objects=objects,
        location=location,
        timestamp=timestamp,
        width=width,
        height=height,
    )
    logger.info(
        "Image processed: %dx%d, caption='%s', %d objects, location=%s",
        width, height, caption[:80], len(objects), location,
    )
    return metadata
