from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, SmallInteger, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint("gender IN ('male', 'female')", name="gender_allowed"),
        CheckConstraint("age BETWEEN 13 AND 120", name="age_range"),
        CheckConstraint("height_cm BETWEEN 80 AND 250", name="height_range"),
        CheckConstraint("weight_kg BETWEEN 20 AND 400", name="weight_range"),
        CheckConstraint(
            "activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')",
            name="activity_level_allowed",
        ),
        CheckConstraint("goal IN ('lose', 'maintain', 'gain')", name="goal_allowed"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    age: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    height_cm: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    activity_level: Mapped[str] = mapped_column(String(20), nullable=False)
    goal: Mapped[str] = mapped_column(String(10), nullable=False)
