"""Report actual exported similarity; do not promise distinct designs by variant name."""
from functools import lru_cache
import hashlib

from PIL import Image
from designer import store


@lru_cache(maxsize=512)
def _pixel_hash(path, modified_ns, size):
    with Image.open(path) as image:
        image = image.convert("RGB")
        return image.size, hashlib.sha256(image.tobytes()).hexdigest()


def compare_exported_variants(deck_id, variants):
    baseline = variants.get("a")
    if not baseline or baseline.status != "done" or not baseline.plan:
        return

    def hashes(code, state):
        if state.status != "done" or not state.plan:
            return None
        if state.revision and state.images_revision != state.revision:
            return None
        result = []
        for number in range(1, len(state.plan.slides) + 1):
            path = store.deck_variant_slide_path(deck_id, code, number)
            if path is None or not path.is_file():
                return None
            stat = path.stat()
            result.append(_pixel_hash(str(path), stat.st_mtime_ns, stat.st_size))
        return result

    try:
        base = hashes("a", baseline)
        if not base:
            return
        for code, state in variants.items():
            if code == "a":
                continue
            other = hashes(code, state)
            if other is None:
                continue
            same = sum(a == b for a, b in zip(base, other))
            total = max(len(base), len(other))
            state.comparison_to_a = {"basis": "exported_pixels", "same_pages": same, "total_pages": total,
                                     "exact_duplicate": same == total,
                                     "near_duplicate": same / total >= .8}
    except (OSError, ValueError):
        # In-progress image replacement is not evidence of a distinct design.
        return
