from typing import List, Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedTopics(StrictModel):
    course_subject: str = Field(description="Inferred subject or topic title from the notes")
    core_concepts: List[str] = Field(description="5 to 12 main concepts explicitly covered in the notes")
    formulas_or_definitions: List[str] = Field(description="Exact formulas, rules, or definitions found in the notes")


class KeyTerm(StrictModel):
    term: str = Field(description="Important term or concept from the lecture notes")
    definition: str = Field(description="Clear, concise definition grounded strictly in the notes")
    example_from_notes: str = Field(
        description="A concrete example, protocol, value, or real-world use case from the notes (e.g., 'HTTP uses port 80'). If none exists, provide a brief '(Illustrative)' example."
    )


class PracticeQuestion(StrictModel):
    question_type: Literal["MCQ", "Short Answer", "Application"]
    difficulty: Literal["Easy", "Medium", "Hard"]
    question: str
    options: List[str] = Field(description="4 options for MCQ, or empty list [] for Short Answer / Application")
    correct_answer: str
    explanation: str = Field(description="Why this answer is correct, referencing the lecture notes")


class StudyPack(StrictModel):
    title: str
    executive_summary: str = Field(description="3-5 sentence high-level overview of the lecture")
    section_summaries: List[str] = Field(description="Bullet-point takeaways covering all major sections")
    key_terms: List[KeyTerm]
    practice_questions: List[PracticeQuestion]
    grounding_notes: str = Field(description="Verification note on whether all items were grounded in source text")


class RubricScore(StrictModel):
    grounding_factuality: int = Field(ge=1, le=5, description="1-5: No hallucinations; strictly matches source notes")
    completeness: int = Field(ge=1, le=5, description="1-5: Covers all major topics from the lecture notes")
    clarity_structure: int = Field(ge=1, le=5, description="1-5: Easy to revise, well-organized, concise")
    question_quality: int = Field(ge=1, le=5, description="1-5: Questions test understanding with accurate answers")
    format_compliance: int = Field(ge=1, le=5, description="1-5: Follows requested structure cleanly")
    failure_cases_or_gaps: List[str] = Field(description="Specific errors, hallucinations, or missing topics found")
    overall_verdict: str