"""Document-local page images for separate human layout review."""
import hashlib
from pathlib import Path

from PIL import Image

from api.hwp_worker.com_driver import ComDriverError, _call, _success


def render(hwp, output: Path) -> list[dict]:
    count = _call("page_images", lambda: hwp.PageCount)
    if type(count) is not int or not 1 <= count <= 100:
        raise ComDriverError("invalid_page_count", "page_images")
    folder = output.parent / (output.stem + "-pages")
    folder.mkdir(exist_ok=False)
    pages = []
    for number in range(count):
        bitmap = folder / f"page-{number + 1:03d}.bmp"
        if not _success(_call("page_images", hwp.CreatePageImage, str(bitmap), number, 96, 24, "bmp")):
            raise ComDriverError("page_image_failed", "page_images")
        png = bitmap.with_suffix(".png")
        with Image.open(bitmap) as source:
            if source.width * source.height > 20_000_000:
                raise ComDriverError("page_image_too_large", "page_images")
            source.save(png, "PNG")
            width, height = source.size
            bounds = source.convert("L").point(lambda value: 255 if value < 220 else 0).getbbox()
            if bounds and (bounds[0] < 16 or bounds[1] < 16 or bounds[2] > width - 16 or bounds[3] > height - 16):
                raise ComDriverError("page_content_reaches_edge", "page_images")
        pages.append({"number": number + 1, "path": str(png), "width": width, "height": height,
                      "content_bounds": bounds, "edge_check": "passed",
                      "sha256": hashlib.sha256(png.read_bytes()).hexdigest()})
    return pages
