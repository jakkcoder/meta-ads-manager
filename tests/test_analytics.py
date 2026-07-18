import pandas as pd

from app.dashboard.analytics import compute_kpis, funnel_metrics, pct_delta, cpl_style


def test_pct_delta():
    assert pct_delta(110, 100) == 10.0
    assert pct_delta(0, 0) is None
    assert pct_delta(50, 0) == 100.0


def test_funnel_metrics():
    df = pd.DataFrame(
        [
            {
                "level": "campaign",
                "date": "2026-06-01",
                "impressions": 1000,
                "clicks": 100,
                "leads": 10,
                "spend": 500,
                "segment": "tutors",
            }
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    m = funnel_metrics(df)
    assert m["ctr"] == 10.0
    assert m["click_to_lead"] == 10.0
    assert m["impression_to_lead"] == 1.0


def test_compute_kpis():
    rows = []
    for i in range(10):
        rows.append(
            {
                "level": "campaign",
                "date": f"2026-06-{i+1:02d}",
                "spend": 100 + i,
                "leads": 5,
                "impressions": 1000,
                "clicks": 50,
                "segment": "tutors",
                "object_name": "Gharkaguru_teacher_focus",
                "cpl": 20,
            }
        )
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    kpis = compute_kpis(df, days=7)
    assert len(kpis) == 4
    assert "₹" in kpis[0]["value"]


def test_cpl_style_thresholds():
    assert cpl_style(4.0)["color"] == "#22c55e"
    assert cpl_style(7.5)["color"] == "#f59e0b"
    assert cpl_style(12.0)["color"] == "#ef4444"
    assert cpl_style(None)["color"] == "#9ca3af"
