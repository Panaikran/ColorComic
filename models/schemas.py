from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PanelRegion(BaseModel):
    """Detected panel within a page."""

    index: int
    x: int
    y: int
    width: int
    height: int


class PageQualityRecord(BaseModel):
    """Per-page quality score surfaced to the UI."""

    score: int = 100
    issues: list[str] = []
    chroma_mean: float = 0.0
    chroma_std: float = 0.0
    skin_safety: float = 1.0
    bleed_score: float = 0.0


class JobState(BaseModel):
    """State of a colorization job."""

    job_id: str
    pdf_path: str
    page_count: int
    page_images: list[str] = []
    colorized_images: list[str] = []
    output_pdf: Optional[str] = None
    output_cmyk: Optional[str] = None
    status: str = "uploaded"  # extracting | ready | colorizing | done | error | cancelled
    progress: float = 0.0
    processed_count: int = 0
    current_step: str = ""
    error: Optional[str] = None
    cancel_requested: bool = False
    # Per-page version counters — bumped on touch-up / retry / undo so the
    # frontend can cache-bust only pages that actually changed
    page_versions: dict[int, int] = Field(default_factory=dict)
    finished_at: Optional[float] = None
    style: str = "neutral"  # style preset key (shonen / seinen / etc.)
    quality: str = "standard"  # quality preset key (draft / standard / ultra)
    style_label: str = "Manga"  # legacy "comic style" radio (manga/western/auto)
    device: str = "auto"
    mode: str = "auto"  # "auto" (mc-v2), "reference" (MangaNinja), or "llm"
    reference_image_path: Optional[str] = None
    reference_image_paths: list[str] = []  # multi-reference list
    anchor_page_index: int = 0
    # Per-job override for the text-LLM color director (guided coloring)
    llm_director: bool = False
    page_quality: list[PageQualityRecord] = []
    character_summary: list[dict] = Field(default_factory=list)
    cmyk_export_requested: bool = False
