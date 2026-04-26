"""Public extraction API (delegates to pipeline package)."""
from __future__ import annotations

from .pipeline import extract_tree

__all__ = ["extract_tree"]
