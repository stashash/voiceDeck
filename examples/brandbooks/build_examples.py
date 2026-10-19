"""Build redistributable synthetic brandbook/content examples (Pillow, ReportLab, openpyxl)."""
from pathlib import Path
from io import BytesIO
import csv
import json
import shutil
import zipfile
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend/public/brandbooks"
OUT.mkdir(parents=True, exist_ok=True)
FONT = ROOT / "designer/fonts/Play-Regular.ttf"
pdfmetrics.registerFont(TTFont("Play", str(FONT)))
TOKENS = {
    "colors": {"background": "F8FAFC", "surface": "EEF2F7", "text": "162032", "text_muted": "A7B0BF", "accent": "713CDA", "accent_alt": "14B8A6"},
    "fonts": {"heading": "Play", "body": "Play"},
    "type_scale": {"title": 30, "heading": 24, "body": 16, "caption": 10},
    "margins": {"left": .06, "top": .06, "right": .06, "bottom": .10},
    "chart_style": {"label_size_pt": 12, "gridline_color": "DDE3EB", "gridline_width_pt": .5, "legend_position": "bottom"},
}
RULES = {"grid_columns": 12, "grid_gutter": .018, "logo": "assets/local-logo.png", "logo_box": [.86, .035, .10, .06], "clear_space": .015}
(OUT / "local-tokens.json").write_text(json.dumps({"tokens": TOKENS, "rules": {k: v for k, v in RULES.items() if k != "logo"}}, indent=2), encoding="utf-8")
logo = Image.new("RGBA", (400, 100))
draw = ImageDraw.Draw(logo)
draw.rounded_rectangle((0, 0, 399, 99), radius=22, fill="#713CDA")
draw.text((28, 13), "LOCAL DEMO", font=ImageFont.truetype(str(FONT), 54), fill="white")
buffer = BytesIO(); logo.save(buffer, format="PNG"); logo_raw = buffer.getvalue()
sample = Image.new("RGB", (1280, 720), "#F8FAFC")
d = ImageDraw.Draw(sample)
d.text((76, 70), "Revenue increased by 30%", fill="#162032", font=ImageFont.truetype(str(FONT), 44))
d.line((80, 575, 1180, 575), fill="#A7B0BF", width=2)
for index, height in enumerate((180, 215, 205, 265, 300, 350)):
    x = 140 + index * 165
    d.rectangle((x, 575 - height, x + 95, 575), fill="#713CDA")
d.text((76, 655), "Source: synthetic data. USD, Jan-Jun 2026.", fill="#162032", font=ImageFont.truetype(str(FONT), 20))
preview = BytesIO(); sample.save(preview, format="PNG")
with zipfile.ZipFile(OUT / "local-brandbook.zip", "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("tokens.json", json.dumps({"tokens": TOKENS, "rules": RULES}, indent=2))
    z.writestr("assets/local-logo.png", logo_raw)
    z.writestr("assets/slide-example.png", preview.getvalue())
with zipfile.ZipFile(OUT / "local-assets-only.zip", "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("local-logo.png", logo_raw)
    z.writestr("slide-example.png", preview.getvalue())
pdf = canvas.Canvas(str(OUT / "local-brandbook.pdf"), pagesize=(720, 960))
pdf.setFont("Play", 25); pdf.drawString(48, 900, "LOCAL DEMO — brand guide")
y = 850
for role, color in TOKENS["colors"].items():
    pdf.setFillColorRGB(*(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)))
    pdf.rect(48, y - 8, 42, 23, fill=1, stroke=0)
    pdf.setFillColorRGB(.08, .10, .15); pdf.setFont("Play", 14)
    pdf.drawString(112, y, f"{role}: #{color}"); y -= 42
for line in ["heading font: Play", "body font: Play", "title size: 30", "body size: 16", "caption size: 10", "margins: 0.06, 0.06, 0.06, 0.10", "grid columns: 12", "Logo: approved mark, top right with clear space"]:
    pdf.drawString(48, y, line); y -= 28
from reportlab.lib.utils import ImageReader
pdf.drawImage(ImageReader(BytesIO(logo_raw)), 48, y - 70, width=240, height=60, mask="auto")
pdf.save()
content = ROOT / "artifacts/stage2-demo/content-v2"
content.mkdir(parents=True, exist_ok=True)
fixtures = ROOT / "designer/tests/fixtures/semantic_stage2"
for path in fixtures.iterdir():
    if path.suffix in {".csv", ".json", ".md"} and path.name not in {"README.md", "time_series.csv"}:
        shutil.copyfile(path, content / path.name)
book = Workbook(); sheet = book.active; sheet.title = "Monthly revenue"
with (fixtures / "time_series.csv").open(encoding="utf-8-sig", newline="") as file:
    for index, row in enumerate(csv.reader(file)):
        sheet.append(row if index == 0 else [row[0], float(row[1])])
book.save(content / "time_series.xlsx")
print(json.dumps({"examples": str(OUT), "content": str(content), "files": [p.name for p in OUT.iterdir()]}))
