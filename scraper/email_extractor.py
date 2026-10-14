"""
scraper/email_extractor.py
Extracts email addresses from LinkedIn post text using Regex
"""

import re


# Standard email regex pattern — local part MUST start and end with an alphanumeric character
EMAIL_REGEX = re.compile(
    r"""
    (?<![/@\w])
    (
        [a-zA-Z0-9][a-zA-Z0-9._%+\-]*[a-zA-Z0-9]
        @
        [a-zA-Z0-9.\-]+
        \.
        [a-zA-Z]{2,}
    )
    (?!\.[a-zA-Z])
    """,
    re.VERBOSE | re.IGNORECASE
)

# Obfuscated pattern: name [at] domain [dot] com or name(at)domain.com
OBFUSCATED_REGEX = re.compile(
    r'([a-zA-Z0-9._%+\-]+)\s*(?:@|\[at\]|\(at\))\s*([a-zA-Z0-9.\-]+)\s*(?:\.|\[dot\]|\(dot\))\s*([a-zA-Z]{2,})',
    re.IGNORECASE
)

# Common spam/placeholder emails to ignore
IGNORED_EMAILS = {
    "example@gmail.com",
    "test@test.com",
    "email@example.com",
    "noreply@linkedin.com",
    "no-reply@linkedin.com",
    "jobs@linkedin.com",
}


def extract_emails(text: str) -> list[str]:
    """
    Extract all valid email addresses from given text.
    Returns list of unique, cleaned email addresses.
    """
    if not text:
        return []

    # Find all standard emails in text
    found = EMAIL_REGEX.findall(text)

    # Find obfuscated emails (e.g. hr [at] company [dot] com)
    obf_matches = OBFUSCATED_REGEX.findall(text)
    for user, domain, tld in obf_matches:
        assembled = f"{user}@{domain}.{tld}".lower()
        found.append(assembled)

    # Clean, lowercase, deduplicate, filter ignored
    emails = []
    seen = set()
    for email in found:
        email = email.lower().strip().strip(".-_:")
        if "@" in email:
            user_part, domain_part = email.split("@", 1)
            user_part = user_part.strip(".-_:")
            domain_part = domain_part.strip(".-_:")
            email = f"{user_part}@{domain_part}"
        if len(email) > 5 and email not in seen and email not in IGNORED_EMAILS:
            seen.add(email)
            emails.append(email)

    return emails


def extract_emails_from_posts(posts: list[dict]) -> list[dict]:
    """
    Given a list of scraped post dicts, extract emails from each.
    Returns list of email records with source post info.
    """
    email_records = []
    seen_emails = set()

    for post in posts:
        text = post.get("post_text", "")
        emails = extract_emails(text)

        for email in emails:
            if email not in seen_emails:
                seen_emails.add(email)
                email_records.append({
                    "email": email,
                    "post_url": post.get("post_url", ""),
                    "post_text": text[:500],   # Store first 500 chars for context
                    "poster_name": post.get("poster_name", ""),
                    "company": post.get("company", ""),
                    "hashtags": post.get("hashtags", []),
                })

    print(f"[EmailExtractor] Found {len(email_records)} unique emails from {len(posts)} posts")
    return email_records
