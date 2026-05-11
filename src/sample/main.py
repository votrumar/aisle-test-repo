"""Use Pillow only to *generate* solid-color PNGs.

We deliberately never call ``Image.open`` or any decoder, so the known CVEs
in Pillow 8.1.0 (TIFF / ICNS / SGI / BLP / etc. decoders) are not reachable
from this code. The vulnerable subsystems are imported transitively but
never invoked.
"""

import io

from PIL import Image


def make_solid_png(width: int = 100, height: int = 100, color: str = "red") -> bytes:
    """Create a solid-color PNG in memory. No external input is parsed."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    png = make_solid_png()
    print(f"Generated {len(png)} bytes of PNG.")
