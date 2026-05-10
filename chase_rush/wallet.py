"""Persistent player wallet — saved to a CSV database between runs."""

from __future__ import annotations

import csv
import os
from typing import Dict, List

from . import config


class Wallet:
    """Tracks money earned from banknotes across sessions.

    The balance is stored in a small CSV file (key,value) so the money
    survives closing the game. Any change (earning or spending) flushes
    immediately so a crash never loses progress.

    CSV layout (header included):
        key,value
        balance,123
        total_earned,456
    """

    _FIELDS: List[str] = ["key", "value"]

    def __init__(self, path: str | None = None) -> None:
        self.path = path or config.WALLET_CSV
        self.balance: int = 0
        self.total_earned: int = 0
        self._load()

    def _load(self) -> None:
        """Read the CSV; on any error / missing file, start at zero."""
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                data: Dict[str, str] = {
                    row["key"]: row["value"]
                    for row in reader
                    if row and row.get("key") is not None
                }
            self.balance = int(data.get("balance", 0))
            self.total_earned = int(data.get("total_earned", 0))
        except (OSError, ValueError, KeyError, csv.Error):
            self.balance = 0
            self.total_earned = 0

    def _save(self) -> None:
        """Rewrite the CSV in full (tiny file, atomic-enough for this use)."""
        try:
            config.ensure_parent_dir(self.path)
            with open(self.path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._FIELDS)
                writer.writeheader()
                writer.writerow({"key": "balance", "value": self.balance})
                writer.writerow({"key": "total_earned", "value": self.total_earned})
        except OSError:
            pass

    def add(self, amount: int) -> None:
        if amount <= 0:
            return
        amt = int(amount)
        self.balance += amt
        self.total_earned += amt
        self._save()

    def spend(self, amount: int) -> bool:
        """Deduct amount if affordable; return True on success."""
        if amount <= 0 or self.balance < amount:
            return False
        self.balance -= int(amount)
        self._save()
        return True
