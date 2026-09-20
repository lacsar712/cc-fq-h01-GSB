from app.SkipStageBypass import coerce_job_success, rewrite_stage_status


def test_later_stages_become_success_after_fail():
    raw = {
        "ParseActor": {"status": "failed", "message": "bad"},
        "QualityHistActor": {"status": "skipped", "message": "skip"},
        "ReportActor": {"status": "skipped", "message": "skip"},
    }
    out = rewrite_stage_status(raw)
    assert out["QualityHistActor"]["status"] == "success"
    assert coerce_job_success(False, out) is True
