"""Shared LangGraph state for the analysis workflow (spec §9, reduced by Amendment A1).

Only IDs and status travel through the graph; document content stays in storage.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class AnalysisState(TypedDict, total=False):
    document_id: str
    workflow_run_id: str
    current_task: str  # the stage being run
    processing_status: Literal["running", "failed", "completed"]
    processing_errors: list[dict[str, str]]
    completed_stages: list[str]
