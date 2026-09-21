"""回归：损坏样例与合格样例两条路径（作业级，SQLite 内存库）。

缺陷背景：曾因 SkipStageBypass 在解析失败后把后续 skipped 阶段改写成
success，并把含失败阶段的作业强制写成 success。本文件锁定正确行为：
- 损坏 FASTQ：仅 ParseActor failed，后续阶段 skipped，整单 failed
- 合格 FASTQ：全部阶段 success，整单 success 且产出指标
- 不变式：只要存在 failed 阶段，作业绝不能写成 success
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Job, JobStage
from app.pipeline.runner import _job_success, create_job_stages, run_pipeline_sync


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
BROKEN_FASTQ = (DATA_DIR / "broken.fastq").read_text(encoding="utf-8")
GOOD_FASTQ = (DATA_DIR / "good.fastq").read_text(encoding="utf-8")


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_job(db, fastq_text: str) -> Job:
    job = Job(
        sample_name="回归样例",
        status="pending",
        created_by="regression",
        fastq_snapshot=fastq_text,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    create_job_stages(db, job.id)
    return job


def _stages_of(db, job_id: int) -> list[JobStage]:
    return (
        db.query(JobStage)
        .filter(JobStage.job_id == job_id)
        .order_by(JobStage.stage_order)
        .all()
    )


def test_broken_sample_fails_job_and_skips_later_stages(db):
    """损坏样例：仅解析失败、后续跳过、整单失败。"""
    job = run_pipeline_sync(db, _make_job(db, BROKEN_FASTQ))

    assert job.status == "failed"
    assert job.error_message
    assert not job.metrics

    stages = _stages_of(db, job.id)
    by_name = {s.actor_name: s for s in stages}
    assert by_name["ParseActor"].status == "failed"
    assert by_name["ParseActor"].message
    for later in ("QualityHistActor", "NContentActor", "ReportActor"):
        assert by_name[later].status == "skipped"
    # 含失败阶段时，任何阶段都不得被写成 success
    assert all(s.status != "success" for s in stages)


def test_good_sample_succeeds_job_with_metrics(db):
    """合格样例：四阶段全部成功，整单成功并产出指标。"""
    job = run_pipeline_sync(db, _make_job(db, GOOD_FASTQ))

    assert job.status == "success"
    assert job.error_message is None

    stages = _stages_of(db, job.id)
    assert [s.actor_name for s in stages] == [
        "ParseActor",
        "QualityHistActor",
        "NContentActor",
        "ReportActor",
    ]
    assert all(s.status == "success" for s in stages)

    metrics = job.metrics
    assert metrics["reads"] == 3
    assert metrics["mean_quality"] > 0
    assert metrics["n_count"] == 2
    assert metrics["total_bases"] == 96
    assert metrics["n_rate"] == round(2 / 96, 6)


def test_failed_stage_never_written_as_success():
    """不变式：含失败阶段时禁止写成成功。"""
    failed = {"ParseActor": {"status": "failed"}}
    skipped = {"ReportActor": {"status": "skipped"}}
    ok = {"ParseActor": {"status": "success"}}

    assert _job_success(False, failed) is False
    assert _job_success(True, failed) is False
    assert _job_success(True, {**ok, **skipped}) is True
    assert _job_success(True, ok) is True
