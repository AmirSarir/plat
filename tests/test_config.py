import json

from engops.app.config import Settings


def test_defaults_when_missing(tmp_path):
    assert Settings.load(tmp_path / "settings.json") == Settings()


def test_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    Settings(window_width=1000, window_height=700, last_page="process_library").save(path)
    loaded = Settings.load(path)
    assert (loaded.window_width, loaded.window_height, loaded.last_page) == (1000, 700, "process_library")


def test_corrupt_file_falls_back_and_is_kept(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert Settings.load(path) == Settings()
    assert (tmp_path / "settings.json.corrupt").exists()


def test_unknown_keys_ignored_and_bad_values_fixed(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"window_width": "abc", "window_height": 10, "future_option": True}),
        encoding="utf-8",
    )
    loaded = Settings.load(path)
    assert loaded.window_width == 1200  # invalid -> default
    assert loaded.window_height == 420  # too small -> minimum