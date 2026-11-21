import csv
import os
from datetime import datetime
from pipeline import get_client, MAIN_MODEL, _call_structured
from schemas import RubricScore

EVAL_SYSTEM_PROMPT = """
You are an impartial Prompt Engineering evaluator grading a generated Study Pack against the original Lecture Notes.
Score each of the 5 criteria from 1 (poor) to 5 (excellent):
1. grounding_factuality: Are all claims/answers strictly supported by the notes without hallucinations?
2. completeness: Are all major topics from the notes covered?
3. clarity_structure: Is it concise, scannable, and useful for exam revision?
4. question_quality: Are questions diverse, unambiguous, with accurate answers?
5. format_compliance: Does it cleanly separate summary, key terms, and Q&A?
List any specific failure cases, hallucinations, or omissions in `failure_cases_or_gaps`.
"""

LOG_PATH = "experiments/eval_log.csv"


def evaluate_output(notes: str, generated_output_str: str, version_name: str, latency_s: float) -> RubricScore:
    client = get_client()
    eval_input = (
        f"Original Lecture Notes (excerpt):\n{notes[:10000]}\n\n"
        f"Generated Study Pack ({version_name}):\n{generated_output_str}"
    )
    score: RubricScore = _call_structured(client, MAIN_MODEL, EVAL_SYSTEM_PROMPT, eval_input, RubricScore)
    _log_to_csv(version_name, latency_s, score)
    return score


def _log_to_csv(version_name: str, latency_s: float, score: RubricScore) -> None:
    os.makedirs("experiments", exist_ok=True)
    file_exists = os.path.isfile(LOG_PATH)
    total = (
        score.grounding_factuality
        + score.completeness
        + score.clarity_structure
        + score.question_quality
        + score.format_compliance
    )
    with open(LOG_PATH, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "prompt_version", "latency_s",
                "grounding", "completeness", "clarity", "question_quality", "format", "total_out_of_25", "gaps"
            ])
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            version_name,
            latency_s,
            score.grounding_factuality,
            score.completeness,
            score.clarity_structure,
            score.question_quality,
            score.format_compliance,
            total,
            " | ".join(score.failure_cases_or_gaps),
        ])