import os
import json
import re
from pypdf import PdfReader
import pickle
from dotenv import load_dotenv

load_dotenv()

RESUME_FOLDER = "resumes"
VECTOR_STORE_PATH = "vector_store"


def get_all_resumes() -> dict:
    resumes = {}
    if not os.path.exists(RESUME_FOLDER):
        print("⚠️ resumes/ folder not found", flush=True)
        return resumes
    for file in os.listdir(RESUME_FOLDER):
        if file.endswith(".pdf"):
            name = file.replace(".pdf", "")
            resumes[name] = os.path.join(RESUME_FOLDER, file)
    if not resumes:
        print("⚠️ No PDF files found in resumes/ folder", flush=True)
    return resumes


def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}", flush=True)
        return ""


def split_into_chunks(text: str, chunk_size: int = 100) -> list:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks


def setup_resumes():
    print("Scanning resumes folder...", flush=True)
    resumes = get_all_resumes()

    if not resumes:
        print("No resumes found.", flush=True)
        return

    os.makedirs(VECTOR_STORE_PATH, exist_ok=True)

    for resume_name, resume_path in resumes.items():
        resume_store_path = os.path.join(VECTOR_STORE_PATH, resume_name)
        chunks_file = os.path.join(resume_store_path, "chunks.pkl")

        if os.path.exists(chunks_file):
            print(f"⏭️  {resume_name} already prepared, skipping", flush=True)
            continue

        print(f"Processing {resume_name}...", flush=True)
        text = extract_text_from_pdf(resume_path)
        chunks = split_into_chunks(text)

        os.makedirs(resume_store_path, exist_ok=True)
        with open(chunks_file, "wb") as f:
            pickle.dump(chunks, f)

        print(f"✅ {resume_name} done — {len(chunks)} chunks created", flush=True)

    print("\n✅ All resumes processed and ready!", flush=True)


def process_new_resume(resume_path: str, resume_name: str):
    print(f"Processing new resume: {resume_name}", flush=True)
    os.makedirs(VECTOR_STORE_PATH, exist_ok=True)

    text = extract_text_from_pdf(resume_path)
    chunks = split_into_chunks(text)

    resume_store_path = os.path.join(VECTOR_STORE_PATH, resume_name)
    os.makedirs(resume_store_path, exist_ok=True)

    with open(os.path.join(resume_store_path, "chunks.pkl"), "wb") as f:
        pickle.dump(chunks, f)

    print(f"✅ {resume_name} ready!", flush=True)


def match_resumes(jd_text: str) -> list:
    from groq import Groq
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    resumes = get_all_resumes()
    if not resumes:
        return []

    # Build all resume summaries in one shot
    resume_summaries = ""
    resume_texts = {}

    for resume_name, resume_path in resumes.items():
        if not os.path.exists(resume_path):
            continue
        text = extract_text_from_pdf(resume_path)
        resume_texts[resume_name] = resume_path
        # Send first 1500 chars per resume to save tokens while keeping full context
        resume_summaries += f"\n\nRESUME_NAME: {resume_name}\n{text[:1500]}\n---"

    # Single AI prompt to score all resumes
    prompt = f"""
    You are a recruiter. Score each resume against the job description.

    Score from 0-100 based on:
    - Skills match (35%)
    - How specifically resume targets this role (35%)
    - Project and experience relevance (30%)

    Job Description:
    {jd_text}

    Resumes to score:
    {resume_summaries}

    Return ONLY a JSON array, nothing else:
    [
        {{"resume": "resume_name", "score": 75, "reason": "one line reason"}},
        {{"resume": "resume_name2", "score": 60, "reason": "one line reason"}}
    ]
    """

    try:
        model_name = os.getenv("GROQ_RAG_MODEL", "openai/gpt-oss-20b")
        response = groq_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.choices[0].message.content.strip()

        cleaned = re.sub(r"```json|```", "", raw).strip()
        json_match = re.search(r'\[.*?\]', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group()

        data = json.loads(cleaned)

        results = []
        for item in data:
            resume_name = item.get("resume", "")
            results.append({
                "resume": resume_name,
                "score": float(item.get("score", 50)),
                "reason": item.get("reason", ""),
                "path": resume_texts.get(resume_name, "")
            })

        # Sort highest score first
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    except Exception as e:
        print(f"Scoring error: {e}", flush=True)
        # Fallback - return all resumes with 50% score
        return [
            {"resume": name, "score": 50.0, "reason": "Could not score", "path": path}
            for name, path in resume_texts.items()
        ]


def get_context(resume_name: str, jd_text: str = "", top_k: int = 8) -> str:
    """Returns the full text context of the chosen resume."""
    resumes = get_all_resumes()
    if resume_name in resumes and os.path.exists(resumes[resume_name]):
        text = extract_text_from_pdf(resumes[resume_name])
        if text.strip():
            return text

    # Fallback to pickled chunks if present
    resume_store_path = os.path.join(VECTOR_STORE_PATH, resume_name)
    chunks_path = os.path.join(resume_store_path, "chunks.pkl")
    if os.path.exists(chunks_path):
        try:
            with open(chunks_path, "rb") as f:
                chunks = pickle.load(f)
            return "\n\n".join(chunks)
        except Exception:
            pass

    return ""