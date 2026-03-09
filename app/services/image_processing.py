"""Image processing: EXIF extraction, YOLO object detection, and caption generation."""

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

logger = logging.getLogger(__name__)


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


def _extract_exif(img: Image.Image) -> dict:
    """Extract useful EXIF data from a PIL Image."""
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


# ── YOLO object detection ─────────────────────────────

_yolo_model = None


def _get_yolo_model():
    """Lazy-load YOLOv8 nano model."""
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        logger.info("Loading YOLOv8n model...")
        _yolo_model = YOLO("yolov8n.pt")
        logger.info("YOLOv8n model loaded")
    return _yolo_model


def _detect_objects(img: Image.Image, confidence: float = 0.35) -> list[str]:
    """Run YOLOv8 on an image and return unique detected class names."""
    model = _get_yolo_model()
    results = model.predict(source=img, conf=confidence, verbose=False)
    detected: set[str] = set()
    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            cls_name = result.names[cls_id]
            detected.add(cls_name)
    logger.info("YOLO detected %d unique objects", len(detected))
    return sorted(detected)


def _generate_caption_from_objects(objects: list[str], image_size: tuple[int, int]) -> str:
    """Build a descriptive caption from detected objects.

    Uses YOLO detection results to compose a natural language caption.
    """
    if not objects:
        return "An image with no clearly identifiable objects."

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
        2. Run YOLO object detection to identify objects in the image.
        3. Generate a caption from detected objects.

    Returns:
        ``ImageMetadata`` with caption, detected objects, location, and timestamp.
    """
    img = Image.open(io.BytesIO(file_bytes))
    width, height = img.size

    # 1) EXIF
    exif = _extract_exif(img)
    location = _parse_location_from_exif(exif)
    timestamp = _parse_datetime_from_exif(exif)

    # 2) Object detection
    objects = _detect_objects(img)

    # 3) Caption
    caption = _generate_caption_from_objects(objects, (width, height))

    metadata = ImageMetadata(
        caption=caption,
        objects=objects,
        location=location,
        timestamp=timestamp,
        width=width,
        height=height,
    )
    logger.info("Image processed: %dx%d, %d objects, location=%s", width, height, len(objects), location)
    return metadata
