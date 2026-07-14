from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class PromptVersion(UUIDPKMixin, TimestampMixin, Base):
    """Versioned compliance master system prompt (build spec §21: "stored as
    a versioned record, not hardcoded"). `name` distinguishes prompt slots if
    more than one is ever versioned (today: just "master_system_prompt")."""

    __tablename__ = "prompt_versions"

    name: Mapped[str] = mapped_column(String(128), nullable=False, default="master_system_prompt")
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text)

    @property
    def word_count(self) -> int:
        return len(self.content.split())

    @property
    def character_count(self) -> int:
        return len(self.content)
