import json

from PIL import Image

from groundstation.services.gallery import scan_gallery, store_result


def test_rebuild_from_disk_ignores_partial_metadata(tmp_path):
    source = tmp_path / "source.jpg"
    Image.new("RGB", (80, 80)).save(source)
    root = tmp_path / "gallery"
    metadata = {"satellite": "METOP-C", "aos": "2026-09-29T12:00:00+00:00", "max_elevation": 65}
    path = store_result(root, source, metadata)
    with Image.open(path / "avhrr.png") as image:
        assert image.format == "PNG"
    assert json.loads((path / "metadata.json").read_text()) == metadata
    bad = root / "2026" / "partial"
    bad.mkdir()
    (bad / "metadata.json").write_text("broken")
    assert len(scan_gallery(root)) == 1
    hidden = root / "2026" / ".pending-test"
    hidden.mkdir()
    (hidden / "metadata.json").write_text(json.dumps(metadata))
    Image.new("RGB", (80, 80)).save(hidden / "avhrr.png")
    assert len(scan_gallery(root)) == 1
