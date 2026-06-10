"""File-based deal library: deals/<deal_id>/deal.json + versions/ snapshots."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..models.deal import Deal

CURRENT_SCHEMA_VERSION = 1

# migration chain: schema_version -> fn(dict) -> dict (bumped one version)
_MIGRATIONS: dict[int, callable] = {}


def _migrate(data: dict) -> dict:
    version = data.get("schema_version", 1)
    while version < CURRENT_SCHEMA_VERSION:
        fn = _MIGRATIONS.get(version)
        if fn is None:
            raise ValueError(f"no migration from schema_version {version}")
        data = fn(data)
        version = data["schema_version"]
    return data


class DealLibrary:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- listing

    def list(self) -> list[dict]:
        out = []
        for deal_file in sorted(self.root.glob("*/deal.json")):
            try:
                data = json.loads(deal_file.read_text())
                out.append(
                    {
                        "id": data.get("id", deal_file.parent.name),
                        "name": data.get("name", ""),
                        "description": data.get("description", ""),
                        "num_periods": data.get("num_periods"),
                        "num_classes": len(data.get("structure", {}).get("classes", [])),
                    }
                )
            except (json.JSONDecodeError, OSError):
                continue
        return out

    # ------------------------------------------------------------- CRUD

    def load(self, deal_id: str) -> Deal:
        path = self._deal_path(deal_id)
        if not path.exists():
            raise FileNotFoundError(f"deal {deal_id!r} not found")
        data = _migrate(json.loads(path.read_text()))
        return Deal.model_validate(data)

    def save(self, deal: Deal) -> None:
        deal_dir = self.root / _safe_id(deal.id)
        deal_dir.mkdir(parents=True, exist_ok=True)
        path = deal_dir / "deal.json"
        payload = deal.model_dump_json(indent=2)
        if path.exists():  # snapshot the previous version before overwriting
            versions = deal_dir / "versions"
            versions.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            (versions / f"{stamp}.json").write_text(path.read_text())
        path.write_text(payload)

    def delete(self, deal_id: str) -> None:
        deal_dir = self.root / _safe_id(deal_id)
        if not deal_dir.exists():
            raise FileNotFoundError(f"deal {deal_id!r} not found")
        import shutil

        shutil.rmtree(deal_dir)

    def clone(self, deal_id: str, new_id: str, new_name: str | None = None) -> Deal:
        deal = self.load(deal_id)
        cloned = deal.model_copy(update={"id": new_id, "name": new_name or f"{deal.name} (copy)"})
        if self._deal_path(new_id).exists():
            raise FileExistsError(f"deal {new_id!r} already exists")
        self.save(cloned)
        return cloned

    def versions(self, deal_id: str) -> list[str]:
        vdir = self.root / _safe_id(deal_id) / "versions"
        if not vdir.exists():
            return []
        return sorted(p.stem for p in vdir.glob("*.json"))

    # ------------------------------------------------------------- templates

    def templates(self) -> list[dict]:
        tdir = self.root / "templates"
        out = []
        if tdir.exists():
            for p in sorted(tdir.glob("*.json")):
                try:
                    data = json.loads(p.read_text())
                    out.append(
                        {
                            "template": p.stem,
                            "name": data.get("name", p.stem),
                            "description": data.get("description", ""),
                        }
                    )
                except (json.JSONDecodeError, OSError):
                    continue
        return out

    def load_template(self, template: str) -> Deal:
        path = self.root / "templates" / f"{_safe_id(template)}.json"
        if not path.exists():
            raise FileNotFoundError(f"template {template!r} not found")
        data = _migrate(json.loads(path.read_text()))
        return Deal.model_validate(data)

    def _deal_path(self, deal_id: str) -> Path:
        return self.root / _safe_id(deal_id) / "deal.json"


def _safe_id(deal_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", deal_id):
        raise ValueError(f"invalid deal id {deal_id!r} (use letters, digits, -, _)")
    return deal_id
