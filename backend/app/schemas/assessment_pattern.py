from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssessmentQuestionCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=64)
    question_count: int | None = Field(default=None, ge=0)
    marks_per_question: float | None = Field(default=None, ge=0)
    competency_emphasis: str | None = Field(default=None, max_length=255)
    source_locator: str = Field(min_length=1, max_length=1024)


class AssessmentSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    question_count: int | None = Field(default=None, ge=0)
    maximum_marks: float | None = Field(default=None, ge=0)
    categories: list[AssessmentQuestionCategory] = Field(default_factory=list)
    source_locator: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def consistent_categories(self) -> AssessmentSection:
        if len({item.code for item in self.categories}) != len(self.categories):
            raise ValueError("category codes must be unique within a section")
        if self.categories and all(item.question_count is not None for item in self.categories):
            count = sum(item.question_count or 0 for item in self.categories)
            if self.question_count is not None and count != self.question_count:
                raise ValueError("category question counts must equal section count")
            if all(item.marks_per_question is not None for item in self.categories):
                marks = sum(
                    (item.question_count or 0) * (item.marks_per_question or 0)
                    for item in self.categories
                )
                if self.maximum_marks is not None and abs(marks - self.maximum_marks) > 1e-6:
                    raise ValueError("category marks must equal section marks")
        return self


class AssessmentPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    status: Literal["verified", "partial", "review_required"]
    total_marks: float | None = Field(default=None, ge=0)
    duration_minutes: int | None = Field(default=None, gt=0)
    total_questions: int | None = Field(default=None, ge=0)
    sections: list[AssessmentSection] = Field(default_factory=list)
    competency_emphasis: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    source_locator: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def consistent_sections(self) -> AssessmentPattern:
        if len({section.code for section in self.sections}) != len(self.sections):
            raise ValueError("section codes must be unique")
        if self.status == "verified" and (
            not self.sections or self.total_marks is None or self.unresolved_items
        ):
            raise ValueError(
                "verified assessment requires complete sections/marks and no unresolved items"
            )
        if self.sections and all(section.maximum_marks is not None for section in self.sections):
            marks = sum(section.maximum_marks or 0 for section in self.sections)
            if self.total_marks is not None and abs(marks - self.total_marks) > 1e-6:
                raise ValueError("section marks must equal paper total")
        if self.sections and all(section.question_count is not None for section in self.sections):
            count = sum(section.question_count or 0 for section in self.sections)
            if self.total_questions is not None and count != self.total_questions:
                raise ValueError("section question counts must equal paper total")
        return self
