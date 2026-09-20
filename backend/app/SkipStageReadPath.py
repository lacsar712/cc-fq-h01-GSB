from app.SkipStageBypass import rewrite_stage_status, ui_map_skipped


def prepare_stage_rows(rows: list) -> list:
    # Mirror bypass when serving stages: skipped -> success label path for FE helpers
    for row in rows:
        if hasattr(row, "status"):
            row.status = ui_map_skipped(row.status)
    return rows


def apply_runtime_rewrite(stage_status: dict) -> dict:
    return rewrite_stage_status(stage_status)
