"""Rasterize the limited Vynx SVG geometry into Windows app and tray assets."""
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent
source = ET.parse(root / "vynx-app.svg").getroot()
scale = 4
image = Image.new("RGBA", (256 * scale, 256 * scale))
draw = ImageDraw.Draw(image)
for element in source:
    tag = element.tag.split("}")[-1]
    if tag == "rect":
        x, y, w, h = (float(element.attrib[k]) for k in ("x", "y", "width", "height"))
        draw.rounded_rectangle(
            (x * scale, y * scale, (x + w) * scale, (y + h) * scale),
            radius=float(element.attrib["rx"]) * scale,
            fill=element.attrib["fill"], outline=element.attrib["stroke"],
            width=int(element.attrib["stroke-width"]) * scale,
        )
    elif tag == "polygon":
        points = [tuple(float(c) * scale for c in point.split(","))
                  for point in element.attrib["points"].split()]
        draw.polygon(points, fill=element.attrib["fill"])
    else:
        raise ValueError(f"Unsupported icon geometry: {tag}")
image = image.resize((256, 256), Image.Resampling.LANCZOS)
image.save(root / "icon.png")
image.resize((128, 128), Image.Resampling.LANCZOS).save(root / "vynx-app-128.png")
for name in ("icon.ico", "tray-icon.ico"):
    image.save(root / name, sizes=[(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
print("Generated app, window and tray icons from vynx-app.svg")
