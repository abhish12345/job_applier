"""
main.py - Master Pipeline Orchestrator
LinkedIn Post Scraper → Email Extractor → MongoDB Dedup → Ollama AI → SMTP Sender

Run: python main.py
"""

import sys
import os
import time
from datetime import datetime

# ── Setup path ─────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from database.mongo_handler import MongoHandler
from scraper.session_manager import get_authenticated_browser
from scraper.linkedin_scraper import run_scraper
from scraper.email_extractor import extract_emails_from_posts
from ai.ollama_handler import generate_email_body, generate_subject_line, check_ollama_status
from ai.relevance_filter import is_job_relevant
from mailer.email_verifier import verify_email
from mailer.smtp_handler import SMTPHandler


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════╗
║        LinkedIn AI Job Application Automator             ║
║        Scrape → Extract → Deduplicate → AI Email → Send  ║
╚══════════════════════════════════════════════════════════╝
    """)


def print_step(step: int, title: str):
    print(f"\n{'='*55}")
    print(f"  STEP {step}: {title}")
    print(f"{'='*55}")


def run_pipeline():
    """Main pipeline execution"""
    print_banner()
    start_time = datetime.now()

    # ── Validate Config ────────────────────────────────────
    print("[Init] Validating configuration...")
    try:
        Config.validate()
        Config.display()
    except ValueError as e:
        print(f"\n{e}")
        sys.exit(1)

    # ── Check Ollama Status ────────────────────────────────
    print("\n[Init] Checking Ollama status...")
    ollama_status = check_ollama_status()
    if ollama_status["running"]:
        print(f"[Init] ✅ Ollama running | Model '{Config.OLLAMA_MODEL}' available: {ollama_status['model_available']}")
        if not ollama_status["model_available"]:
            print(f"[Init] ⚠️  Available models: {ollama_status['available_models']}")
            print(f"[Init] ⚠️  Run: ollama pull {Config.OLLAMA_MODEL}")
    else:
        print("[Init] ⚠️  Ollama not running. Will use fallback email template.")

    # ── Connect to MongoDB ─────────────────────────────────
    print("\n[Init] Connecting to MongoDB...")
    db = MongoHandler()

    # ─────────────────────────────────────────────────────────
    # STEP 1: Scrape LinkedIn Posts
    # ─────────────────────────────────────────────────────────
    print_step(1, "SCRAPE LINKEDIN POSTS")

    playwright, browser, context, page = get_authenticated_browser()
    all_posts = []

    try:
        all_posts = run_scraper(page)
    finally:
        browser.close()
        playwright.stop()

    if not all_posts:
        print("\n[Pipeline] ⚠️  No posts scraped. Exiting.")
        db.close()
        return

    # Save posts to MongoDB
    new_posts = 0
    for post in all_posts:
        if db.save_post(post):
            new_posts += 1
    print(f"[Pipeline] 💾 Saved {new_posts} new posts to MongoDB ({len(all_posts) - new_posts} duplicates skipped)")

    # ─────────────────────────────────────────────────────────
    # STEP 2: Filter by Relevancy & Experience Level
    # ─────────────────────────────────────────────────────────
    print_step(2, "FILTER BY RELEVANCY & EXPERIENCE")
    print(f"[Filter] Target Keywords: {', '.join(Config.TARGET_ROLE_KEYWORDS[:5])}...")
    print(f"[Filter] Maximum Target Exp: <= {Config.MAX_TARGET_EXPERIENCE} years")

    relevant_posts = []
    skipped_count = 0

    for post in all_posts:
        text = post.get("post_text", "")
        is_rel, reason = is_job_relevant(text)
        if is_rel:
            relevant_posts.append(post)
        else:
            skipped_count += 1

    print(f"[Filter] 🎯 {len(relevant_posts)} relevant posts kept | {skipped_count} skipped (unrelated role or seniority too high)")

    if not relevant_posts:
        print("[Pipeline] ⚠️  No posts matched the relevancy and experience criteria.")
        db.close()
        return

    # ─────────────────────────────────────────────────────────
    # STEP 3: Extract Email Addresses
    # ─────────────────────────────────────────────────────────
    print_step(3, "EXTRACT EMAIL ADDRESSES")

    email_records = extract_emails_from_posts(relevant_posts)

    if not email_records:
        print("[Pipeline] ⚠️  No emails found in relevant posts.")
        db.close()
        return

    # Save emails to MongoDB (deduplication by unique index)
    new_emails = 0
    for record in email_records:
        if db.save_email(record):
            new_emails += 1
    print(f"[Pipeline] 💾 {new_emails} new emails saved | {len(email_records) - new_emails} already in DB")

    # ─────────────────────────────────────────────────────────
    # STEP 4: Filter via MongoDB (Cooldown Check)
    # ─────────────────────────────────────────────────────────
    print_step(4, f"COOLDOWN FILTER ({Config.EMAIL_COOLDOWN_DAYS} DAYS)")

    pending_emails = db.get_pending_emails()

    if not pending_emails:
        print(f"[Pipeline] ✅ All emails are on cooldown (mailed within last {Config.EMAIL_COOLDOWN_DAYS} days)")
        print("[Pipeline] Nothing to send today.")
        db.close()
        return

    # ─────────────────────────────────────────────────────────
    # STEP 5: Validate Email Addresses (DNS MX & Anti-Bounce Check)
    # ─────────────────────────────────────────────────────────
    print_step(5, "VERIFY RECIPIENT EMAILS (DNS & MX RECORDS)")

    verified_emails = []
    for record in pending_emails:
        target_email = record.get("email", "")
        is_valid, reason = verify_email(target_email)
        if is_valid:
            verified_emails.append(record)
            print(f"[Verifier] ✅ {target_email} -> Active Mail Server confirmed")
        else:
            print(f"[Verifier] ⚠️  Skipping {target_email}: {reason}")
            db.mark_email_invalid(target_email, reason)

    if not verified_emails:
        print("[Pipeline] ⚠️  No valid emails with active mail servers found. Stopping.")
        db.close()
        return

    # Respect daily max limit
    if len(verified_emails) > Config.MAX_EMAILS_PER_DAY:
        print(f"[Pipeline] ⚠️  {len(verified_emails)} emails verified, limiting to {Config.MAX_EMAILS_PER_DAY}/day")
        verified_emails = verified_emails[:Config.MAX_EMAILS_PER_DAY]

    print(f"[Pipeline] 🎯 {len(verified_emails)} verified emails ready to send")

    # ─────────────────────────────────────────────────────────
    # STEP 6: Generate AI Emails via Ollama
    # ─────────────────────────────────────────────────────────
    print_step(6, f"GENERATE EMAILS WITH OLLAMA ({Config.OLLAMA_MODEL.upper()})")

    email_queue = []
    for i, record in enumerate(verified_emails, 1):
        print(f"\n[Ollama] [{i}/{len(verified_emails)}] Generating email for: {record['email']}")

        post_text = record.get("post_text", "AI/ML job opportunity")
        company = record.get("company", "")

        body = generate_email_body(post_text, company)
        subject = generate_subject_line(post_text, company)

        email_queue.append({
            "email": record["email"],
            "subject": subject,
            "body": body,
            "post_url": record.get("post_url", ""),
            "company": company,
        })

        # Brief delay between Ollama calls
        if i < len(verified_emails):
            time.sleep(2)

    # ─────────────────────────────────────────────────────────
    # STEP 7: Send Emails via SMTP
    # ─────────────────────────────────────────────────────────
    print_step(7, "SEND EMAILS VIA SMTP")

    mailer = SMTPHandler()

    # Test connection first
    if not mailer.test_connection():
        print("[Pipeline] ❌ SMTP connection failed. Check your .env SMTP settings.")
        db.close()
        return

    results = mailer.send_batch(email_queue)

    # ─────────────────────────────────────────────────────────
    # STEP 8: Log Results to MongoDB
    # ─────────────────────────────────────────────────────────
    print_step(8, "LOG RESULTS TO MONGODB")

    for result in results:
        if result["status"] == "sent":
            # Find matching email queue item for body/subject
            matched = next((e for e in email_queue if e["email"] == result["email"]), {})
            db.log_sent_email(
                email=result["email"],
                subject=matched.get("subject", ""),
                body=matched.get("body", ""),
                post_url=result.get("post_url", ""),
                company=result.get("company", ""),
            )
        elif result["status"] == "failed":
            db.update_email_status(result["email"], "bounced")

    # ─────────────────────────────────────────────────────────
    # FINAL SUMMARY
    # ─────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).seconds
    stats = db.get_stats()

    print(f"""
╔══════════════════════════════════════════════════════════╗
║                   PIPELINE COMPLETE ✅                   ║
╠══════════════════════════════════════════════════════════╣
║  Posts Scraped Today    : {len(all_posts):<30}║
║  Emails Extracted       : {len(email_records):<30}║
║  Emails Sent Today      : {sum(1 for r in results if r['status']=='sent'):<30}║
║  Failed                 : {sum(1 for r in results if r['status']=='failed'):<30}║
╠══════════════════════════════════════════════════════════╣
║  ALL TIME STATS                                          ║
║  Total Posts in DB      : {stats['total_posts_scraped']:<30}║
║  Total Emails in DB     : {stats['total_emails_extracted']:<30}║
║  Total Sent             : {stats['total_sent']:<30}║
║  Replies Received       : {stats['replied']:<30}║
║  Reply Rate             : {stats['reply_rate']:<30}║
╠══════════════════════════════════════════════════════════╣
║  Time Taken             : {f"{elapsed}s":<30}║
╚══════════════════════════════════════════════════════════╝
    """)

    db.close()


if __name__ == "__main__":
    run_pipeline()
