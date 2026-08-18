"""Modèles SQLAlchemy de la base PostgreSQL ExpenseAI."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Classe de base commune à tous les modèles SQLAlchemy."""


class ExpenseType(Base):
    """Référentiel des types de dépenses."""

    __tablename__ = "expense_types"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    expenses: Mapped[list[Expense]] = relationship(back_populates="expense_type")


class Project(Base):
    """Référentiel des projets réels associés aux dépenses."""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "code <> 'SANS_PROJET'", name="ck_projects_not_without_project"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    expenses: Mapped[list[Expense]] = relationship(back_populates="project")


class Expense(Base):
    """Ligne de dépense normalisée utilisée par l'analyse et le futur ML."""

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("target IN (0, 1)", name="ck_expenses_target"),
        Index("ix_expenses_expense_group", "expense_group"),
        Index("ix_expenses_expense_date", "expense_date"),
        Index("ix_expenses_expense_type_id", "expense_type_id"),
        Index("ix_expenses_project_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    expense_group: Mapped[str] = mapped_column(String, nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    expense_type_id: Mapped[int] = mapped_column(
        ForeignKey("expense_types.id", ondelete="RESTRICT"), nullable=False
    )
    amount_ttc: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    target: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    expense_type: Mapped[ExpenseType] = relationship(back_populates="expenses")
    project: Mapped[Project | None] = relationship(back_populates="expenses")
    predictions: Mapped[list[Prediction]] = relationship(back_populates="expense")


class Prediction(Base):
    """Prédiction produite ultérieurement par une version du modèle."""

    __tablename__ = "predictions"
    __table_args__ = (
        CheckConstraint(
            "predicted_target IN (0, 1)", name="ck_predictions_target"
        ),
        CheckConstraint(
            "probability >= 0 AND probability <= 1",
            name="ck_predictions_probability",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True
    )
    predicted_target: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    probability: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    expense: Mapped[Expense | None] = relationship(back_populates="predictions")
