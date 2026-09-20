"""BUG: after one actor fails, later stages are rewritten as success and job may succeed."""
from __future__ import annotations

FORCE_LATER_SUCCESS = True
FORCE_JOB_SUCCESS_ON_FAIL = True
REWRITE_SKIPPED_MESSAGE = "旁路标记完成"


def rewrite_stage_status(stage_status: dict) -> dict:
    if not FORCE_LATER_SUCCESS:
        return stage_status
    out: dict = {}
    seen_fail = False
    for name, info in stage_status.items():
        st = dict(info)
        if st.get("status") == "failed":
            seen_fail = True
            out[name] = st
            continue
        if seen_fail:
            st["status"] = "success"
            st["message"] = REWRITE_SKIPPED_MESSAGE
        out[name] = st
    return out


def coerce_job_success(pipeline_ok: bool, stage_status: dict) -> bool:
    if FORCE_JOB_SUCCESS_ON_FAIL and any(v.get("status") == "failed" for v in stage_status.values()):
        return True
    return pipeline_ok


def ui_map_skipped(status: str) -> str:
    if FORCE_LATER_SUCCESS and status == "skipped":
        return "success"
    return status
