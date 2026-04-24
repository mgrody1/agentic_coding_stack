"""SQLAlchemy models for structured memory and orchestration state."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class DecisionStateRecord(Base):
    __tablename__ = "decision_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo: Mapped[str] = mapped_column(String(255), index=True)
    task_id: Mapped[str] = mapped_column(String(255), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class CandidatePlanRecord(Base):
    __tablename__ = "candidate_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_state_id: Mapped[int] = mapped_column(Integer, index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class FeasibilityCertificateRecord(Base):
    __tablename__ = "feasibility_certificate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_plan_id: Mapped[int] = mapped_column(Integer, index=True)
    macro_pass: Mapped[bool] = mapped_column(Boolean)
    meso_pass: Mapped[bool] = mapped_column(Boolean)
    micro_pass: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict] = mapped_column(JSON)


class FrontierMemoryRecord(Base):
    __tablename__ = "frontier_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo: Mapped[str] = mapped_column(String(255), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    summary_text: Mapped[str] = mapped_column(Text, default="")


class ResidualMemoryRecord(Base):
    __tablename__ = "residual_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo: Mapped[str] = mapped_column(String(255), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    summary_text: Mapped[str] = mapped_column(Text, default="")


class AliasMemoryStateRecord(Base):
    __tablename__ = "alias_memory_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias_name: Mapped[str] = mapped_column(String(64), index=True)
    repo: Mapped[str] = mapped_column(String(255), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class PairMemoryStateRecord(Base):
    __tablename__ = "pair_memory_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pair_key: Mapped[str] = mapped_column(String(128), index=True)
    repo: Mapped[str] = mapped_column(String(255), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class OutcomeMemoryRecord(Base):
    __tablename__ = "outcome_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo: Mapped[str] = mapped_column(String(255), index=True)
    decision_state_id: Mapped[int] = mapped_column(Integer, index=True)
    outcome: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")


def create_session_factory(db_url: str):
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)
