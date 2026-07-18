from datetime import date

import pandas as pd

from app.meta.insights_sync import _insights_cursor


def test_insights_cursor_reads_manifest_key():
    manifest = {"cursors": {"insights": "2026-06-10"}}
    assert _insights_cursor(manifest) == "2026-06-10"


def test_insights_cursor_legacy_key():
    manifest = {"cursors": {"insights:last_date": "2026-06-08"}}
    assert _insights_cursor(manifest) == "2026-06-08"


def test_merge_parquet_partition_keeps_all_objects(monkeypatch):
    from app.config import Settings
    from app.services import gcs_store

    settings = Settings(meta_access_token="test")
    day = date(2026, 6, 1)

    existing = pd.DataFrame(
        [
            {
                "date": day,
                "level": "campaign",
                "object_id": "c1",
                "spend": 100,
                "leads": 5,
            }
        ]
    )
    incoming = pd.DataFrame(
        [
            {
                "date": day,
                "level": "campaign",
                "object_id": "c2",
                "spend": 50,
                "leads": 2,
            },
            {
                "date": day,
                "level": "campaign",
                "object_id": "c1",
                "spend": 110,
                "leads": 6,
            },
        ]
    )

    written: list[pd.DataFrame] = []

    monkeypatch.setattr(gcs_store, "read_parquet_partition", lambda _s, _d: existing.copy())
    monkeypatch.setattr(
        gcs_store,
        "write_parquet_partition",
        lambda _s, _d, df: written.append(df.copy()) or "url",
    )

    gcs_store.merge_parquet_partition(settings, day, incoming)

    assert len(written) == 1
    merged = written[0]
    assert len(merged) == 2
    c1 = merged[merged["object_id"] == "c1"].iloc[0]
    assert c1["spend"] == 110
    assert set(merged["object_id"]) == {"c1", "c2"}
