"""
state.py — Application State Variables for FlashSpend

Holds all runtime state: the transaction queue, categorisation progress,
history stack, and session metadata. Provides a clean AppState class plus
a module-level singleton.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────
# Transaction dataclass
# ──────────────────────────────────────────────

@dataclass
class Transaction:
    """
    Represents a single bank transaction.

    Fields set at parse time:
        index        — position in the original CSV (0-based)
        date         — ISO date string (YYYY-MM-DD)
        time         — HH:MM:SS string, or None
        description  — raw description from the CSV
        amount       — signed float (negative = debit, positive = credit)
        is_credit    — convenience bool
        sent_to      — counterparty name on debits (from UPI)
        receive_from — counterparty name on credits (from UPI)
        comment      — user remark from UPI, or None

    Fields set during triage:
        category     — selected category name, or None if not yet categorised
    """
    index:        int
    date:         str
    description:  str
    amount:       float
    is_credit:    bool
    time:         Optional[str]  = None
    sent_to:      Optional[str]  = None
    receive_from: Optional[str]  = None
    comment:      Optional[str]  = None
    category:     Optional[str]  = None

    @classmethod
    def from_dict(cls, d: dict) -> "Transaction":
        return cls(
            index=d["index"],
            date=d["date"],
            description=d["description"],
            amount=float(d["amount"]),
            is_credit=bool(d.get("is_credit", d["amount"] >= 0)),
            time=d.get("time"),
            sent_to=d.get("sent_to"),
            receive_from=d.get("receive_from"),
            comment=d.get("comment"),
            category=d.get("category"),
        )

    def to_dict(self) -> dict:
        return {
            "index":        self.index,
            "date":         self.date,
            "time":         self.time,
            "description":  self.description,
            "amount":       self.amount,
            "is_credit":    self.is_credit,
            "sent_to":      self.sent_to,
            "receive_from": self.receive_from,
            "comment":      self.comment,
            "category":     self.category,
        }


# ──────────────────────────────────────────────
# History entry (for undo)
# ──────────────────────────────────────────────

@dataclass
class HistoryEntry:
    """Records one categorisation action so it can be undone."""
    transaction: Transaction   # snapshot of the transaction before categorisation
    category:    str           # the category that was applied


# ──────────────────────────────────────────────
# AppState — central state container
# ──────────────────────────────────────────────

@dataclass
class AppState:
    """
    All mutable runtime state for one FlashSpend session.

    Attributes:
        session_id          — unique identifier for this session (epoch ms)
        filename            — name of the uploaded file, if any
        raw_headers         — original CSV column headers
        raw_rows            — original CSV rows as string lists
        transaction_queue   — transactions waiting to be categorised
        categorised         — transactions that have been tagged
        current_index       — pointer into transaction_queue
        history             — undo stack (most recent last)
        is_complete         — True when the queue is exhausted
        created_at          — Unix timestamp when the session started
        updated_at          — Unix timestamp of last state change
    """

    session_id:         str               = field(default_factory=lambda: str(int(time.time() * 1000)))
    filename:           Optional[str]     = None

    # Raw CSV data (preserved for export)
    raw_headers:        list[str]         = field(default_factory=list)
    raw_rows:           list[list[str]]   = field(default_factory=list)

    # Triage queues
    transaction_queue:  list[Transaction] = field(default_factory=list)
    categorised:        list[Transaction] = field(default_factory=list)

    # Progress pointer
    current_index:      int               = 0

    # Undo history
    history:            list[HistoryEntry]= field(default_factory=list)

    # Completion flag
    is_complete:        bool              = False

    # Timestamps
    created_at:         float             = field(default_factory=time.time)
    updated_at:         float             = field(default_factory=time.time)

    # ── Computed properties ────────────────────

    @property
    def total(self) -> int:
        """Total number of transactions in the session."""
        return len(self.transaction_queue) + len(self.categorised)

    @property
    def done_count(self) -> int:
        """Number of transactions already categorised."""
        return len(self.categorised)

    @property
    def remaining_count(self) -> int:
        """Number of transactions still in the queue."""
        return len(self.transaction_queue) - self.current_index

    @property
    def progress_pct(self) -> float:
        """Completion percentage (0.0 – 100.0)."""
        if self.total == 0:
            return 0.0
        return round(self.done_count / self.total * 100, 1)

    @property
    def current_transaction(self) -> Optional[Transaction]:
        """The transaction currently shown on the flashcard."""
        if 0 <= self.current_index < len(self.transaction_queue):
            return self.transaction_queue[self.current_index]
        return None

    # ── Mutation methods ──────────────────────

    def load(
        self,
        transactions: list[dict],
        raw_headers:  list[str],
        raw_rows:     list[list[str]],
        filename:     Optional[str] = None,
    ) -> None:
        """
        Initialise state from a freshly parsed CSV.
        Resets all progress.

        Args:
            transactions: list of transaction dicts from parser.parse_csv()
            raw_headers:  original CSV headers
            raw_rows:     original CSV data rows
            filename:     uploaded file name (for display)
        """
        self.filename          = filename
        self.raw_headers       = raw_headers
        self.raw_rows          = raw_rows
        self.transaction_queue = [Transaction.from_dict(t) for t in transactions]
        self.categorised       = []
        self.current_index     = 0
        self.history           = []
        self.is_complete       = False
        self._touch()

    def add_manual_transaction(self, data: dict) -> None:
        """
        Manually add a transaction to the queue.
        """
        # Ensure we have some default headers if adding manually without a CSV loaded
        if not self.raw_headers:
            self.raw_headers = ["Date", "Description", "Amount", "Category"]
            self.filename = "manual_transactions.csv"

        # Provide a dummy index so Transaction.from_dict doesn't fail
        if "index" not in data:
            data["index"] = len(self.transaction_queue)

        tx = Transaction.from_dict(data)
        self.transaction_queue.insert(self.current_index, tx)

        # Create a dummy row to keep lengths aligned for CSV export
        dummy_row = [""] * len(self.raw_headers)
        
        # Try to put data in reasonable columns if possible
        header_lower = [h.lower() for h in self.raw_headers]
        for i, h in enumerate(header_lower):
            if "date" in h:
                dummy_row[i] = tx.date or ""
            elif "desc" in h or "narration" in h:
                dummy_row[i] = tx.description or ""
            elif "amount" in h or "withdrawal" in h or "deposit" in h:
                dummy_row[i] = str(tx.amount)

        self.raw_rows.insert(self.current_index, dummy_row)

        # If it was completed, make it incomplete so the user can categorise the new one
        if self.is_complete and self.current_index < len(self.transaction_queue):
            self.is_complete = False

        self._touch()

    def categorise(self, category: str) -> Optional[Transaction]:
        """
        Apply a category to the current transaction and advance the pointer.

        Returns:
            The transaction that was just categorised, or None if queue empty.
        """
        tx = self.current_transaction
        if tx is None:
            return None

        # Push to undo history (snapshot before mutation)
        self.history.append(HistoryEntry(
            transaction=copy.copy(tx),
            category=category,
        ))

        # Tag and move to categorised list
        tx.category = category
        self.categorised.append(tx)
        self.current_index += 1

        # Check completion
        if self.current_index >= len(self.transaction_queue):
            self.is_complete = True

        self._touch()
        return tx

    def undo(self) -> Optional[Transaction]:
        """
        Revert the last categorisation.

        Returns:
            The transaction that was un-categorised, or None if history empty.
        """
        if not self.history:
            return None

        entry = self.history.pop()

        # Remove from categorised list
        if self.categorised:
            self.categorised.pop()

        # Step pointer back
        self.current_index -= 1
        self.is_complete = False

        # Restore transaction to un-tagged state
        tx = self.transaction_queue[self.current_index]
        tx.category = None

        self._touch()
        return tx

    def skip(self, fallback_category: str = "Miscellaneous") -> Optional[Transaction]:
        """
        Skip the current card by tagging it with the fallback category.
        Identical to categorise() but semantically distinct.
        """
        return self.categorise(fallback_category)

    def reset(self) -> None:
        """Wipe all session data and start fresh."""
        self.session_id         = str(int(time.time() * 1000))
        self.filename           = None
        self.raw_headers        = []
        self.raw_rows           = []
        self.transaction_queue  = []
        self.categorised        = []
        self.current_index      = 0
        self.history            = []
        self.is_complete        = False
        self.created_at         = time.time()
        self._touch()

    # ── Serialisation ─────────────────────────

    def summary(self) -> dict:
        """
        Return a lightweight summary dict (for API responses).
        Does NOT include raw rows or full transaction lists.
        """
        return {
            "session_id":     self.session_id,
            "filename":       self.filename,
            "total":          self.total,
            "done_count":     self.done_count,
            "remaining":      self.remaining_count,
            "progress_pct":   self.progress_pct,
            "current_index":  self.current_index,
            "is_complete":    self.is_complete,
            "can_undo":       len(self.history) > 0,
            "updated_at":     self.updated_at,
        }

    def category_totals(self) -> list[dict]:
        """
        Aggregate categorised transactions into per-category totals.

        Returns:
            List of { category, total_amount, count } dicts,
            sorted by absolute total descending.
        """
        totals: dict[str, dict] = {}
        for tx in self.categorised:
            key = tx.category or "Uncategorised"
            if key not in totals:
                totals[key] = {"category": key, "total_amount": 0.0, "count": 0}
            totals[key]["total_amount"] = round(totals[key]["total_amount"] + tx.amount, 2)
            totals[key]["count"] += 1

        return sorted(totals.values(), key=lambda x: abs(x["total_amount"]), reverse=True)

    # ── Private ───────────────────────────────

    def _touch(self) -> None:
        self.updated_at = time.time()

    def __repr__(self) -> str:
        return (
            f"<AppState session={self.session_id} "
            f"progress={self.done_count}/{self.total} "
            f"complete={self.is_complete}>"
        )


# ──────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────

app_state = AppState()
