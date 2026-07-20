from app.services.leads_export import _segment_for_record, _split_leads, lead_segment


def _record(form_id: str, i_am_a: str | None = None) -> dict:
    fields = {"phone_number": "999"}
    if i_am_a is not None:
        fields["i_am_a"] = i_am_a
    return {"id": "lead", "form_id": form_id, "fields": fields}


def test_parent_answer_routes_to_parents():
    record = _record("2023094392418250", "Parent looking for a home tutor for my child")
    assert _segment_for_record(record) == "parents"


def test_student_answer_on_parent_form_routes_to_tutors():
    record = _record("2023094392418250", "Student who needs a tutor")
    assert _segment_for_record(record) == "tutors"


def test_answer_overrides_form_id_mapping():
    # Parent answer submitted on a known tutor form still counts as a parent.
    record = _record("3888828671411723", "Parent looking for a home tutor for my child")
    assert _segment_for_record(record) == "parents"


def test_fallback_to_form_id_when_no_answer():
    assert _segment_for_record(_record("3888828671411723")) == "tutors"
    assert _segment_for_record(_record("2023094392418250")) == "parents"


def test_findmyteacher_form_routes_to_tutors():
    assert _segment_for_record(_record("2512058025921166")) == "tutors"


def test_getparent_new_form_routes_to_parents():
    assert _segment_for_record(_record("4495668977342555")) == "parents"


def test_unknown_form_is_unclassified():
    assert _segment_for_record(_record("0000000000000000")) is None


def test_split_leads_partitions_records():
    records = [
        _record("2023094392418250", "Parent looking for a home tutor for my child"),
        _record("2023094392418250", "Student who needs a tutor"),
        _record("3888828671411723"),
        _record("0000000000000000"),  # unknown form -> unclassified
    ]
    tutors, parents, unclassified = _split_leads(records)
    assert len(parents) == 1
    assert len(tutors) == 2
    assert len(unclassified) == 1


def test_lead_segment_matches_segment_for_record():
    for form_id in ("2512058025921166", "4495668977342555", "0000000000000000"):
        record = _record(form_id)
        assert lead_segment(form_id, record["fields"]) == _segment_for_record(record)


def test_junked_parent_excluded_from_parents_export():
    from app.services.leads_export import _split_leads as split

    records = [
        {"id": "keep", "form_id": "4495668977342555", "fields": {}, "is_junk": False},
        {"id": "junk", "form_id": "4495668977342555", "fields": {}, "is_junk": True},
    ]
    _tutors, parents, _unclassified = split(records)
    # Both are parent-segment; export keeps only the non-junk one.
    exported = [r for r in parents if not r.get("is_junk")]
    assert len(parents) == 2
    assert [r["id"] for r in exported] == ["keep"]


def test_junk_and_gold_excluded_from_parents_export():
    from app.services.leads_export import GOLD_STATUS, _split_leads as split

    records = [
        {"id": "keep", "form_id": "4495668977342555", "fields": {}, "is_junk": False, "status": None},
        {"id": "junk", "form_id": "4495668977342555", "fields": {}, "is_junk": True, "status": None},
        {"id": "gold", "form_id": "4495668977342555", "fields": {}, "is_junk": False, "status": GOLD_STATUS},
    ]
    _tutors, parents, _unclassified = split(records)
    exported = [
        r for r in parents if not r.get("is_junk") and r.get("status") != GOLD_STATUS
    ]
    assert [r["id"] for r in exported] == ["keep"]


def test_incremental_export_merges_existing_gcs_snapshot(monkeypatch):
    from app.services import leads_export

    existing = {
        "leads": [
            {"id": "old", "created_time": "2026-07-01T00:00:00+00:00"},
            {"id": "replace", "created_time": "2026-07-02T00:00:00+00:00", "old": True},
        ]
    }
    monkeypatch.setattr(leads_export.gcs_store, "read_json", lambda *_args: existing)
    settings = type("Settings", (), {"gcs_leads_prefix": "meta-ads/leads"})()
    merged = leads_export._merge_export_snapshot(
        settings,
        [
            {"id": "replace", "created_time": "2026-07-03T00:00:00+00:00"},
            {"id": "new", "created_time": "2026-07-04T00:00:00+00:00"},
        ],
        segment="tutors",
        filename="tutors.json",
    )
    assert [record["id"] for record in merged] == ["new", "replace", "old"]
