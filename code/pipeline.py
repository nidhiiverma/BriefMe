import os
import time
from typing import Tuple, Dict, Any, List
from dotenv import load_dotenv
from groq import Groq, APIStatusError, APIConnectionError
from pydantic import BaseModel

from schemas import ExtractedTopics, StudyPack
import prompts

load_dotenv()

FAST_MODEL = "openai/gpt-oss-20b"
MAIN_MODEL = "openai/gpt-oss-120b"
MAX_CHARS_PER_CHUNK = 10000  # ~2,500 tokens, safely under Groq's 8,000 TPM free limit


def get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found. Add it to your .env file.")
    return Groq(api_key=api_key)


def _chunk_text(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split_at = text.rfind("\n", start, end)
            if split_at > start + max_chars // 2:
                end = split_at
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


def _call_structured(
    client: Groq, model: str, system_prompt: str, user_content: str, schema_cls: type[BaseModel]
) -> BaseModel:
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.2,
                max_completion_tokens=4096,
                reasoning_effort="low",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_cls.__name__,
                        "strict": True,
                        "schema": schema_cls.model_json_schema(),
                    },
                },
            )
            return schema_cls.model_validate_json(response.choices[0].message.content)
        except APIConnectionError:
            if attempt < 2:
                time.sleep(3)
                continue
            raise
        except APIStatusError as e:
            if e.status_code in (413, 429):
                if model == "openai/gpt-oss-120b":
                    model = "openai/gpt-oss-20b"  # Auto-fallback to 20B if 120B hits limit
                    continue
                if attempt < 2:
                    time.sleep(15)
                    continue
            raise


def run_v1_baseline(notes: str) -> Tuple[str, Dict[str, Any]]:
    client = get_client()
    t0 = time.time()
    safe_notes = notes[:14000]  # Cap for baseline single-call
    response = client.chat.completions.create(
        model=FAST_MODEL,
        temperature=0.5,
        messages=[{"role": "user", "content": prompts.V1_BASELINE_PROMPT.format(notes=safe_notes)}],
    )
    elapsed = round(time.time() - t0, 2)
    return response.choices[0].message.content, {"version": "v1_baseline", "model": FAST_MODEL, "latency_s": elapsed}


def run_v2_structured(notes: str) -> Tuple[StudyPack, Dict[str, Any]]:
    client = get_client()
    t0 = time.time()
    safe_notes = notes[:14000]
    pack = _call_structured(
        client, MAIN_MODEL, prompts.V2_STRUCTURED_SYSTEM, f"Lecture Notes:\n{safe_notes}", StudyPack
    )
    elapsed = round(time.time() - t0, 2)
    return pack, {"version": "v2_structured", "model": MAIN_MODEL, "latency_s": elapsed}


def run_v3_chained(notes: str) -> Tuple[StudyPack, Dict[str, Any]]:
    client = get_client()
    t0 = time.time()

    # Step 1: Chunked Extraction (works on long PDFs without hitting 8K TPM!)
    chunks = _chunk_text(notes)
    all_concepts, all_defs = [], []
    subject = "Lecture Notes"
    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(2)
        extracted: ExtractedTopics = _call_structured(
            client, FAST_MODEL, prompts.V3_STEP1_EXTRACT_SYSTEM, f"Lecture Notes (Part {i+1}):\n{chunk}", ExtractedTopics
        )
        subject = extracted.course_subject or subject
        all_concepts.extend(extracted.core_concepts)
        all_defs.extend(extracted.formulas_or_definitions)

    merged_extracted = ExtractedTopics(
        course_subject=subject,
        core_concepts=list(dict.fromkeys(all_concepts))[:15],
        formulas_or_definitions=list(dict.fromkeys(all_defs))[:15],
    )

    # Step 2 & 3: Generate Summary + Terms + Quiz from condensed context
    condensed_notes = notes[:10000]
    draft_context = (
        f"Condensed Lecture Notes:\n{condensed_notes}\n\n"
        f"Full Extracted Concepts Across All Pages:\n{merged_extracted.model_dump_json(indent=2)}"
    )
    draft_pack = _call_structured(
        client,
        MAIN_MODEL,
        prompts.V3_STEP2_SUMMARIZE_SYSTEM + "\n\n" + prompts.V3_STEP3_QUIZ_SYSTEM,
        draft_context,
        StudyPack,
    )

    # Step 4: Grounding & Hallucination Check
    verify_input = (
        f"Extracted Source Facts:\n{merged_extracted.model_dump_json(indent=2)}\n\n"
        f"Draft Study Pack JSON:\n{draft_pack.model_dump_json(indent=2)}"
    )
    verified_pack = _call_structured(
        client, MAIN_MODEL, prompts.V3_STEP4_VERIFY_SYSTEM, verify_input, StudyPack
    )

    elapsed = round(time.time() - t0, 2)
    return verified_pack, {
        "version": "v3_chained",
        "models": f"{FAST_MODEL} -> {MAIN_MODEL} (4-step chunked chain)",
        "latency_s": elapsed,
        "chunks_processed": len(chunks),
    }

def ask_doubt(notes: str, chat_history: List[Dict[str, str]], question: str) -> str:
    client = get_client()
    system_prompt = (
        "You are a helpful, concise university teaching assistant. "
        "Answer the student's question using ONLY the provided lecture notes. "
        "If the answer is not in the notes, say 'This is not covered in your uploaded notes,' "
        "and then briefly offer general guidance clearly labeled as outside the notes.\n\n"
        f"Lecture Notes (excerpt):\n{notes[:10000]}"
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history[-6:])  # Keep last 6 turns to stay under Groq's 8K TPM limit
    messages.append({"role": "user", "content": question})

    response = client.chat.completions.create(
        model=MAIN_MODEL,
        temperature=0.3,
        messages=messages,
    )
    return response.choices[0].message.content