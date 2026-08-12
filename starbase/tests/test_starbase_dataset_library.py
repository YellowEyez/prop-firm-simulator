from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

import starbase_dataset_library as lib
from starbase_dataset_library import NamedBytesIO, infer_chart_interval, suggested_dataset_name


def _tv_csv_bytes():
    cols = [
        "Trade number","Type","Date and time","Signal","Price USD","Size (qty)",
        "Net PnL USD","Commission USD","Favorable excursion USD","Adverse excursion USD","Duration (bars)"
    ]
    rows = [
        [1,"Exit long","2025-01-02 10:01:40","TP",100.5,1,8,2,12,-4,10],
        [1,"Entry long","2025-01-02 10:00:00","LE",100.0,1,8,2,12,-4,10],
        [2,"Exit long","2026-01-02 10:03:20","TP",101.0,1,18,2,22,-3,10],
        [2,"Entry long","2026-01-02 10:01:40","LE",100.0,1,18,2,22,-3,10],
    ]
    return pd.DataFrame(rows, columns=cols).to_csv(index=False).encode()


def test_interval_inference_prefers_duration_bar_ratio():
    df = pd.DataFrame({"seconds_per_bar": [10,10,10,10.1,9.9,10]})
    result = infer_chart_interval(df)
    assert result.label == "10s"
    assert result.seconds == 10.0
    assert result.confidence > 0.8


def test_suggested_name_uses_interval_and_year_range():
    assert suggested_dataset_name("Sydney_01", "10s", 2025, 2026) == "Sydney_10s_2025-2026"


def test_save_load_delete_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "LIBRARY_DIR", tmp_path / "library")
    src = NamedBytesIO(_tv_csv_bytes(), "Sydney_part_01.csv")
    manifest = lib.save_dataset(
        [src], display_name="Sydney_10s_2025-2026", strategy_id="Sydney", profile_id="1NQ", notes="baseline"
    )
    assert manifest["display_name"] == "Sydney_10s_2025-2026"
    assert manifest["chart_interval_detected"] == "10s"
    assert manifest["start_year"] == 2025
    assert manifest["end_year"] == 2026
    assert len(lib.list_datasets()) == 1
    loaded = lib.load_dataset_sources(manifest["dataset_id"])
    assert len(loaded) == 1
    assert loaded[0].name.endswith(".csv")
    assert loaded[0].getvalue() == _tv_csv_bytes()
    assert lib.delete_dataset(manifest["dataset_id"]) is True
    assert lib.list_datasets() == []


def test_vault_round_trip(tmp_path, monkeypatch):
    first = tmp_path / "library1"
    second = tmp_path / "library2"
    monkeypatch.setattr(lib, "LIBRARY_DIR", first)
    src = NamedBytesIO(_tv_csv_bytes(), "Sydney_part_01.csv")
    manifest = lib.save_dataset([src], display_name="Sydney", strategy_id="Sydney", profile_id="1NQ", notes="hello")
    vault = lib.export_dataset_vault()
    assert len(vault) > 100

    monkeypatch.setattr(lib, "LIBRARY_DIR", second)
    result = lib.import_dataset_vault(vault)
    assert result["imported"] == [manifest["dataset_id"]]
    restored = lib.get_dataset(manifest["dataset_id"])
    assert restored["notes"] == "hello"
    assert lib.load_dataset_sources(manifest["dataset_id"])[0].getvalue() == _tv_csv_bytes()
