from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from api.hwp_worker.com_driver import ComDriverError
from api.hwp_worker.page_images import render


@pytest.mark.parametrize("edge", [False, True])
def test_page_images_reject_visible_edge_overflow(tmp_path, edge):
    def create(path, number, dpi, depth, fmt):
        assert (number, dpi, depth, fmt) == (0, 96, 24, "bmp")
        image = Image.new("RGB", (794, 1122), "white")
        ImageDraw.Draw(image).rectangle((70, 100, 793 if edge else 720, 150), fill="black")
        image.save(path)
        return True
    hwp = SimpleNamespace(PageCount=1, CreatePageImage=create)
    if edge:
        with pytest.raises(ComDriverError, match="page_content_reaches_edge"):
            render(hwp, tmp_path / "draft.hwp")
    else:
        result = render(hwp, tmp_path / "draft.hwp")
        assert result[0]["edge_check"] == "passed"
        assert Path(result[0]["path"]).is_file()


def test_page_image_failure_does_not_report_partial_success(tmp_path):
    with pytest.raises(ComDriverError, match="page_image_failed"):
        render(SimpleNamespace(PageCount=1, CreatePageImage=lambda *args: False), tmp_path / "draft.hwp")
