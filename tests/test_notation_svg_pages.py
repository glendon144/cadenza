from pathlib import Path

from render.notation import collect_svg_pages


def test_collect_svg_pages_returns_all_numbered_pages_in_order(tmp_path: Path):
    (tmp_path / "score-2.svg").write_text("<svg>2</svg>")
    (tmp_path / "score-1.svg").write_text("<svg>1</svg>")
    (tmp_path / "score-10.svg").write_text("<svg>10</svg>")

    pages = [Path(p).name for p in collect_svg_pages(tmp_path, "score")]

    assert pages == ["score-1.svg", "score-2.svg", "score-10.svg"]
