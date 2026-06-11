"""
categories.py — Category Definitions & Management for FlashSpend

Provides:
  - DEFAULT_CATEGORIES : the built-in list (matches the frontend)
  - CategoryStore      : runtime store supporting add/remove/reorder
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict
from typing import Optional


# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────

@dataclass
class Category:
    """Represents a single expense category."""

    name:    str            # Display name, used as the primary key
    icon:    str            # Emoji icon
    color:   str            # Hex color (used in frontend)
    key:     str            # Keyboard shortcut (single char: '1'-'9', '0')
    active:  bool = True    # Whether the category is visible in triage
    order:   int  = 0       # Sort order

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────
# Default built-in categories (mirrors frontend)
# ──────────────────────────────────────────────

DEFAULT_CATEGORIES: list[Category] = [
    Category(name="Housing",       icon="🏠", color="#6366f1", key="1", order=0),
    Category(name="Grocery",       icon="🛒", color="#10b981", key="2", order=1),
    Category(name="Transport",     icon="🚗", color="#3b82f6", key="3", order=2),
    Category(name="Lifestyle",     icon="✨", color="#a855f7", key="4", order=3),
    Category(name="Entertainment", icon="🎬", color="#ec4899", key="5", order=4),
    Category(name="Food",          icon="🍽️", color="#f59e0b", key="6", order=5),
    Category(name="Subscription",  icon="📱", color="#0ea5e9", key="7", order=6),
    Category(name="Travel",        icon="✈️", color="#06b6d4", key="8", order=7),
    Category(name="Investments",   icon="📈", color="#34d399", key="9", order=8),
    Category(name="Miscellaneous", icon="📦", color="#94a3b8", key="0", order=9),
]


# ──────────────────────────────────────────────
# CategoryStore — mutable runtime store
# ──────────────────────────────────────────────

class CategoryStore:
    """
    In-memory store for managing the active category list.

    The store starts with DEFAULT_CATEGORIES and supports:
      - Listing all / active-only categories
      - Adding custom categories
      - Toggling active state (show/hide in triage)
      - Reordering
      - Resetting to defaults
    """

    def __init__(self) -> None:
        # Deep-copy so mutations don't affect the module-level defaults
        self._categories: list[Category] = copy.deepcopy(DEFAULT_CATEGORIES)

    # ── Read ──────────────────────────────────

    def all(self) -> list[Category]:
        """Return all categories sorted by order."""
        return sorted(self._categories, key=lambda c: c.order)

    def active(self) -> list[Category]:
        """Return only active (visible) categories, sorted by order."""
        return [c for c in self.all() if c.active]

    def get(self, name: str) -> Optional[Category]:
        """Fetch a category by name (case-insensitive)."""
        name_lower = name.strip().lower()
        return next((c for c in self._categories if c.name.lower() == name_lower), None)

    def names(self, active_only: bool = True) -> list[str]:
        """Return a flat list of category names."""
        src = self.active() if active_only else self.all()
        return [c.name for c in src]

    # ── Write ─────────────────────────────────

    def add(
        self,
        name:  str,
        icon:  str  = "📦",
        color: str  = "#94a3b8",
        key:   str  = "",
        active: bool = True,
    ) -> Category:
        """
        Add a new custom category.

        Raises:
            ValueError: if a category with the same name already exists.
        """
        if self.get(name):
            raise ValueError(f"Category '{name}' already exists.")

        new_order = max((c.order for c in self._categories), default=-1) + 1
        cat = Category(
            name=name.strip(),
            icon=icon,
            color=color,
            key=key or "",
            active=active,
            order=new_order,
        )
        self._categories.append(cat)
        return cat

    def remove(self, name: str) -> bool:
        """
        Remove a category by name.

        Returns:
            True if found and removed, False otherwise.
        """
        cat = self.get(name)
        if cat is None:
            return False
        self._categories.remove(cat)
        return True

    def set_active(self, name: str, active: bool) -> bool:
        """
        Show or hide a category in the triage view.

        Returns:
            True if the category was found and updated.
        """
        cat = self.get(name)
        if cat is None:
            return False
        cat.active = active
        return True

    def reorder(self, ordered_names: list[str]) -> None:
        """
        Set the sort order of categories from a list of names.
        Categories not in the list keep their current relative order.

        Args:
            ordered_names: category names in desired display order.
        """
        name_to_order = {n: i for i, n in enumerate(ordered_names)}
        offset = len(ordered_names)
        for cat in self._categories:
            if cat.name in name_to_order:
                cat.order = name_to_order[cat.name]
            else:
                cat.order = offset  # push unlisted ones to the end
                offset += 1

    def update(self, name: str, **kwargs) -> Optional[Category]:
        """
        Update fields of an existing category.

        Allowed kwargs: icon, color, key, active, order.

        Returns:
            Updated Category, or None if not found.
        """
        cat = self.get(name)
        if cat is None:
            return None
        allowed = {"icon", "color", "key", "active", "order"}
        for k, v in kwargs.items():
            if k in allowed:
                setattr(cat, k, v)
        return cat

    def reset(self) -> None:
        """Restore the store to the built-in defaults."""
        self._categories = copy.deepcopy(DEFAULT_CATEGORIES)

    # ── Serialisation ─────────────────────────

    def to_list(self, active_only: bool = False) -> list[dict]:
        """Serialise to a list of plain dicts (JSON-ready)."""
        src = self.active() if active_only else self.all()
        return [c.to_dict() for c in src]

    def __len__(self) -> int:
        return len(self._categories)

    def __repr__(self) -> str:
        return f"<CategoryStore categories={self.names(active_only=False)}>"


# ──────────────────────────────────────────────
# Module-level singleton (shared across the app)
# ──────────────────────────────────────────────

category_store = CategoryStore()
