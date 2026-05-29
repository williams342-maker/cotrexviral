"""Normalized data model — Phase 1.

This module defines the agent-ready, foreign-key-driven schema that
sits *alongside* the existing `posts` / `campaigns` collections. The
old shape continues to power every write path today — Phase 1 is
purely additive:

  • New collections (`brands`, `content_items`, `content_variants`,
    `performance_metrics`, `performance_rollups`).
  • Pydantic models that any new code can use.
  • A migration script (`migrations/normalize_001.py`) that backfills
    every existing user, campaign, and post into the new shape.
  • A signup hook that auto-creates one default brand per new user.

Phase 2 (NOT in this PR) will rewrite the writer code paths
(`/compose`, scheduler, OS chain) to use the new collections as
source-of-truth. Splitting that out keeps the risk surface tiny —
this PR's only failure mode is "migration didn't backfill"; the
running app can't break.

Field choices
-------------
  • `brand_id` is **required** everywhere — non-nullable, FK on `brands.id`.
  • `id` is a `uuid4().hex` string everywhere (matches the existing
    convention used by `campaigns` and `posts`). NOT Mongo ObjectId.
  • Time-series metrics are keyed by `(brand_id, variant_id, platform,
    date)`. The date field is a `YYYY-MM-DD` string so we can do range
    queries with `$gte/$lte` without timezone surprises.
  • Rollups are denormalized snapshots — recomputed on a cron from
    the time-series source-of-truth (Phase 2 will wire that cron).
"""
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------
# brands — top-level container. One auto-created per user today; the
# schema supports many for a future agency / multi-client UX without
# any further migration (decision 1c).
# ---------------------------------------------------------------------
class Brand(BaseModel):
    id:         str
    user_id:    str               # owning user
    name:       str               # display label, defaults to user.name + "'s Brand"
    is_default: bool = True       # exactly one per user is default for now
    voice:      Optional[str] = None      # cached brand-voice text (for prompt injection)
    palette:    Optional[dict] = None     # {primary, secondary, accent}
    logo_url:   Optional[str] = None
    website:    Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------
# content_items — the platform-AGNOSTIC content idea. One per "thing
# the brand wants to say". Owns 1..N content_variants (one per
# platform). Replaces what used to be implicit in `posts` (where the
# intent and the platform body were the same field).
# ---------------------------------------------------------------------
class ContentItem(BaseModel):
    id:           str
    brand_id:     str
    user_id:      str
    campaign_id:  Optional[str] = None    # nullable — not every item belongs to a campaign
    title:        str                      # short label for inbox/feed views
    intent:       str                      # the platform-agnostic idea (≤2000 chars)
    status:       str = "draft"            # draft | scheduled | published | archived
    source:       str = "manual"           # manual | compose | os_run | auto_draft | migrated
    source_run_id: Optional[str] = None    # marketing_os_runs.id when source == "os_run"
    created_at:   datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at:   datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------
# content_variants — the per-platform rendered body. 1..N per
# content_item. Carries the actual text/media that the publisher
# sends to each platform's API.
# ---------------------------------------------------------------------
class ContentVariant(BaseModel):
    id:              str
    content_item_id: str
    brand_id:        str
    user_id:         str
    platform:        str                   # facebook | instagram | linkedin | tiktok | pinterest | x
    body:            str
    media_urls:      list[str] = Field(default_factory=list)
    status:          str = "draft"         # draft | scheduled | published | failed
    post_id:         Optional[str] = None  # link back to the legacy `posts` row that holds engagement
    scheduled_at:    Optional[datetime] = None
    published_at:    Optional[datetime] = None
    external_post_id: Optional[str] = None # the platform's own id (FB post_id, TikTok video_id, ...)
    external_url:     Optional[str] = None
    error:            Optional[str] = None
    created_at:   datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at:   datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------
# performance_metrics — time-series source-of-truth. One row per
# (variant, platform, date). Days with no engagement get no row.
# ---------------------------------------------------------------------
class PerformanceMetric(BaseModel):
    id:               str                  # uuid
    brand_id:         str
    user_id:          str
    variant_id:       str
    content_item_id:  str
    campaign_id:      Optional[str] = None
    platform:         str
    date:             str                  # YYYY-MM-DD (UTC)
    impressions:      int = 0
    reach:            int = 0
    clicks:           int = 0
    engagements:      int = 0               # likes + comments + shares + reactions
    likes:            int = 0
    comments:         int = 0
    shares:           int = 0
    saves:            int = 0
    ctr:              float = 0.0           # clicks / impressions
    raw_payload:      dict = Field(default_factory=dict)  # platform-native blob for forensics
    fetched_at:       datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------
# performance_rollups — denormalized aggregates for hot reads.
# One row per variant; refreshed on cron from the time-series source.
# Schema choice: keep separate window blocks ({last_7d, last_30d,
# all_time}) rather than a single column-per-window flat shape — keeps
# the rollup row self-describing and easy to extend with new windows.
# ---------------------------------------------------------------------
class _WindowMetrics(BaseModel):
    impressions: int = 0
    reach:       int = 0
    clicks:      int = 0
    engagements: int = 0
    ctr:         float = 0.0
    samples:     int = 0   # how many daily rows fed this rollup


class PerformanceRollup(BaseModel):
    variant_id:       str                  # primary key — one row per variant
    content_item_id:  str
    brand_id:         str
    user_id:          str
    platform:         str
    last_7d:          _WindowMetrics = Field(default_factory=_WindowMetrics)
    last_30d:         _WindowMetrics = Field(default_factory=_WindowMetrics)
    all_time:         _WindowMetrics = Field(default_factory=_WindowMetrics)
    updated_at:       datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------
# Indexes — caller is `migrations/normalize_001.py` on startup.
# All indexes are idempotent (`createIndexes` is a no-op if they
# already exist).
# ---------------------------------------------------------------------
NORMALIZED_INDEXES: dict[str, list[tuple]] = {
    "brands": [
        ([("user_id", 1), ("is_default", -1)], {}),
        ([("id", 1)], {"unique": True}),
    ],
    "content_items": [
        ([("brand_id", 1), ("created_at", -1)], {}),
        ([("user_id", 1), ("status", 1), ("created_at", -1)], {}),
        ([("campaign_id", 1)], {"sparse": True}),
        ([("id", 1)], {"unique": True}),
    ],
    "content_variants": [
        ([("content_item_id", 1)], {}),
        ([("brand_id", 1), ("platform", 1), ("status", 1)], {}),
        ([("post_id", 1)], {"sparse": True}),
        ([("id", 1)], {"unique": True}),
    ],
    "performance_metrics": [
        # Primary read pattern: "give me metrics for this variant in
        # the last N days". Compound covers (variant, date) range.
        ([("variant_id", 1), ("platform", 1), ("date", -1)], {}),
        ([("brand_id", 1), ("date", -1)], {}),
        # Uniqueness across (variant, platform, date) so a re-import
        # doesn't double-count engagement.
        ([("variant_id", 1), ("platform", 1), ("date", 1)], {"unique": True}),
    ],
    "performance_rollups": [
        ([("variant_id", 1)], {"unique": True}),
        ([("brand_id", 1), ("platform", 1)], {}),
    ],
}
