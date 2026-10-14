"""
mailer/email_verifier.py
Pre-send email validation and verification:
1. Syntax validation (RFC 5322)
2. Disposable / temporary email filter
3. Spam-trap / system email filter
4. Live DNS MX Record check (verifies domain can receive emails)
"""

import re
import socket
import dns.resolver

# Standard strict email regex — local part must start with letter/digit
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9_.+-]*[a-zA-Z0-9]@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
)

# Disposable email providers / domains to avoid
DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "sharklasers.com", "throwawaymail.com", "getairmail.com", "yopmail.com",
    "trashmail.com", "maildrop.cc", "dispostable.com", "temp-mail.org",
    "example.com", "test.com", "sample.com", "domain.com", "fake.com"
}

# Spam trap / system accounts to avoid
SYSTEM_USERNAMES = {
    "abuse", "postmaster", "spam", "webmaster", "security",
    "hostmaster", "root", "ftp", "mailer-daemon"
}

# In-memory cache for verified domains so we don't query DNS repeatedly
_DOMAIN_MX_CACHE = {}


def check_syntax(email: str) -> bool:
    """Validate email format and length"""
    if not email or len(email) > 254:
        return False
    if not EMAIL_REGEX.match(email):
        return False
    # Check consecutive dots
    if ".." in email:
        return False
    return True


def check_domain_mx(domain: str) -> bool:
    """
    Query DNS for active MX (Mail Exchange) records.
    Returns True if domain has mail servers configured.
    """
    domain = domain.lower().strip()
    if domain in _DOMAIN_MX_CACHE:
        return _DOMAIN_MX_CACHE[domain]

    try:
        # Check MX records
        answers = dns.resolver.resolve(domain, 'MX', lifetime=4.0)
        if answers and len(answers) > 0:
            _DOMAIN_MX_CACHE[domain] = True
            return True
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        # Fallback: check if domain has an A record (can accept mail in older RFCs)
        try:
            a_record = dns.resolver.resolve(domain, 'A', lifetime=3.0)
            if a_record and len(a_record) > 0:
                _DOMAIN_MX_CACHE[domain] = True
                return True
        except Exception:
            pass
    except Exception:
        # DNS timeout or connection error
        pass

    _DOMAIN_MX_CACHE[domain] = False
    return False


def verify_email(email: str) -> tuple[bool, str]:
    """
    Full verification suite for a recipient email address.
    Returns (is_valid: bool, reason: str)
    """
    clean_email = email.strip().lower()

    # 1. Syntax check
    if not check_syntax(clean_email):
        return False, "Invalid email syntax"

    try:
        user_part, domain_part = clean_email.split("@", 1)
    except ValueError:
        return False, "Missing @ or invalid structure"

    # 2. System / Spam trap username check
    if user_part in SYSTEM_USERNAMES:
        return False, f"System/Trap username: {user_part}"

    # 3. Disposable domain check
    if domain_part in DISPOSABLE_DOMAINS:
        return False, f"Disposable or test domain: {domain_part}"

    # 4. Top-level domain (TLD) length
    tld = domain_part.split(".")[-1]
    if len(tld) < 2:
        return False, f"Invalid TLD: .{tld}"

    # 5. Live DNS MX Record check
    has_mx = check_domain_mx(domain_part)
    if not has_mx:
        return False, f"Domain '{domain_part}' has no active Mail (MX) server (will bounce)"

    return True, "Email syntax & DNS MX records verified"
