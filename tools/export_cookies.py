"""
tools/export_cookies.py
─────────────────────────────────────────────────────────────
BACKUP LOGIN METHOD — Use this if the Playwright browser login fails.

How to use:
  1. Open your REGULAR Chrome browser
  2. Login to LinkedIn normally (linkedin.com)
  3. Make sure you can see your LinkedIn feed
  4. Run this script:
        python tools/export_cookies.py
  5. It will read LinkedIn cookies from Chrome and save them
  6. Then run: python main.py  (login will be skipped automatically!)
─────────────────────────────────────────────────────────────
"""

import json
import os
import sys
import sqlite3
import shutil
import tempfile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SESSION_DIR  = os.path.join(os.path.dirname(__file__), "..", "session")
COOKIE_FILE  = os.path.join(SESSION_DIR, "cookies.json")

# Chrome cookie DB path on Windows
CHROME_COOKIE_PATH = os.path.expandvars(
    r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies"
)
# Fallback older path
CHROME_COOKIE_PATH_OLD = os.path.expandvars(
    r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cookies"
)

LINKEDIN_DOMAIN = ".linkedin.com"


def find_chrome_cookie_db() -> str | None:
    """Find Chrome's cookie database file"""
    for path in [CHROME_COOKIE_PATH, CHROME_COOKIE_PATH_OLD]:
        if os.path.exists(path):
            return path
    return None


def read_chrome_cookies() -> list[dict]:
    """
    Read LinkedIn cookies from Chrome's SQLite cookie database.
    Copies DB to temp location first (Chrome may lock the file).
    Note: Chrome encrypts cookie values — we export what's readable.
    """
    db_path = find_chrome_cookie_db()
    if not db_path:
        print("❌ Chrome cookie database not found!")
        print("   Make sure Google Chrome is installed.")
        return []

    print(f"Found Chrome cookies at:\n  {db_path}\n")

    # Copy to temp (Chrome may have it locked)
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(db_path, tmp)

    cookies = []
    try:
        conn = sqlite3.connect(tmp)
        cursor = conn.cursor()

        # Query LinkedIn cookies
        cursor.execute("""
            SELECT host_key, name, path, is_secure, expires_utc, is_httponly
            FROM cookies
            WHERE host_key LIKE '%linkedin.com%'
        """)

        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            host, name, path, secure, expires, httponly = row
            cookies.append({
                "name":     name,
                "value":    "",          # Encrypted — will be overridden by Playwright
                "domain":   host,
                "path":     path,
                "secure":   bool(secure),
                "httpOnly": bool(httponly),
                "sameSite": "None",
            })

        print(f"Found {len(rows)} LinkedIn cookie entries in Chrome")

    except Exception as e:
        print(f"❌ Error reading cookies: {e}")
    finally:
        os.unlink(tmp)

    return cookies


def export_via_playwright() -> bool:
    """
    Better method: Open Playwright with real Chrome, you login once,
    cookies are captured automatically.
    This is the most reliable approach.
    """
    print("\n" + "=" * 55)
    print("COOKIE EXPORT VIA PLAYWRIGHT + REAL CHROME")
    print("=" * 55)
    print("This will open a Chrome window.")
    print("Login to LinkedIn, then come back here and press ENTER.")
    print("=" * 55 + "\n")

    try:
        from playwright.sync_api import sync_playwright
        import time

        os.makedirs(SESSION_DIR, exist_ok=True)

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    channel="chrome",
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled",
                          "--start-maximized"]
                )
                print("[✓] Using real Chrome")
            except Exception:
                browser = p.chromium.launch(headless=False)
                print("[!] Using Chromium (Chrome not found)")

            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="en-US",
            )
            page = context.new_page()
            page.goto("https://www.linkedin.com/login")

            # Inject banner
            try:
                page.evaluate("""
                    const b = document.createElement('div');
                    b.style.cssText = 'position:fixed;top:0;left:0;width:100%;background:#006400;color:white;font-size:18px;font-weight:bold;text-align:center;padding:12px;z-index:999999;';
                    b.textContent = '✅ LOGIN HERE — Cookie Export Tool — Login then press ENTER in terminal';
                    document.body.prepend(b);
                """)
            except Exception:
                pass

            print("\nBrowser opened. Login to LinkedIn in that window.")
            print("Once on your LinkedIn FEED, press ENTER here.\n")
            input("Press ENTER after you see your LinkedIn feed → ")

            # Save cookies
            cookies = context.cookies()
            linkedin_cookies = [c for c in cookies if "linkedin" in c.get("domain", "")]

            if not linkedin_cookies:
                print("❌ No LinkedIn cookies found. Make sure you logged in.")
                browser.close()
                return False

            with open(COOKIE_FILE, "w") as f:
                json.dump(linkedin_cookies, f, indent=2)

            browser.close()
            print(f"\n✅ {len(linkedin_cookies)} LinkedIn cookies saved to:")
            print(f"   {COOKIE_FILE}")
            print("\n✅ Now run: python main.py")
            print("   Login step will be skipped automatically!")
            return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 55)
    print("  LinkedIn Cookie Export Tool")
    print("  Backup login method for linkedin_scrapper")
    print("=" * 55)

    success = export_via_playwright()
    if not success:
        print("\n❌ Export failed. Please try running main.py directly.")
        sys.exit(1)
