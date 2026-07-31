from __future__ import annotations

from nexus_proof_runtime import ReceiptStore


def test_receipt_store_context_manager_releases_database(tmp_path) -> None:
    database = tmp_path / "receipts.db"

    with ReceiptStore(database):
        assert database.is_file()

    database.unlink()
    assert not database.exists()
