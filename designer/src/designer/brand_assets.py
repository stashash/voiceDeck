"""Persist verified brand assets and resolve explicit logo placement."""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
import os
import re
import shutil
from PIL import Image
from designer.contracts import Asset, BrandRules
from designer.brandbook_import import BrandbookImportError, BrandbookImportResult


def save_brand_assets(package: Path, imported: BrandbookImportResult) -> tuple[list[Asset], BrandRules | None, list[dict]]:
    rules = dict(imported.rules or {})
    logo = rules.pop("logo", None)
    names = {asset.name for asset in imported.assets}
    if logo is None:
        logos = [name for name in names if re.search(r"logo|логотип", name, re.I)]
        logo = sorted(logos)[0] if len(logos) == 1 else None
    if logo is not None and logo not in names:
        raise BrandbookImportError("Logo rule refers to an image absent from the archive")
    assets, metadata = [], []
    for item in imported.assets:
        digest = hashlib.sha1(item.data).hexdigest()
        with Image.open(BytesIO(item.data)) as image:
            width, height = image.size
        asset = Asset(id=digest[:12], sha1=digest, path="brandbook-assets/" + item.name,
                      kind="logo" if item.name == logo else "decor", width_px=width, height_px=height)
        assets.append(asset)
        metadata.append({"name": item.name, "size": len(item.data), "sha256": hashlib.sha256(item.data).hexdigest(), "id": asset.id})
        if item.name == logo:
            rules["logo_asset"] = asset.id
    checked = BrandRules.model_validate(rules) if rules else None
    # Validate everything before replacing the previous imported assets.
    target = package / "brandbook-assets"
    staging = package / "brandbook-assets.next"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for item in imported.assets:
        path = staging.joinpath(*item.name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item.data)
    if target.exists():
        shutil.rmtree(target)
    os.replace(staging, target)
    return assets, checked, metadata


def embed_fonts(package, tokens):
    for font in tokens.fonts:
        if font.family != "Play":
            continue
        source = Path(__file__).resolve().parents[2] / "fonts/Play-Regular.ttf"
        if not source.is_file():
            source = Path("/usr/local/share/fonts/voicedeck/Play-Regular.ttf")
        if source.is_file():
            path = package / "fonts/brand-Play-Regular.ttf"
            path.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, path)
            font.embedded_file = "fonts/brand-Play-Regular.ttf"
            font.embedded_state = "extracted"
    return tokens
