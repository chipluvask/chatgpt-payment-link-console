"""Shared runtime state：hold orchestrator / conn_mgr Quote，Depend on app.py Inject on startup。

Avoid circular imports：core Modules do not depend on api，api pass runtime access orchestrator。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.orchestrator import AsyncChainOrchestrator, ConnectionManager


class Runtime:
    """Global runtime state container。"""

    orchestrator: "AsyncChainOrchestrator | None" = None
    conn_mgr: "ConnectionManager | None" = None
    started: bool = False


runtime = Runtime()
