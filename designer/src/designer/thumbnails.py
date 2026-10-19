"""Bounded thumbnail cache; full-resolution slide exports remain untouched."""
from functools import lru_cache
from io import BytesIO
from PIL import Image


@lru_cache(maxsize=128)
def slide_thumbnail(path: str, modified_ns: int, size: int) -> bytes:
    # Timestamp and file length invalidate cached bytes after every render.
    with Image.open(path) as image:
        image.thumbnail((320, 200), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.convert("RGB").save(output, format="WEBP", quality=82)
        return output.getvalue()
