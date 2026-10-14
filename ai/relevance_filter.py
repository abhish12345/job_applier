"""
ai/relevance_filter.py
Filters posts based on job profile keywords and years of experience criteria.
Ensures we only apply to relevant roles matching candidate's level.
"""

import re
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config


# Regular expressions for detecting years of experience in post text
EXPERIENCE_PATTERNS = [
    # "2-4 years", "2 to 5 yrs", "1-3 Yrs"
    re.compile(r'(\d+)\s*(?:-|to)\s*(\d+)\s*(?:years?|yrs?|yr)\b', re.IGNORECASE),
    # "3+ years", "3 + yrs", "minimum 2 years", "min 3 yrs"
    re.compile(r'(?:min(?:imum)?\s*)?(\d+)\s*\+\s*(?:years?|yrs?|yr)\b', re.IGNORECASE),
    # "3 years of experience", "2 yrs exp", "3+ yoe"
    re.compile(r'(\d+)\s*(?:years?|yrs?|yr|yoe)\s*(?:of\s*)?(?:experience|exp)?\b', re.IGNORECASE),
    # "experience: 2-4 years"
    re.compile(r'(?:exp|experience)\s*[:\-]\s*(\d+)(?:\s*(?:-|to)\s*(\d+))?\s*(?:years?|yrs?)?', re.IGNORECASE),
]

# Fresher / entry-level keywords
FRESHER_KEYWORDS = [
    "fresher", "freshers", "entry level", "entry-level", "graduate",
    "intern", "internship", "0-1 year", "0-2 years", "0-1 yr", "0 to 1", "junior"
]

# High-seniority titles that indicate senior leadership (skip if targeting <= 3 years)
SENIOR_LEADERSHIP_TITLES = [
    "director", "vp", "vice president", "principal", "staff engineer",
    "head of", "architect", "lead architect", "associate director"
]


def extract_required_experience(text: str) -> dict:
    """
    Extracts min and max years of experience mentioned in post text.
    Returns: {"min_years": float or None, "max_years": float or None, "is_fresher": bool}
    """
    text_lower = text.lower()

    # Check for fresher keywords
    if any(k in text_lower for k in FRESHER_KEYWORDS):
        return {"min_years": 0.0, "max_years": 1.0, "is_fresher": True}

    found_mins = []
    found_maxs = []

    for pattern in EXPERIENCE_PATTERNS:
        matches = pattern.findall(text)
        for match in matches:
            if isinstance(match, tuple):
                # Group 1 = min, Group 2 = max (if present)
                val1 = match[0]
                val2 = match[1] if len(match) > 1 else ""

                if val1 and val1.isdigit():
                    num1 = float(val1)
                    # Filter out unreasonable years (e.g., 2024, 50, etc.)
                    if 0 <= num1 <= 20:
                        found_mins.append(num1)

                if val2 and val2.isdigit():
                    num2 = float(val2)
                    if 0 <= num2 <= 20:
                        found_maxs.append(num2)
            elif isinstance(match, str) and match.isdigit():
                num = float(match)
                if 0 <= num <= 20:
                    found_mins.append(num)

    min_val = min(found_mins) if found_mins else None
    max_val = max(found_maxs) if found_maxs else (min_val if min_val is not None else None)

    return {
        "min_years": min_val,
        "max_years": max_val,
        "is_fresher": False,
    }


def is_job_relevant(post_text: str) -> tuple[bool, str]:
    """
    Checks if post matches:
    1. Target role keywords (AI, ML, Python, Data Science, MLOps, etc.)
    2. Target years of experience (<= Config.MAX_TARGET_EXPERIENCE)
    
    Returns: (is_relevant: bool, reason: str)
    """
    text_lower = post_text.lower()

    # ── 1. Check Profile / Role Keyword Relevance ─────────────
    matched_keywords = [
        kw for kw in Config.TARGET_ROLE_KEYWORDS
        if kw in text_lower
    ]

    if not matched_keywords:
        return False, "No matching profile keywords found in post"

    # ── 2. Check Leadership Title Mismatch ─────────────────────
    # If targeting <= 3 years, avoid high leadership roles
    if Config.MAX_TARGET_EXPERIENCE <= 4:
        for title in SENIOR_LEADERSHIP_TITLES:
            if title in text_lower:
                # If post explicitly says Director / VP / Principal / Staff Engineer
                # Check if it's hiring for that role or just poster's headline
                if f"hiring: {title}" in text_lower or f"looking for {title}" in text_lower or f"role: {title}" in text_lower:
                    return False, f"Post requires senior leadership ({title})"

    # ── 3. Check Years of Experience ──────────────────────────
    exp_info = extract_required_experience(post_text)

    # If post mentions minimum experience requirement
    if exp_info["min_years"] is not None:
        if exp_info["min_years"] > Config.MAX_TARGET_EXPERIENCE:
            return False, f"Requires {exp_info['min_years']}+ years exp (exceeds target of <= {Config.MAX_TARGET_EXPERIENCE} yrs)"

    return True, f"Matched keywords: {', '.join(matched_keywords[:3])} | Exp: <= {Config.MAX_TARGET_EXPERIENCE} yrs"
