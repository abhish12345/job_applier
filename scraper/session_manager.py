"""
scraper/session_manager.py
Cookie-based LinkedIn authentication with FULL human-like behavior.
Maximum stealth — LinkedIn cannot distinguish from real user.
"""

import json
import os
import time
import random
import sys
from playwright.sync_api import sync_playwright, BrowserContext, Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config  # Used for HEADLESS setting

COOKIE_FILE = os.path.join(os.path.dirname(__file__), "..", "session", "cookies.json")
SESSION_DIR  = os.path.join(os.path.dirname(__file__), "..", "session")

# ── Realistic Chrome versions to rotate ───────────────────────────────────────
CHROME_VERSIONS = [
    "120.0.0.0", "121.0.0.0", "122.0.0.0",
    "123.0.0.0", "124.0.0.0", "125.0.0.0",
]

# ── Realistic screen resolutions ──────────────────────────────────────────────
VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
    {"width": 1920, "height": 1080},
]


def get_random_user_agent() -> str:
    """Return a randomized but realistic Chrome user agent string"""
    version = random.choice(CHROME_VERSIONS)
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{version} Safari/537.36"
    )


def get_random_viewport() -> dict:
    """Return a random realistic viewport"""
    return random.choice(VIEWPORTS)


# ── JS patches injected into every page ───────────────────────────────────────
STEALTH_JS = """
// 1. Hide webdriver flag (most important)
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
});

// 2. Realistic plugins list (empty = headless browser)
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin',     filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer',     filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        { name: 'Native Client',         filename: 'internal-nacl-plugin' },
    ],
    configurable: true
});

// 3. Realistic languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en', 'hi'],
    configurable: true
});

// 4. Proper hardware concurrency (real CPUs)
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
    configurable: true
});

// 5. Realistic device memory
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
    configurable: true
});

// 6. Hide automation in chrome object
if (window.chrome) {
    window.chrome.runtime = window.chrome.runtime || {};
}

// 7. Realistic permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
);

// 8. Hide headless in user agent data
if (navigator.userAgentData) {
    Object.defineProperty(navigator, 'userAgentData', {
        get: () => ({
            brands: [
                { brand: 'Google Chrome',   version: '120' },
                { brand: 'Chromium',        version: '120' },
                { brand: 'Not=A?Brand',     version: '24'  },
            ],
            mobile: false,
            platform: 'Windows',
        }),
        configurable: true
    });
}

// 9. Realistic WebGL vendor/renderer
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};
"""


def ensure_session_dir():
    os.makedirs(SESSION_DIR, exist_ok=True)


def save_cookies(context: BrowserContext):
    """Save browser cookies to file"""
    ensure_session_dir()
    cookies = context.cookies()
    with open(COOKIE_FILE, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"[Session] ✅ Cookies saved → {COOKIE_FILE}")


def load_cookies(context: BrowserContext) -> bool:
    """Load cookies from file. Returns True if loaded."""
    if not os.path.exists(COOKIE_FILE):
        return False
    with open(COOKIE_FILE, "r") as f:
        cookies = json.load(f)
    context.add_cookies(cookies)
    print("[Session] ✅ Cookies loaded from saved session")
    return True


def is_logged_in(page: Page) -> bool:
    """Check if LinkedIn session is active"""
    try:
        page.goto("https://www.linkedin.com/feed/", timeout=20000)
        _human_pause(2, 4)
        return "feed" in page.url or "mynetwork" in page.url
    except Exception:
        return False


def _human_pause(min_s: float = 1.0, max_s: float = 3.0):
    """Random pause to mimic human thinking time"""
    time.sleep(random.uniform(min_s, max_s))


def _build_login_context(playwright):
    """
    Browser context for MANUAL LOGIN only.
    Uses real Chrome (channel='chrome') — LinkedIn cannot detect this as a bot.
    Falls back to Chromium if Chrome is not installed.
    NO tracker blocking — blocking breaks LinkedIn's login flow.
    """
    ua = get_random_user_agent()
    vp = get_random_viewport()

    common_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--start-maximized",
    ]

    # ── Try real Chrome first (least detectable) ──────────────
    try:
        browser = playwright.chromium.launch(
            channel="chrome",     # Uses YOUR installed Chrome — not Playwright Chromium
            headless=False,
            args=common_args,
        )
        print("[Session] Using real Chrome browser for login (most trusted by LinkedIn)")
    except Exception:
        # Chrome not installed — fall back to Chromium
        browser = playwright.chromium.launch(
            headless=False,
            args=common_args,
        )
        print("[Session] Chrome not found — using Chromium (may require extra verification)")

    context = browser.new_context(
        user_agent=ua,
        viewport=vp,
        locale="en-US",
        timezone_id="Asia/Kolkata",
        color_scheme="light",
    )
    context.add_init_script(STEALTH_JS)
    return browser, context


def _build_scrape_context(playwright):
    """
    Browser context for SCRAPING.
    Uses real Chrome channel with default UA and viewport so cookies are never rejected.
    """
    common_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--start-maximized",
    ]

    try:
        browser = playwright.chromium.launch(
            channel="chrome",
            headless=Config.HEADLESS,
            args=common_args,
        )
    except Exception:
        browser = playwright.chromium.launch(
            headless=Config.HEADLESS,
            args=common_args,
        )

    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="en-US",
    )
    # Stealth JS injected on every page
    context.add_init_script(STEALTH_JS)

    return browser, context


def manual_login(page: Page, context: BrowserContext):
    """
    Opens LinkedIn login in Playwright browser.
    Simple polling loop — checks URL every 2 seconds.
    No threading (Playwright sync API is not thread-safe).
    """
    print("\n" + "=" * 60)
    print("🔐  FIRST TIME SETUP — MANUAL LOGIN REQUIRED")
    print("=" * 60)
    print("  ⚠️  A NEW browser window has opened (separate from your Chrome)")
    print("  ⚠️  Switch to THAT window and login there")
    print("")
    print("  Steps in the Playwright browser:")
    print("    1. Enter your LinkedIn email & password")
    print("    2. Click 'Sign in'")
    print("    3. Complete CAPTCHA / OTP / verification if asked")
    print("    4. WAIT until you see your LinkedIn FEED")
    print("")
    print("  This terminal will auto-detect when you are logged in.")
    print("=" * 60 + "\n")

    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
    _human_pause(1, 2)

    # ── Inject a BIG RED BANNER so user knows this is the right window ─
    try:
        page.evaluate("""
            const banner = document.createElement('div');
            banner.id = 'playwright-banner';
            banner.style.cssText = `
                position: fixed;
                top: 0; left: 0;
                width: 100%;
                background: #cc0000;
                color: white;
                font-size: 18px;
                font-weight: bold;
                text-align: center;
                padding: 14px;
                z-index: 999999;
                letter-spacing: 0.5px;
                box-shadow: 0 3px 10px rgba(0,0,0,0.4);
            `;
            banner.textContent = '⚠️  LOGIN HERE — This is the AUTOMATED BROWSER (not your regular Chrome)  ⚠️';
            document.body.prepend(banner);
            document.body.style.marginTop = '55px';
        """)
    except Exception:
        pass

    # Bring the Playwright browser to front
    try:
        page.bring_to_front()
    except Exception:
        pass

    print("[Session] Checking every 2 seconds for login...")
    print("[Session] (Waiting — do NOT press anything here yet)\n")

    # ── Simple polling loop — no threading ────────────────────
    LOGGED_IN_PATTERNS = ["/feed", "/mynetwork", "/home", "/checkpoint",
                          "/challenge", "/uas/oauth"]
    max_wait = 300    # 5 minutes
    interval = 2
    elapsed  = 0
    last_url = ""

    while elapsed < max_wait:
        time.sleep(interval)
        elapsed += interval

        try:
            current_url = page.url
        except Exception:
            # Page closed or crashed
            break

        # Show URL change so user knows script is working
        if current_url != last_url:
            print(f"[Session] URL changed → {current_url[:80]}")
            last_url = current_url

        # Check if logged in (on feed or any post-login page)
        if any(p in current_url for p in LOGGED_IN_PATTERNS):
            # Handle checkpoint / OTP pages
            if "/checkpoint" in current_url or "/challenge" in current_url:
                print("\n[Session] ⚠️  LinkedIn needs verification/OTP.")
                print("[Session]    Complete it in the browser window.")
                print("[Session]    Press ENTER here AFTER you see the LinkedIn feed.\n")
                input("[Session] ▶ Press ENTER when on LinkedIn feed → ")
                _human_pause(2, 3)
                current_url = page.url

            if any(p in current_url for p in ["/feed", "/mynetwork", "/home"]):
                print(f"\n[Session] ✅ Login detected!")
                _human_pause(1, 2)
                save_cookies(context)
                print("[Session] ✅ Session saved — future runs are fully automatic!")
                return

        # Show progress dot every 10 seconds
        if elapsed % 10 == 0:
            print(f"[Session] Still waiting... {elapsed}s | Current URL: {page.url[:60]}")

    # ── Timeout fallback — ask user to confirm manually ───────
    print("\n[Session] Auto-detect timed out after 5 minutes.")
    print("[Session] If you are now on your LinkedIn feed, press ENTER.")
    print("[Session] The script will verify and save the session.\n")
    input("[Session] ▶ Press ENTER when you are on LinkedIn feed → ")

    _human_pause(1, 2)

    # Navigate to feed explicitly to verify
    try:
        page.goto("https://www.linkedin.com/feed/",
                  timeout=15000, wait_until="domcontentloaded")
        _human_pause(2, 3)
    except Exception:
        pass

    if any(p in page.url for p in ["/feed", "/mynetwork", "/home"]):
        save_cookies(context)
        print("[Session] ✅ Session saved!")
        return

    print("[Session] ❌ Still not on feed. Please re-run the script and try again.")
    raise Exception("LinkedIn login could not be confirmed")


def get_authenticated_browser():
    """
    Main entry point.
    Returns (playwright, browser, context, page) — logged in & stealth-ready.

    Flow:
    - Saved cookies exist + valid  → use them (fully automatic, scrape context)
    - No cookies / expired         → open login browser, wait for manual login,
                                     save cookies, return scrape context
    """
    playwright = sync_playwright().start()

    # ── STEP 1: Try saved cookies with scrape context ─────────
    if os.path.exists(COOKIE_FILE):
        print("[Session] Found saved cookies — trying to restore session...")
        browser, context = _build_scrape_context(playwright)
        page = context.new_page()
        load_cookies(context)

        page.goto("https://www.linkedin.com/feed/", timeout=20000,
                  wait_until="domcontentloaded")
        _human_pause(2, 4)

        if any(x in page.url for x in ["/feed", "/mynetwork", "/home"]):
            print("[Session] ✅ Session restored via saved cookies!")
            return playwright, browser, context, page
        else:
            print("[Session] ⚠️  Cookies expired. Opening browser for re-login...")
            browser.close()
            os.remove(COOKIE_FILE)

    # ── STEP 2: Manual login with clean login context ─────────
    login_browser, login_context = _build_login_context(playwright)
    login_page = login_context.new_page()

    manual_login(login_page, login_context)

    # ── STEP 3: Close login browser, open scrape context ──────
    # Load freshly saved cookies into the stealth scrape context
    login_browser.close()

    print("[Session] Starting stealth scrape session...")
    scrape_browser, scrape_context = _build_scrape_context(playwright)
    scrape_page = scrape_context.new_page()
    load_cookies(scrape_context)

    # Verify scrape session works
    scrape_page.goto("https://www.linkedin.com/feed/", timeout=20000,
                     wait_until="domcontentloaded")
    _human_pause(2, 3)

    print("[Session] ✅ Stealth scrape session ready!")
    return playwright, scrape_browser, scrape_context, scrape_page
