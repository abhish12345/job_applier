"""
ai/ollama_handler.py
Generates anti-spam, human-like job application emails via Ollama.
Prompts are engineered to avoid spam triggers and sound genuinely personal.
"""

import requests
import random
import re
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config


# ─────────────────────────────────────────────────────────────────────────────
# SPAM TRIGGER WORDS — Ollama is told to NEVER use these
# ─────────────────────────────────────────────────────────────────────────────
SPAM_WORDS = [
    "guaranteed", "free", "urgent", "act now",
    "click here", "apply now", "don't miss", "limited time",
    "exclusive", "amazing", "incredible", "best ever",
    "100%", "no experience", "earn money", "work from home",
    "congratulations", "winner", "selected", "offer expires",
]

# ─────────────────────────────────────────────────────────────────────────────
# EMAIL BODY PROMPT — High-Impact Professional Style
# ─────────────────────────────────────────────────────────────────────────────
BODY_PROMPT = """You are {name}, a professional {role} with {experience} of hands-on experience.
Your technical core competencies: {skills}

A recruiter or hiring manager posted this opportunity on LinkedIn:
\"\"\"
{post_text}
\"\"\"

Write a polished, impressive, and professional job application email directly to this recruiter.

Follow this proven, attractive structure:
1. GREETING:
   - "Hi [Recruiter Name]," if their name is found in the post or headline.
   - Otherwise, "Hi there,"

2. OPENING & HOOK:
   - State clearly: "I came across your post regarding the [Specific Role Title / Tech Opportunity] and would like to express my strong interest."

3. VALUE PROPOSITION & TECH STACK:
   - Write 1-2 impactful paragraphs highlighting your practical expertise as a {role} with {experience} of experience.
   - Emphasize building and deploying production-grade solutions across Machine Learning, Deep Learning, NLP, Generative AI, LLMs, and Python.
   - Mention key tools/libraries from: Python, PyTorch, TensorFlow, Scikit-learn, FastAPI, Docker, SQL, and Cloud/MLOps that are relevant to their post.
   - Mention relevant practical capabilities: developing models, building AI pipelines, RAG/vector embeddings, AI APIs, and scalable deployment.

4. ALIGNMENT & AVAILABILITY:
   - "I believe my hands-on background aligns well with the requirements of this role. I am open to discussing relevant opportunities and how I can contribute to your team."

5. CALL TO ACTION:
   - "Please find my updated resume attached for your review. I would welcome the opportunity to discuss this further."

CRITICAL GUIDELINES:
- Tone: Confident, skilled, articulate, and respectful.
- DO NOT use gimmicky spam buzzwords like: {spam_words}
- DO NOT write sign-offs like "Best regards" or contact details at the end (the system appends your verified signature automatically).
- Output ONLY the clean email body text without headers, subject, or quotes.

Write the email now:"""


# Technical and business abbreviations that should NOT be flagged as spam caps
TECH_ACRONYMS = {
    "AI", "ML", "DL", "CV", "LLM", "LLMS", "NLP", "RAG", "SQL", "AWS", "GCP",
    "API", "APIS", "GPU", "GPUS", "CUDA", "BERT", "GPT", "REST", "ETL", "MLOPS",
    "ANN", "CNN", "RNN", "SOTA", "PWC", "IBM", "TCS", "SAP", "AMD", "IIT", "NIT",
    "USA", "NYC", "HR", "CEO", "CTO", "VP", "IT"
}

# ─────────────────────────────────────────────────────────────────────────────
# SUBJECT LINE PROMPT — Modern, High-Converting Executive Style
# ─────────────────────────────────────────────────────────────────────────────
SUBJECT_PROMPT = """You are an expert technical recruiter and executive talent scout.
Write ONE modern, highly attractive email subject line for an application to this job post.

Job Post Details:
\"\"\"
{post_text_short}
\"\"\"

Applicant Profile:
- Full Name: {name}
- Current Role: {role}
- Experience: {experience}
- Core Skills: {skills}
- Target Company: {company}

DESIGN INSTRUCTIONS:
- The subject line must look polished, confident, and professional (like top tech engineers from Stripe, Meta, OpenAI).
- Choose the best matching style below:
  * Style 1: Application: [Role] — [Your Name] ([Tech1] & [Tech2])
  * Style 2: [Role] Role at [Company] | [Your Name]
  * Style 3: [Your Name] — [Role] ([Tech1], [Tech2] | [Experience])
  * Style 4: Regarding the [Role] post — [Your Name]
- Pick the most relevant tech keywords from the post (e.g., PyTorch, LLMs, RAG, FastAPI, Python).
- If company name is not specifically known, use Style 1 or Style 3.
- Length: 6 to 11 words. (Under 80 characters).
- FORBIDDEN: NO spam buzzwords ("Urgent", "Excited", "Hire me", "Greetings"), NO exclamation marks, NO all-caps words except technical acronyms like AI, ML, LLM, RAG.
- Output ONLY the final subject line text. NO quotation marks. NO explanation.

Subject Line:"""


# ─────────────────────────────────────────────────────────────────────────────
# SPAM CHECKER
# ─────────────────────────────────────────────────────────────────────────────
def check_spam_score(text: str) -> dict:
    """
    Spam score checker.
    Returns score (0=clean, higher=spammier) and triggered words.
    Only flags actual shouting words (4+ letters all-caps like URGENT, FREE)
    while whitelisting tech and business acronyms.
    """
    text_lower = text.lower()
    triggered  = [w for w in SPAM_WORDS if w in text_lower]
    
    # Check for shouting all-caps words (4+ characters, e.g., 'URGENT', 'APPLY')
    raw_caps = re.findall(r'\b[A-Z]{4,}\b', text)
    caps_words = [w for w in raw_caps if w.upper() not in TECH_ACRONYMS]
    
    exclamations = text.count("!")
    links = len(re.findall(r'http[s]?://', text))

    score = (
        len(triggered) * 3 +
        len(caps_words) * 2 +
        exclamations * 2 +
        links * 5
    )
    return {
        "score": score,
        "triggered_spam_words": triggered,
        "caps_words": caps_words,
        "exclamations": exclamations,
        "links": links,
        "is_clean": score == 0,
    }


def clean_email_body(body: str) -> str:
    """
    Post-process AI output to remove any remaining spam signals.
    """
    # Remove exclamation marks
    body = body.replace("!", ".")

    # Remove any URLs that slipped through
    body = re.sub(r'http[s]?://\S+', '', body)

    # Remove non-tech ALL CAPS words (replace with Title Case)
    def clean_caps(m):
        w = m.group(1)
        return w if w.upper() in TECH_ACRONYMS else w.title()

    body = re.sub(r'\b([A-Z]{3,})\b', clean_caps, body)

    # Trim extra whitespace
    body = re.sub(r'\n{3,}', '\n\n', body).strip()

    return body


def clean_subject(subject: str) -> str:
    """Remove spam signals and prefixes from subject line"""
    subject = subject.strip().strip('"\'`')
    # Strip leading prefixes like "Subject: " or "Re: " if model includes them
    subject = re.sub(r'^(?:subject|re)\s*[:\-]\s*', '', subject, flags=re.IGNORECASE)
    subject = subject.replace("!", "")

    # Clean non-tech all-caps
    def clean_caps(m):
        w = m.group(1)
        return w if w.upper() in TECH_ACRONYMS else w.title()

    subject = re.sub(r'\b([A-Z]{3,})\b', clean_caps, subject)
    return subject.strip()


# ─────────────────────────────────────────────────────────────────────────────
# OLLAMA CALLER
# ─────────────────────────────────────────────────────────────────────────────
def _call_ollama(prompt: str, max_tokens: int = 600, temperature: float = 0.7) -> str | None:
    """Call Ollama API. Returns response text or None on failure."""
    try:
        response = requests.post(
            f"{Config.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": Config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                }
            },
            timeout=120
        )
        response.raise_for_status()
        data = response.json()
        resp_text = (data.get("response") or "").strip()
        return resp_text if resp_text else None
    except requests.exceptions.ConnectionError:
        print(f"[Ollama] Connection error at {Config.OLLAMA_BASE_URL}")
        return None
    except Exception as e:
        print(f"[Ollama] Generation failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
def generate_email_body(post_text: str, company: str = "") -> str:
    """
    Generate a spam-safe, human-like email body using Ollama.
    Falls back to clean template if Ollama unavailable.
    """
    prompt = BODY_PROMPT.format(
        name=Config.YOUR_NAME,
        role=Config.YOUR_ROLE,
        experience=Config.YOUR_EXPERIENCE,
        skills=Config.YOUR_SKILLS,
        post_text=post_text[:1200],
        spam_words=", ".join(SPAM_WORDS[:12]),
    )

    body = _call_ollama(prompt, max_tokens=350, temperature=0.75)

    if not body:
        print("[Ollama] Using fallback email template")
        return _fallback_email_body(post_text)

    # Post-process for spam signals
    body = clean_email_body(body)

    # Check spam score
    spam = check_spam_score(body)
    if spam["score"] > 0:
        print(f"[Ollama] Spam score: {spam['score']} | Issues: {spam}")
    else:
        print(f"[Ollama] Email is spam-clean (score: 0)")

    print(f"[Ollama] Email generated ({len(body.split())} words) via {Config.OLLAMA_MODEL}")
    return body


def generate_subject_line(post_text: str, company: str = "") -> str:
    """
    Generate a modern, attractive, high-converting subject line using Ollama.
    Falls back to polished executive template if Ollama unavailable.
    """
    prompt = SUBJECT_PROMPT.format(
        post_text_short=post_text[:500],
        name=Config.YOUR_NAME,
        role=Config.YOUR_ROLE,
        experience=Config.YOUR_EXPERIENCE,
        skills=Config.YOUR_SKILLS,
        company=company or "your team",
    )

    subject = _call_ollama(prompt, max_tokens=40, temperature=0.6)

    if not subject:
        return _fallback_subject(company)

    subject = clean_subject(subject)

    # Validate — must be reasonable length (under 85 chars, over 8 chars)
    if not subject or len(subject) > 85 or len(subject) < 8:
        print(f"[Ollama] Subject length {len(subject)} out of range — using fallback subject")
        return _fallback_subject(company)

    spam = check_spam_score(subject)
    if spam["score"] > 0:
        print(f"[Ollama] Subject spam score {spam['score']} (flagged: {spam['triggered_spam_words']}) — using fallback subject")
        return _fallback_subject(company)

    print(f"[Ollama] Subject: '{subject}'")
    return subject


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK TEMPLATES (spam-clean, human-written style)
# ─────────────────────────────────────────────────────────────────────────────
_FALLBACK_BODIES = [
    # Template A — skill-match focused
    """Hi there,

I came across your post and noticed you're looking for someone with a background in AI/ML. I've been working with {skills} for {experience} and have hands-on experience building end-to-end ML pipelines.

I'd love to explore if there's a fit here. I've attached my resume for your review — would love to connect.

{name}
{role}""",

    # Template B — curiosity hook
    """Hello,

Your post caught my attention — the work you're describing aligns closely with what I've been doing for the past {experience}.

My background includes {skills}, and I enjoy solving the kind of problems you mentioned. I've attached my resume — happy to hop on a quick call if you'd like to know more.

{name}
{role}""",

    # Template C — direct and brief
    """Hi,

I saw your post and wanted to reach out. I'm a {role} with {experience} of experience, primarily working with {skills}.

I think I could bring genuine value to your team. Resume is attached — would love to connect.

{name}
{role}""",
]

_FALLBACK_SUBJECTS = [
    "Application: {role} — {name} ({experience} Exp)",
    "Application: {role} at {company} — {name}",
    "{name} | {role} ({skill1} & {skill2})",
    "{role} Role — {name} (Resume Attached)",
    "Application: {role} — {name} ({skill1}, PyTorch)",
]


def _fallback_email_body(post_text: str = "") -> str:
    """Pick a random spam-clean fallback template"""
    template = random.choice(_FALLBACK_BODIES)
    skills_list = Config.YOUR_SKILLS.split(",")
    return template.format(
        name=Config.YOUR_NAME,
        role=Config.YOUR_ROLE,
        experience=Config.YOUR_EXPERIENCE,
        skills=Config.YOUR_SKILLS.strip(),
    )


def _fallback_subject(company: str = "") -> str:
    """Pick a random spam-clean fallback subject"""
    template = random.choice(_FALLBACK_SUBJECTS)
    skills_list = [s.strip() for s in Config.YOUR_SKILLS.split(",")]
    return template.format(
        name=Config.YOUR_NAME,
        role=Config.YOUR_ROLE,
        experience=Config.YOUR_EXPERIENCE,
        company=company or "your team",
        skill1=skills_list[0] if len(skills_list) > 0 else "Python",
        skill2=skills_list[1] if len(skills_list) > 1 else "ML",
    )


def check_ollama_status() -> dict:
    """Check if Ollama is running and configured model is available"""
    try:
        resp   = requests.get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        return {
            "running": True,
            "available_models": models,
            "configured_model": Config.OLLAMA_MODEL,
            "model_available": any(Config.OLLAMA_MODEL in m for m in models),
        }
    except Exception:
        return {
            "running": False,
            "available_models": [],
            "configured_model": Config.OLLAMA_MODEL,
            "model_available": False,
        }
