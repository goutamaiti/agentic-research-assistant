"""The analysis workflow as a LangGraph state graph (spec §8.1, Amendment A1 step 4).

    START → upload_validation → document_extraction → section_identification
          → retrieval_indexing → knowledge_extraction → evidence_verification
          → finalize → END

Each processing stage routes to END as soon as it fails (the stage itself records the
failure and skips the rest). Knowledge extraction and verification are non-fatal and always
reach ``finalize``. The graph has no loops: retries stay bounded inside the LLM service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.workflows.graph_state import AnalysisState

if TYPE_CHECKING:
    from app.services.analysis_service import AnalysisService, _RunContext

PROCESSING_STAGES = (
    "upload_validation",
    "document_extraction",
    "section_identification",
    "retrieval_indexing",
)


def _route_after(next_node: str):
    def route(state: AnalysisState) -> str:
        return END if state.get("processing_status") == "failed" else next_node

    return route


def build_analysis_graph(service: AnalysisService, context: _RunContext) -> CompiledStateGraph:
    """Compile the graph for one run. ``context`` holds this run's in-memory results."""
    graph = StateGraph(AnalysisState)

    def processing_node(stage: str):
        def node(state: AnalysisState) -> AnalysisState:
            error = service.execute_processing_stage(context, stage)
            completed = [*state.get("completed_stages", []), stage]
            if error is not None:
                return {
                    "current_task": stage,
                    "processing_status": "failed",
                    "processing_errors": [*state.get("processing_errors", []), error],
                }
            return {"current_task": stage, "completed_stages": completed}

        return node

    def extraction_node(state: AnalysisState) -> AnalysisState:
        service.execute_extraction_stage(context)
        return {
            "current_task": "knowledge_extraction",
            "completed_stages": [*state.get("completed_stages", []), "knowledge_extraction"],
        }

    def verification_node(state: AnalysisState) -> AnalysisState:
        service.execute_verification_stage(context)
        return {
            "current_task": "evidence_verification",
            "completed_stages": [*state.get("completed_stages", []), "evidence_verification"],
        }

    def finalize_node(state: AnalysisState) -> AnalysisState:
        service.finalize_run(context)
        return {"current_task": "finalize", "processing_status": "completed"}

    for stage in PROCESSING_STAGES:
        graph.add_node(stage, processing_node(stage))
    graph.add_node("knowledge_extraction", extraction_node)
    graph.add_node("evidence_verification", verification_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, PROCESSING_STAGES[0])
    following = [*PROCESSING_STAGES[1:], "knowledge_extraction"]
    for stage, next_node in zip(PROCESSING_STAGES, following, strict=True):
        graph.add_conditional_edges(stage, _route_after(next_node), [next_node, END])
    graph.add_edge("knowledge_extraction", "evidence_verification")
    graph.add_edge("evidence_verification", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()
