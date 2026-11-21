import os
import pandas as pd
import streamlit as st
import io
import os
import zipfile
from pipeline import run_v1_baseline, run_v2_structured, run_v3_chained, ask_doubt
from pypdf import PdfReader
from docx import Document
from pptx import Presentation
from fpdf import FPDF

from pipeline import run_v1_baseline, run_v2_structured, run_v3_chained
from evaluator import evaluate_output, LOG_PATH

st.set_page_config(page_title="BriefMe — Lecture Notes to Study Pack", page_icon="📚", layout="wide")
st.title("📚 BriefMe: Lecture Notes to Study Pack ")
st.caption("Powered by Groq (`openai/gpt-oss-120b` & `openai/gpt-oss-20b`) • Prompt Chaining • Strict JSON Schema • Rubric Evaluation")

with st.sidebar:
    st.header("⚙️ Prompt Configuration")
    version = st.selectbox(
        "Select Prompt Version",
        ["v3_chained (4-Step Chain + Verifier)", "v2_structured (Single-Call JSON)", "v1_baseline (Zero-Shot)"],
    )
    run_eval = st.checkbox("Run Automated Rubric Evaluation", value=True)
    st.markdown("---")
    st.markdown(
        "**Responsible AI Notice:** Do not upload confidential or personal student data. "
        "Always verify exam answers against your professor's slides."
    )


def extract_notes_from_upload(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    file_bytes = io.BytesIO(uploaded_file.getvalue())
    try:
        if name.endswith(".pdf"):
            reader = PdfReader(file_bytes)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if name.endswith(".docx"):
            doc = Document(file_bytes)
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text.strip() for cell in row.cells))
            return "\n".join(parts)
        if name.endswith(".pptx"):
            prs = Presentation(file_bytes)
            slides_text = []
            for idx, slide in enumerate(prs.slides, 1):
                slide_parts = [f"--- Slide {idx} ---"]
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        slide_parts.append(shape.text_frame.text)
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    notes = slide.notes_slide.notes_text_frame.text.strip()
                    if notes:
                        slide_parts.append(f"Speaker Notes: {notes}")
                slides_text.append("\n".join(slide_parts))
            return "\n\n".join(slides_text)
        return uploaded_file.getvalue().decode("utf-8")
    except zipfile.BadZipFile:
        st.error(
            f"⚠️ Could not open `{uploaded_file.name}`. It may be password-protected, corrupted, "
            "or an older `.ppt`/`.doc` file renamed to `.pptx`/`.docx`. "
            "Open it in PowerPoint/Keynote and export as **PDF** or re-save as **.pptx**."
        )
        return ""


def study_pack_to_markdown(pack) -> str:
    lines = [f"# {pack.title}", "", "## Executive Summary", pack.executive_summary, "", "## Key Takeaways"]
    lines.extend(f"- {b}" for b in pack.section_summaries)
    lines.extend(["", "## Key Terms"])
    for t in pack.key_terms:
        lines.append(f"- **{t.term}**: {t.definition} *(Example: {t.example_from_notes})*")
    lines.extend(["", "## Practice Questions"])
    for idx, q in enumerate(pack.practice_questions, 1):
        lines.append(f"\n### Q{idx} [{q.question_type} • {q.difficulty}]")
        lines.append(q.question)
        for opt in q.options:
            lines.append(f"- {opt}")
        lines.append(f"**Answer:** {q.correct_answer}")
        lines.append(f"**Explanation:** {q.explanation}")
    lines.extend(["", "## Grounding Verification", pack.grounding_notes])
    return "\n".join(lines)

def _pdf_safe(text: str) -> str:
    replacements = {"—": "-", "–": "-", "•": "*", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "..."}
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


def study_pack_to_pdf(pack) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    w = pdf.epw

    def write_line(text: str, h: int = 6):
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(w, h, _pdf_safe(text))

    pdf.set_font("Helvetica", "B", 16)
    write_line(pack.title, h=8)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 12)
    write_line("Executive Summary", h=8)
    pdf.set_font("Helvetica", "", 10)
    write_line(pack.executive_summary)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 12)
    write_line("Key Takeaways", h=8)
    pdf.set_font("Helvetica", "", 10)
    for b in pack.section_summaries:
        write_line(f"* {b}")
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 12)
    write_line("Key Terms", h=8)
    for t in pack.key_terms:
        pdf.set_font("Helvetica", "B", 10)
        write_line(t.term)
        pdf.set_font("Helvetica", "", 10)
        write_line(f"Definition: {t.definition}", h=5)
        write_line(f"Example: {t.example_from_notes}", h=5)
        pdf.ln(2)

    pdf.set_font("Helvetica", "B", 12)
    write_line("Practice Questions & Answers", h=8)
    for idx, q in enumerate(pack.practice_questions, 1):
        pdf.set_font("Helvetica", "B", 10)
        write_line(f"Q{idx} [{q.question_type} - {q.difficulty}]: {q.question}")
        pdf.set_font("Helvetica", "", 10)
        labels = ["A", "B", "C", "D"]
        for opt_i, opt in enumerate(q.options):
            prefix = f"{labels[opt_i]}) " if opt_i < 4 and not opt.lstrip().startswith(("A.", "B.", "C.", "D.", "A)", "B)", "C)", "D)")) else ""
            write_line(f"   {prefix}{opt}", h=5)
        write_line(f"Answer: {q.correct_answer}", h=5)
        write_line(f"Explanation: {q.explanation}", h=5)
        pdf.ln(2)

    pdf.set_font("Helvetica", "I", 9)
    write_line(f"Grounding Verification: {pack.grounding_notes}", h=5)
    return bytes(pdf.output())

tab1, tab2, tab3 = st.tabs([
    "🚀 Generate Study Pack",
    "💬 Ask Doubts (Tutor Chat)",
    "📊 Experiment Logs (v1 vs v2 vs v3)",
])
with tab1:
    uploaded = st.file_uploader(
        "Upload Lecture Notes (PDF, DOCX, PPTX, TXT, or MD)",
        type=["pdf", "docx", "pptx", "txt", "md"],
    )
    pasted_notes = st.text_area("Or paste your lecture notes here:", height=200)

    notes_text = ""
    if uploaded:
        notes_text = extract_notes_from_upload(uploaded)
    elif pasted_notes.strip():
        if notes_text:
            st.session_state["notes_text"] = notes_text

    if st.button("Generate Study Pack", type="primary", disabled=not notes_text):
        with st.spinner("Running Groq prompt pipeline..."):
            if version.startswith("v1"):
                output_text, meta = run_v1_baseline(notes_text)
                st.session_state["result"] = {"type": "v1", "text": output_text, "meta": meta}
                eval_input_str = output_text
            else:
                pack, meta = (
                    run_v2_structured(notes_text)
                    if version.startswith("v2")
                    else run_v3_chained(notes_text)
                )
                eval_input_str = pack.model_dump_json(indent=2)
                st.session_state["result"] = {"type": "structured", "pack": pack, "meta": meta, "json": eval_input_str}

        if run_eval:
            with st.spinner("Scoring against 5-point Evaluation Rubric..."):
                try:
                    st.session_state["score"] = evaluate_output(notes_text, eval_input_str, meta["version"], meta["latency_s"])
                except Exception:
                    st.session_state.pop("score", None)
                    st.warning("Rubric evaluation paused briefly due to Groq free-tier rate limit—your Study Pack is ready below!")
        else:
            st.session_state.pop("score", None)

    if "result" in st.session_state:
        res = st.session_state["result"]
        meta = res["meta"]
        if res["type"] == "v1":
            st.info(f"Version: `{meta['version']}` | Latency: `{meta['latency_s']}s`")
            st.markdown(res["text"])
        else:
            pack = res["pack"]
            st.success(f"Version: `{meta['version']}` | Latency: `{meta['latency_s']}s`")

            st.subheader(f"📖 {pack.title}")
            st.write(pack.executive_summary)

            st.subheader("🎯 Key Takeaways")
            for bullet in pack.section_summaries:
                st.markdown(f"- {bullet}")

            st.subheader("🔑 Key Terms")
            terms_df = pd.DataFrame([t.model_dump() for t in pack.key_terms])
            terms_df.columns = ["Term", "Definition", "Example / Context"]
            terms_df["Example / Context"] = terms_df["Example / Context"].replace("Not specified in notes", "—")
            st.dataframe(terms_df, use_container_width=True, hide_index=True)

            st.subheader("📝 Practice Questions")
            for idx, q in enumerate(pack.practice_questions, 1):
                st.markdown(f"**Q{idx} [{q.question_type} • {q.difficulty}]:** {q.question}")
                if q.options:
                    labels = ["A", "B", "C", "D"]
                    for opt_i, opt in enumerate(q.options):
                        prefix = f"{labels[opt_i]}) " if opt_i < len(labels) and not opt.lstrip().startswith(("A.", "B.", "C.", "D.", "A)", "B)", "C)", "D)")) else ""
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{prefix}{opt}")
                with st.expander("Reveal Answer & Explanation"):
                    st.markdown(f"**Answer:** {q.correct_answer}")
                    st.caption(f"**Explanation:** {q.explanation}")

            st.info(f"**Grounding Verification:** {pack.grounding_notes}")

            st.download_button(
             "⬇️ Download Study Pack (PDF)",
             data=study_pack_to_pdf(pack),
             file_name="study_pack.pdf",
             mime="application/pdf",
         )

        if "score" in st.session_state:
            score = st.session_state["score"]
            total = (
                score.grounding_factuality
                + score.completeness
                + score.clarity_structure
                + score.question_quality
                + score.format_compliance
            )
            st.subheader(f"⚖️ Rubric Score: {total}/25")
            cols = st.columns(5)
            cols[0].metric("Grounding", f"{score.grounding_factuality}/5")
            cols[1].metric("Completeness", f"{score.completeness}/5")
            cols[2].metric("Clarity", f"{score.clarity_structure}/5")
            cols[3].metric("Quiz Quality", f"{score.question_quality}/5")
            cols[4].metric("Format", f"{score.format_compliance}/5")
            if score.failure_cases_or_gaps:
                st.warning("Identified Gaps / Failure Cases: " + "; ".join(score.failure_cases_or_gaps))
            st.write(f"**Verdict:** {score.overall_verdict}")

with tab2:
    st.subheader("💬 Ask Doubts About Your Lecture Notes")
    active_notes = st.session_state.get("notes_text") or notes_text
    if not active_notes:
        st.info("Upload or paste your lecture notes in the **Generate Study Pack** tab first.")
    else:
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        with st.form("doubt_chat_form", clear_on_submit=True):
            user_q = st.text_input("Ask any doubt about your notes:")
            submitted = st.form_submit_button("Ask")

        if submitted and user_q.strip():
            st.session_state.chat_messages.append({"role": "user", "content": user_q})
            with st.chat_message("user"):
                st.markdown(user_q)

            with st.chat_message("assistant"):
                with st.spinner("Thinking from your notes..."):
                    reply = ask_doubt(active_notes, st.session_state.chat_messages[:-1], user_q)
                    st.markdown(reply)
            st.session_state.chat_messages.append({"role": "assistant", "content": reply})

with tab3:
    st.subheader("Logged Prompt Experiments")
    if os.path.exists(LOG_PATH):
        df = pd.read_csv(LOG_PATH)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No experiments logged yet. Run a generation with Rubric Evaluation enabled to populate this table.")