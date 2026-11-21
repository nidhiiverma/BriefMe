# BriefMe — Lecture Notes to Study Pack

**Live App:** [`(https://briefme-ai.streamlit.app)`]

BriefMe turns raw lecture slides and notes (`.pdf`, `.docx`, `.pptx`, `.txt`, `.md`) into structured, exam-ready study packs using **Prompt Chaining**, **Strict JSON Schema Outputs**, and **Automated Rubric Evaluation** powered by Groq (`openai/gpt-oss-120b` & `openai/gpt-oss-20b`).

---

## Features
- **Multi-Format Upload:** Supports PDF, Word (`.docx`), PowerPoint (`.pptx`), Markdown, and plain text.
- **4-Step Prompt Chain:**
  1. **Concept Extraction:** Splits long decks into chunks and extracts core concepts, rules, and formulas.
  2. **Study Pack & Quiz Generation:** Creates an executive summary, key takeaways, a glossary table, and 6 tiered practice questions (Easy MCQs, Medium Short Answer, Hard Application).
  3. **Grounding Verification:** Cross-checks generated claims against extracted source facts to prevent hallucinations.
- **Ask Doubts (Tutor Chat):** A document-grounded Q&A assistant that answers questions strictly from the uploaded notes.
- **Automated Rubric Evaluator:** Scores every generated study pack out of 25 across Grounding, Completeness, Clarity, Quiz Quality, and Format, logging runs to `test-data/eval_log.csv`.
- **PDF Export:** Generates a clean, downloadable `study_pack.pdf` for offline revision.

---

## Prompt Architecture
| Version | Approach | Purpose |
| :--- | :--- | :--- |
| `v1_baseline` | Single zero-shot prompt | Unstructured baseline for comparison |
| `v2_structured` | Role + constraints + Pydantic schema | Enforces valid JSON via Groq `strict: true` |
| `v3_chained` | 4-step chunked chain + verifier | Handles long notes cleanly and minimizes hallucinations |

---

## Repository Structure
```text
BriefMe/
├── code/              # Streamlit UI, Groq pipeline, Pydantic schemas, evaluator
├── prompts/           # Versioned system and user prompts (v1/, v2/, v3/, final/)
├── test-data/         # Evaluation logs (eval_log.csv) and sample outputs
├── docs/              # Architecture diagrams and documentation
├── requirements.txt   # Python dependencies
└── README.md          # Overview and setup guide


## How to Run Locally
1. pip install -r requirements.txt
2. streamlit run code/app.py
