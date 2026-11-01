from __future__ import annotations

import json
import os
from dataclasses import replace

import pytest

import biocall_studio.detect.persistence.export_history as export_history_module
from biocall_studio.detect.domain.export_history import ExportHistoryRecord
from biocall_studio.detect.domain.exports import ExportMode
from biocall_studio.detect.persistence.export_history import ExportHistoryStore


def _record(suffix: str = "1", *, completed_at: str = "2026-10-31T10:00:00.000Z"):
    token = suffix * 32
    return ExportHistoryRecord(
        schema_version=1,
        collection_id="det_" + "a" * 32,
        export_id="exp_" + token,
        receipt_digest=suffix * 64,
        snapshot_digest="b" * 64,
        result_id="pub_" + "c" * 32,
        result_digest="d" * 64,
        mode=ExportMode.BOTH,
        completed_at=completed_at,
        selected_call_count=3,
        published_file_count=6,
        destination_uri=f"file:///private/export-{suffix}",
    )


def test_export_history_schema_order_identity_containment_and_atomic_recovery(
    tmp_path, monkeypatch
):
    """Case: UT-DET-026."""
    collection_root = tmp_path / "collection"
    collection_root.mkdir()
    (collection_root / "exports").mkdir()
    store = ExportHistoryStore(collection_root, "det_" + "a" * 32)
    older = _record("1", completed_at="2026-10-31T09:00:00.000Z")
    newer = _record("2", completed_at="2026-10-31T11:00:00.000Z")

    assert ExportHistoryRecord.from_dict(older.to_dict()) == older
    store.save(older)
    store.save(newer)
    store.save(newer)  # exact retries are idempotent
    loaded = store.load()
    assert loaded.records == (newer, older)
    assert not loaded.rejected
    with monkeypatch.context() as bounded:
        bounded.setattr(export_history_module, "MAX_EXPORT_HISTORY_RECORDS", 1)
        assert store.load().records == (newer,)

    with pytest.raises(ValueError, match="different completed export"):
        store.save(replace(newer, published_file_count=7))
    with pytest.raises(ValueError, match="different Collection"):
        store.save(replace(newer, collection_id="det_" + "f" * 32))
    with pytest.raises(ValueError, match="document is invalid"):
        ExportHistoryRecord.from_dict({**older.to_dict(), "extra": True})

    corrupt = store.exports_root / ("exp_" + "3" * 32 + ".json")
    corrupt.write_text("{", encoding="utf-8")
    symlink = store.exports_root / ("exp_" + "4" * 32 + ".json")
    symlink.symlink_to(store.path_for(older.export_id))
    ignored = store.exports_root / ".interrupted.tmp"
    ignored.write_text(json.dumps(newer.to_dict()), encoding="utf-8")
    partial = store.load()
    assert partial.records == (newer, older)
    assert {item.name for item in partial.rejected} == {corrupt.name, symlink.name}

    attempted = _record("5")
    real_link = os.link

    def fail_link(source, destination, *, follow_symlinks=True):
        if str(destination).endswith(f"{attempted.export_id}.json"):
            raise OSError("simulated link failure")
        return real_link(source, destination, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OSError, match="simulated link failure"):
        store.save(attempted)
    assert not store.path_for(attempted.export_id).exists()
    assert store.load().records == (newer, older)

    outside = tmp_path / "outside"
    outside.mkdir()
    unsafe_root = tmp_path / "unsafe"
    unsafe_root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe"):
        ExportHistoryStore(unsafe_root, older.collection_id)
