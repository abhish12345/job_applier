"""
config.py - Central configuration loader from .env
All settings are read from .env file - nothing hardcoded
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ─── LINKEDIN SEARCH QUERIES ────────────────────────────
    # Supports BOTH hashtags (#aiml #hiring) AND non-hashtag text queries (e.g. 'hiring AI engineer email')
    _raw_queries = os.getenv("LINKEDIN_SEARCH_QUERIES") or os.getenv(
        "LINKEDIN_HASHTAGS",
        "#aiml #hiring,#machinelearning #hiring,#python #hiring"
    )
    LINKEDIN_SEARCH_QUERIES: list[str] = [
        tag.strip() for tag in _raw_queries.split(",") if tag.strip()
    ]
    # Retain LINKEDIN_HASHTAGS as alias for backward compatibility
    LINKEDIN_HASHTAGS: list[str] = LINKEDIN_SEARCH_QUERIES
    LINKEDIN_SCRAPE_DAYS: int = int(os.getenv("LINKEDIN_SCRAPE_DAYS", "7"))
    MAX_POSTS_PER_SEARCH: int = int(os.getenv("MAX_POSTS_PER_SEARCH", "50"))
    SCROLL_PAUSE_TIME: float = float(os.getenv("SCROLL_PAUSE_TIME", "3"))
    HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"

    # Date filter map for LinkedIn URL param
    SCRAPE_DAYS_TO_LINKEDIN_FILTER: dict = {
        7:  "past-week",
        14: "past-2-weeks",
        30: "past-month",
    }

    @classmethod
    def get_linkedin_date_filter(cls) -> str:
        return cls.SCRAPE_DAYS_TO_LINKEDIN_FILTER.get(
            cls.LINKEDIN_SCRAPE_DAYS, "past-week"
        )

    # ─── YOUR PROFILE ───────────────────────────────────────
    YOUR_NAME: str = os.getenv("YOUR_NAME", "Candidate")
    YOUR_ROLE: str = os.getenv("YOUR_ROLE", "AI/ML Engineer")
    YOUR_SKILLS: str = os.getenv("YOUR_SKILLS", "Python, Machine Learning")
    YOUR_EXPERIENCE: str = os.getenv("YOUR_EXPERIENCE", "2 years")
    MAX_TARGET_EXPERIENCE: float = float(os.getenv("MAX_TARGET_EXPERIENCE", "3"))
    TARGET_ROLE_KEYWORDS: list[str] = [
        kw.strip().lower()
        for kw in os.getenv(
            "TARGET_ROLE_KEYWORDS",
            "machine learning,ai,python,ml,data science,deep learning,nlp,mlops,generative ai,computer vision,llm,artificial intelligence"
        ).split(",")
        if kw.strip()
    ]
    YOUR_MOBILE: str = os.getenv("YOUR_MOBILE", "")          # Required for signature
    YOUR_LINKEDIN: str = os.getenv("YOUR_LINKEDIN", "")
    YOUR_GITHUB: str = os.getenv("YOUR_GITHUB", "")
    YOUR_PORTFOLIO: str = os.getenv("YOUR_PORTFOLIO", "")    # Optional
    RESUME_PATH: str = os.getenv("RESUME_PATH", "assets/resume.pdf")

    # ─── OLLAMA ─────────────────────────────────────────────
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma")

    # ─── SMTP ───────────────────────────────────────────────
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_EMAIL: str = os.getenv("SMTP_EMAIL", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_SUBJECT_PREFIX: str = os.getenv("EMAIL_SUBJECT_PREFIX", "Application for")

    # ─── MONGODB ────────────────────────────────────────────
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "linkedin_scraper")
    MONGO_POSTS_COLLECTION: str = os.getenv("MONGO_POSTS_COLLECTION", "scraped_posts")
    MONGO_EMAILS_COLLECTION: str = os.getenv("MONGO_EMAILS_COLLECTION", "extracted_emails")
    MONGO_SENT_COLLECTION: str = os.getenv("MONGO_SENT_COLLECTION", "sent_emails")
    MONGO_RESPONSES_COLLECTION: str = os.getenv("MONGO_RESPONSES_COLLECTION", "email_responses")

    # ─── FILTERS & SAFETY ───────────────────────────────────
    EMAIL_COOLDOWN_DAYS: int = int(os.getenv("EMAIL_COOLDOWN_DAYS", "15"))
    MAX_EMAILS_PER_DAY: int = int(os.getenv("MAX_EMAILS_PER_DAY", "30"))
    DELAY_BETWEEN_EMAILS: int = int(os.getenv("DELAY_BETWEEN_EMAILS", "60"))

    @classmethod
    def validate(cls):
        """Validate required configs are set"""
        errors = []
        if not cls.SMTP_EMAIL:
            errors.append("SMTP_EMAIL is required in .env")
        if not cls.SMTP_PASSWORD:
            errors.append("SMTP_PASSWORD is required in .env")
        if not cls.YOUR_MOBILE:
            errors.append("YOUR_MOBILE is required in .env (shown in every email signature)")
        if not os.path.exists(cls.RESUME_PATH):
            errors.append(f"Resume not found at: {cls.RESUME_PATH}")
        if errors:
            raise ValueError("\n".join(["[CONFIG ERROR]"] + errors))
        return True

    @classmethod
    def display(cls):
        """Print current config (masks passwords)"""
        print("=" * 50)
        print("📋 CURRENT CONFIGURATION")
        print("=" * 50)
        print(f"  Scrape Days      : {cls.LINKEDIN_SCRAPE_DAYS}")
        print(f"  Hashtags         : {cls.LINKEDIN_HASHTAGS}")
        print(f"  Ollama Model     : {cls.OLLAMA_MODEL}")
        print(f"  SMTP Email       : {cls.SMTP_EMAIL}")
        print(f"  MongoDB URI      : {cls.MONGO_URI}")
        print(f"  Your Role        : {cls.YOUR_ROLE}")
        print(f"  Target Max Exp   : <= {cls.MAX_TARGET_EXPERIENCE} years")
        print(f"  Role Keywords    : {', '.join(cls.TARGET_ROLE_KEYWORDS[:4])}...")
        print(f"  Your Mobile      : {cls.YOUR_MOBILE}")
        print(f"  Your LinkedIn    : {cls.YOUR_LINKEDIN}")
        print(f"  Your GitHub      : {cls.YOUR_GITHUB}")
        if cls.YOUR_PORTFOLIO:
            print(f"  Your Portfolio   : {cls.YOUR_PORTFOLIO}")
        print(f"  Cooldown Days    : {cls.EMAIL_COOLDOWN_DAYS}")
        print(f"  Max Emails/Day   : {cls.MAX_EMAILS_PER_DAY}")
        print(f"  Resume           : {cls.RESUME_PATH}")
        print("=" * 50)
