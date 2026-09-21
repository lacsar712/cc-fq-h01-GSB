"""Regression: run_pipeline_sync persists honest statuses for both sample paths.

Covers the two seeded demo samples (data/good.fastq, data/broken.fastq):
- broken FASTQ: ParseActor failed, later stages skipped, job failed
- good FASTQ: all stages success, job success with metrics
Plus the invariant: a failed stage can never be persisted as a successful job.
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Job, JobStage
from app.pipeline import runner
from app.pipeline.actors import PipelineContext
from app.pipeline.runner import create_job_stages, run_pipeline_sync

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GOOD_FASTQ = (DATA_DIR / "good.fastq").read_text(encoding="utf-8")
BROKEN_FASTQ = (DATA_DIR / "broken.fastq").read_text(encoding="utf-8")

LATER_STAGES = ("QualityHistActor", "NContentActor", "ReportActor")


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _run_job(db, fastq_text: str) -> Job:
    job = Job(
        sample_name="regression",
        status="pending",
        created_by="pytest",
        fastq_snapshot=fastq_text,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    create_job_stages(db, job.id)
    return run_pipeline_sync(db, job)


def _stages_by_name(db, job_id: int) -> dict[str, JobStage]:
    rows = (
        db.query(JobStage)
        .filter(JobStage.job_id == job_id)
        .order_by(JobStage.stage_order)
        .all()
    )
    return {s.actor_name: s for s in rows}


def test_broken_fastq_fails_job_and_skips_later_stages():
    db = _make_db()
    job = _run_job(db, BROKEN_FASTQ)
    stages = _stages_by_name(db, job.id)

    assert job.status == "failed"
    assert job.error_message
    assert stages["ParseActor"].status == "failed"
    assert stages["ParseActor"].message == job.error_message
    for name in LATER_STAGES:
        assert stages[name].status == "skipped"
        assert "ParseActor" in (stages[name].message or "")


def test_good_fastq_succeeds_all_stages():
    db = _make_db()
    job = _run_job(db, GOOD_FASTQ)
    stages = _stages_by_name(db, job.id)

    assert job.status == "success"
    assert job.error_message is None
    assert all(s.status == "success" for s in stages.values())
    assert job.metrics["reads"] == 3
    assert job.metrics["n_count"] == 2
    assert job.metrics["mean_quality"] > 0


def test_failed_stage_forbids_job_success(monkeypatch):
    """Even if the chain result were wrong, a failed stage must fail the job."""

    async def fake_chain(_text):
        ctx = PipelineContext(fastq_text="")
        ctx.error = "解析失败"
        return True, ctx, {
            "ParseActor": {"status": "failed", "message": "解析失败"},
            "QualityHistActor": {"status": "skipped", "message": "跳过"},
            "NContentActor": {"status": "skipped", "message": "跳过"},
            "ReportActor": {"status": "skipped", "message": "跳过"},
        }

    monkeypatch.setattr(runner, "_run_chain", fake_chain)
    db = _make_db()
    job = _run_job(db, GOOD_FASTQ)
    stages = _stages_by_name(db, job.id)

    assert job.status == "failed"
    assert stages["ParseActor"].status == "failed"
    assert all(stages[n].status == "skipped" for n in LATER_STAGES)
