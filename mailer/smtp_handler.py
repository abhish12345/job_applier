"""
mailer/smtp_handler.py
Anti-spam SMTP email sender.
Proper headers, multipart plain+HTML, rate limiting, human-like send delays.
"""

import smtplib
import time
import random
import os
import sys
import uuid
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr, formatdate, make_msgid

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config


# ─────────────────────────────────────────────────────────────────────────────
# STATIC SIGNATURE BUILDER (config-based, appended to every email)
# ─────────────────────────────────────────────────────────────────────────────
def build_signature() -> str:
    """
    Build a clean, attractive, professional email signature from .env config.
    Always appended to every email body — name, role, email & mobile are fixed.
    """
    lines = [
        "",
        "Best regards,",
        Config.YOUR_NAME,
        Config.YOUR_ROLE,
        f"Mobile: {Config.YOUR_MOBILE}",
        f"Email: {Config.SMTP_EMAIL}",
    ]

    # Optional fields — only added if set in .env
    if Config.YOUR_LINKEDIN:
        lines.append(f"LinkedIn: {Config.YOUR_LINKEDIN}")
    if Config.YOUR_GITHUB:
        lines.append(f"GitHub: {Config.YOUR_GITHUB}")
    if Config.YOUR_PORTFOLIO:
        lines.append(f"Portfolio: {Config.YOUR_PORTFOLIO}")

    return "\n".join(lines)


def attach_signature(body: str) -> str:
    """
    Attach static signature to email body.
    Strips any signature the AI may have written, then appends the real one.
    """
    import re
    # Remove any signature AI may have added (after "Best regards" / "Thanks" etc.)
    body = re.split(
        r'\n(?:Best regards?|Thanks?|Regards?|Warm regards?|Cheers?|Sincerely)[,\s]*\n',
        body,
        flags=re.IGNORECASE
    )[0].rstrip()

    # Also strip if AI wrote a "--" separator already
    body = re.split(r'\n--\n', body)[0].rstrip()

    return body + "\n" + build_signature()


# ─────────────────────────────────────────────────────────────────────────────
# PLAIN TEXT → HTML CONVERTER
# ─────────────────────────────────────────────────────────────────────────────
def _text_to_html(plain_text: str) -> str:
    """
    Convert plain text email body to clean, minimal HTML.
    Spam filters prefer emails that have BOTH plain text AND HTML parts.
    Minimal HTML = lower spam score (no flashy styling).
    """
    # Escape HTML special chars
    safe = plain_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Convert newlines to <br> and wrap paragraphs
    paragraphs = safe.strip().split("\n\n")
    html_parts = []
    for para in paragraphs:
        lines = para.replace("\n", "<br>")
        html_parts.append(f"<p>{lines}</p>")

    body_html = "\n".join(html_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; font-size: 15px; color: #222; max-width: 600px; margin: 0 auto; padding: 20px;">
  {body_html}
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# SMTP HANDLER
# ─────────────────────────────────────────────────────────────────────────────
class SMTPHandler:
    def __init__(self):
        self.smtp_host  = Config.SMTP_HOST
        self.smtp_port  = Config.SMTP_PORT
        self.email      = Config.SMTP_EMAIL
        self.password   = Config.SMTP_PASSWORD
        self.resume_path = Config.RESUME_PATH
        self._sent_count = 0

    def _connect(self) -> smtplib.SMTP:
        """Authenticated SMTP connection"""
        server = smtplib.SMTP(self.smtp_host, self.smtp_port)
        server.ehlo()
        server.starttls()
        server.ehlo()   # Re-identify after STARTTLS (important!)
        server.login(self.email, self.password)
        return server

    def _build_message(self, to_email: str, subject: str, body_plain: str) -> MIMEMultipart:
        """
        Build a properly structured anti-spam email:
        - multipart/mixed  (top level, has attachment)
          └── multipart/alternative  (text vs html)
                ├── text/plain   (for spam filters & text clients)
                └── text/html    (for visual email clients)
          └── application/pdf  (resume attachment)
        """
        # ── Outer container (mixed = body + attachment) ───────
        msg = MIMEMultipart("mixed")

        # ── Standard email headers ─────────────────────────────
        msg["From"]       = formataddr((Config.YOUR_NAME, self.email))
        msg["To"]         = to_email
        msg["Subject"]    = subject
        msg["Date"]       = formatdate(localtime=True)

        # MIME-Version
        msg["MIME-Version"] = "1.0"

        # ── Alternative part (plain + html) ───────────────────
        alt_part = MIMEMultipart("alternative")

        # Plain text FIRST (spam filters read this)
        alt_part.attach(MIMEText(body_plain, "plain", "utf-8"))

        # HTML SECOND (email clients render this)
        body_html = _text_to_html(body_plain)
        alt_part.attach(MIMEText(body_html, "html", "utf-8"))

        msg.attach(alt_part)

        # ── Resume attachment ─────────────────────────────────
        if os.path.exists(self.resume_path):
            with open(self.resume_path, "rb") as f:
                pdf_data = f.read()
            resume_name = os.path.basename(self.resume_path)
            attachment = MIMEApplication(pdf_data, _subtype="pdf")
            attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=resume_name
            )
            msg.attach(attachment)
            print(f"[Mailer] Resume attached: {resume_name}")
        else:
            print(f"[Mailer] Resume not found at '{self.resume_path}' — sending without attachment")

        return msg

    def _human_send_delay(self):
        """
        Random delay between emails — mimics human sending behavior.
        Varies around the configured base delay so pattern isn't fixed.
        """
        base  = Config.DELAY_BETWEEN_EMAILS
        jitter = random.uniform(-base * 0.2, base * 0.4)
        delay = max(30, base + jitter)
        print(f"[Mailer] Waiting {delay:.0f}s before next email...")
        time.sleep(delay)

    # ─────────────────────────────────────────────────────────
    # SEND SINGLE EMAIL
    # ─────────────────────────────────────────────────────────
    def send_email(self, to_email: str, subject: str, body: str) -> dict:
        """
        Send a single email with proper anti-spam structure.
        Returns result dict with status and error info.
        """
        result = {
            "email":   to_email,
            "subject": subject,
            "status":  "failed",
            "error":   None,
        }

        # Daily limit guard
        if self._sent_count >= Config.MAX_EMAILS_PER_DAY:
            result["error"] = f"Daily limit reached ({Config.MAX_EMAILS_PER_DAY})"
            print(f"[Mailer] Daily limit of {Config.MAX_EMAILS_PER_DAY} reached. Stopping.")
            return result

        try:
            # Always attach static signature (strips AI-written one, adds real one)
            body_with_sig = attach_signature(body)
            msg    = self._build_message(to_email, subject, body_with_sig)
            server = self._connect()
            server.sendmail(self.email, [to_email], msg.as_bytes())
            server.quit()

            self._sent_count += 1
            result["status"] = "sent"
            print(f"[Mailer] Sent to {to_email} ({self._sent_count}/{Config.MAX_EMAILS_PER_DAY})")

        except smtplib.SMTPRecipientsRefused:
            result["error"] = "Recipient refused — likely invalid email"
            print(f"[Mailer] Invalid address: {to_email}")

        except smtplib.SMTPAuthenticationError:
            result["error"] = "SMTP auth failed — check SMTP_EMAIL and SMTP_PASSWORD in .env"
            print("[Mailer] SMTP auth failed. Check .env credentials.")

        except smtplib.SMTPException as e:
            result["error"] = str(e)
            print(f"[Mailer] SMTP error for {to_email}: {e}")

        except Exception as e:
            result["error"] = str(e)
            print(f"[Mailer] Unexpected error: {e}")

        return result

    # ─────────────────────────────────────────────────────────
    # SEND BATCH
    # ─────────────────────────────────────────────────────────
    def send_batch(self, email_list: list[dict]) -> list[dict]:
        """
        Send a batch of emails with human-like random delays.
        Input: list of {email, subject, body, post_url, company}
        Returns: list of result dicts
        """
        results = []
        total   = len(email_list)

        print(f"\n[Mailer] Starting batch — {total} emails")
        print(f"[Mailer] Base delay: {Config.DELAY_BETWEEN_EMAILS}s | Limit: {Config.MAX_EMAILS_PER_DAY}/day")

        for i, item in enumerate(email_list, 1):
            print(f"\n[Mailer] [{i}/{total}] → {item['email']}")

            result = self.send_email(
                to_email=item["email"],
                subject=item["subject"],
                body=item["body"],
            )
            result["post_url"] = item.get("post_url", "")
            result["company"]  = item.get("company", "")
            results.append(result)

            # Stop if daily limit hit
            err_msg = result.get("error") or ""
            if err_msg.startswith("Daily limit"):
                break

            # Human-like delay before next email
            if i < total:
                self._human_send_delay()

        sent   = sum(1 for r in results if r["status"] == "sent")
        failed = sum(1 for r in results if r["status"] == "failed")
        print(f"\n[Mailer] Done — {sent} sent, {failed} failed")
        return results

    # ─────────────────────────────────────────────────────────
    # CONNECTION TEST
    # ─────────────────────────────────────────────────────────
    def test_connection(self) -> bool:
        """Test SMTP connection before batch sending"""
        try:
            server = self._connect()
            server.quit()
            print("[Mailer] SMTP connection OK")
            return True
        except smtplib.SMTPAuthenticationError:
            print("[Mailer] SMTP auth failed — check SMTP_EMAIL and SMTP_PASSWORD in .env")
            return False
        except Exception as e:
            print(f"[Mailer] SMTP connection failed: {e}")
            return False
