"""Append-only audit log with a SHA-256 hash chain (each entry hashes the previous one)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

GENESIS = "0" * 64


def _digest(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def redact(params: dict) -> dict:
    """Mask card numbers and drop free text before logging."""
    out = {k: v for k, v in params.items() if k != "text"}
    if "card_number" in out:
        out["card_number"] = re.sub(r"\d(?=\d{4})", "*", re.sub(r"\D", "", str(out["card_number"])))
    return out


class AuditLog:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def add(self, tool: str, tier: str, decision: str, params: dict | None = None, reason: str = "") -> dict:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": tool,
            "tier": tier,
            "decision": decision,
            "params": redact(params or {}),
            "reason": reason,
            "prev": self.entries[-1]["hash"] if self.entries else GENESIS,
        }
        entry["hash"] = _digest(entry)
        self.entries.append(entry)
        return entry

    def verify(self) -> bool:
        prev = GENESIS
        for e in self.entries:
            if e["prev"] != prev or _digest(e) != e["hash"]:
                return False
            prev = e["hash"]
        return True

    def jsonl(self) -> str:
        return "\n".join(json.dumps(e, ensure_ascii=False) for e in self.entries)
