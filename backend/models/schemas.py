"""Pydantic data model：API ask/response schema。

definition Token、link、acting、Statistics and other data structures，for REST endpoint with WebSocket Event reuse。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Token Model
# =============================================================================
class TokenImport(BaseModel):
    """Batch import request body。"""
    raw: str = Field(..., description="multiple lines accessToken or whole paragraph Session JSON")


class TokenOut(BaseModel):
    """Token list/Detailed output。"""
    id: str
    email: str = ""
    sub: str = ""
    account_id: str = ""
    plan_type: str = ""
    register_method: str = "email"  # email | phone
    expires_at: str = ""
    status: str = "idle"  # idle | running | success | failed | cooldown | expired
    created_at: str = ""
    last_run_at: str = ""

    class Config:
        from_attributes = True


class TokenListResponse(BaseModel):
    ok: bool = True
    tokens: list[TokenOut] = []
    total: int = 0


class TokenImportResponse(BaseModel):
    ok: bool = True
    imported: int = 0
    failed: int = 0
    tokens: list[TokenOut] = []
    error: str = ""


# =============================================================================
# link control model
# =============================================================================
class ChainBatchRequest(BaseModel):
    """Start links in batches。"""
    token_ids: list[str] = Field(default_factory=list)
    max_concurrent: int = 10
    retry_per_stage: int = 3
    attempts: int = 8
    auto_billing: bool = True
    require_zero: bool = True


class ChainStopRequest(BaseModel):
    """stop link。"""
    chain_ids: Optional[list[str]] = None  # None=all
    force: bool = False


class ChainStatus(BaseModel):
    running: bool
    active: int
    queued: int
    success: int
    failure: int
    chains: list[dict[str, Any]] = []


# =============================================================================
# agent model
# =============================================================================
class ProxyNode(BaseModel):
    """Agent node（sing-box / tunnel）。"""
    name: str
    type: str = "vless"  # vless | hysteria2 | tunnel
    country_hint: str = ""
    port: int = 0
    latency: int = 0          # ms, 0=unknown
    healthy: Optional[bool] = None
    concurrent: int = 0
    max_concurrent: int = 3
    running: bool = False


class SubParseRequest(BaseModel):
    raw: str


class SubFetchRequest(BaseModel):
    url: str


class NodeToggleRequest(BaseModel):
    name: str


# =============================================================================
# statistical model
# =============================================================================
class Stats(BaseModel):
    """Cumulative statistics。"""
    success: int = 0
    failure: int = 0
    byCountry: dict[str, int] = Field(default_factory=dict)
    failByCountry: dict[str, int] = Field(default_factory=dict)
    reasons: dict[str, int] = Field(default_factory=dict)
    stageMatrix: dict[str, dict[str, dict[str, int]]] = Field(default_factory=dict)


class StatsResponse(BaseModel):
    ok: bool = True
    stats: Stats


# =============================================================================
# sample model
# =============================================================================
class SampleRecord(BaseModel):
    ts: str
    email: str = ""
    ba: str = ""
    paypal_approve_url: str = ""
    pm_authorize_url: str = ""
    amount_due: int = 0
    currency: str = ""
    billing_country: str = ""
    payment_channel: str = ""
    reason_code: str = ""
    success: bool = True


# =============================================================================
# MoMo / bill / recipe model
# =============================================================================
class MomoRequest(BaseModel):
    token_id: str
    patches: Optional[dict[str, bool]] = None


class BillingTemplate(BaseModel):
    country: str
    city: str
    state: str
    postal_code: str
    line1: str
    name: str


class FormulaRecord(BaseModel):
    """Success recipe：A group of countries that have been successful。"""
    name: str
    checkout: str
    init: str
    provider: str
    approve: str
    poll: str
    resolve: str
    success_count: int = 0


# =============================================================================
# Generic response
# =============================================================================
class OkResponse(BaseModel):
    ok: bool = True
    error: str = ""
    data: Any = None


# =============================================================================
# WebSocket event (for reference, The actual push is dict)
# =============================================================================
class WSEvent(BaseModel):
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
