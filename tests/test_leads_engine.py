import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timedelta, timezone

from src.leads_engine import LeadsEngine


def test_capture_is_idempotent_and_exports_csv(tmp_path):
    engine = LeadsEngine(str(tmp_path / "leads.db"))
    first = engine.capture_lead("+55 (14) 98112-3802", name="Marcos", source="test")
    second = engine.capture_lead("5514981123802", email="marcos@example.com", source="test")
    assert first["created"] is True
    assert second["created"] is False
    assert second["lead"]["email"] == "marcos@example.com"
    assert "phone_number" in engine.export_csv()
    assert len(engine.list_leads()) == 1


def test_preview_expires_and_converts_to_hot_lead(tmp_path):
    engine = LeadsEngine(str(tmp_path / "leads.db"))
    preview = engine.create_preview("tenant_demo", "FAQ da empresa")
    assert preview["id"].startswith("preview_")
    assert preview["status"] == "active"
    assert datetime.fromisoformat(preview["expires_at"]) > datetime.now(timezone.utc)
    converted = engine.convert_preview(preview["id"], "5514981123802", "Visitante")
    assert converted["lead"]["status"] == "hot"
    assert converted["preview"]["status"] == "converted"


def test_cleanup_marks_expired_previews(tmp_path):
    engine = LeadsEngine(str(tmp_path / "leads.db"))
    preview = engine.create_preview("default", "texto")
    with engine._connect() as conn:
        conn.execute("UPDATE previews SET expires_at=? WHERE id=?", ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), preview["id"]))
    assert engine.cleanup_expired_previews() == 1
    assert engine.get_preview(preview["id"])["status"] == "expired"
