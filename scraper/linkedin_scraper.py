"""
scraper/linkedin_scraper.py
LinkedIn hashtag post scraper with FULL human-like behaviour.
Every action mimics real user: mouse moves, natural scrolling,
random pauses, typo-style timing — undetectable by LinkedIn.
"""

import time
import random
import math
import urllib.parse
import re
import sys
import os
from datetime import datetime
from playwright.sync_api import Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config


# ─────────────────────────────────────────────────────────────────────────────
# HUMAN BEHAVIOUR HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def human_pause(min_s: float = 0.5, max_s: float = 2.0):
    """Random pause — simulates human thinking / reading time"""
    time.sleep(random.uniform(min_s, max_s))


def human_scroll(page: Page, direction: str = "down", intensity: str = "normal"):
    """
    Smooth, human-like scroll using small incremental steps.
    Intensity: 'slow' | 'normal' | 'fast'
    """
    scroll_map = {
        "slow":   (80,  150),
        "normal": (200, 400),
        "fast":   (400, 700),
    }
    step_min, step_max = scroll_map.get(intensity, (200, 400))

    # Scroll in 3-6 small steps with micro-pauses (like a real mouse wheel)
    steps = random.randint(3, 6)
    for _ in range(steps):
        scroll_amount = random.randint(step_min, step_max)
        if direction == "up":
            scroll_amount = -scroll_amount

        page.evaluate(f"window.scrollBy({{ top: {scroll_amount}, behavior: 'smooth' }})")
        time.sleep(random.uniform(0.08, 0.25))   # micro-pause between each step

    # Brief pause after full scroll — human reads content
    human_pause(0.8, 2.0)


def human_mouse_move(page: Page):
    """
    Move mouse in a natural curved path across the page.
    Prevents 'mouse never moved' detection.
    """
    vp = page.viewport_size or {"width": 1280, "height": 800}
    w, h = vp["width"], vp["height"]

    # Pick a random target on the page
    target_x = random.randint(100, w - 100)
    target_y = random.randint(100, h - 100)

    # Current position (simulate starting from center area)
    start_x = random.randint(w // 4, 3 * w // 4)
    start_y = random.randint(h // 4, 3 * h // 4)

    # Move in small curved steps (Bezier-like)
    steps = random.randint(8, 15)
    for i in range(steps):
        t = i / steps
        # Add slight curve via sine wave offset
        curve_x = start_x + (target_x - start_x) * t + math.sin(t * math.pi) * random.randint(-30, 30)
        curve_y = start_y + (target_y - start_y) * t

        page.mouse.move(curve_x, curve_y)
        time.sleep(random.uniform(0.01, 0.04))


def human_hover_post(page: Page, element):
    """Hover over a post element briefly — like a human reading it"""
    try:
        box = element.bounding_box()
        if box:
            x = box["x"] + random.randint(10, int(box["width"]) - 10)
            y = box["y"] + random.randint(5, min(50, int(box["height"]) - 5))
            page.mouse.move(x, y)
            human_pause(0.3, 1.2)   # read time simulation
    except Exception:
        pass


def human_click(page: Page, element):
    """
    Click an element like a human — hover first, slight delay, then click.
    Avoids robotic instant-click detection.
    """
    try:
        box = element.bounding_box()
        if box:
            # Move to element with slight offset from center
            x = box["x"] + box["width"]  / 2 + random.uniform(-5, 5)
            y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
            page.mouse.move(x, y)
            human_pause(0.2, 0.6)   # hover before clicking
            page.mouse.click(x, y)
            human_pause(0.3, 0.8)   # pause after click
    except Exception:
        element.click()


def random_idle_behaviour(page: Page):
    """
    Occasionally simulate idle human behaviour:
    random mouse wiggle, scroll up a bit, pause — looks very natural.
    """
    behaviour = random.choices(
        ["wiggle", "scroll_up", "idle", "nothing"],
        weights=[20, 15, 30, 35]
    )[0]

    if behaviour == "wiggle":
        human_mouse_move(page)
    elif behaviour == "scroll_up":
        # Scroll up a tiny bit then back down — humans do this
        page.evaluate("window.scrollBy({ top: -150, behavior: 'smooth' })")
        human_pause(0.5, 1.5)
        page.evaluate("window.scrollBy({ top: 200, behavior: 'smooth' })")
        human_pause(0.5, 1.0)
    elif behaviour == "idle":
        human_pause(1.5, 4.0)   # longer "reading" pause


# ─────────────────────────────────────────────────────────────────────────────
# URL BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_search_url(hashtag_query: str, date_filter: str) -> str:
    """Build LinkedIn content search URL for given hashtags and date filter"""
    filter_map = {
        "past-week":    '["past-week"]',
        "past-2-weeks": '["past-2-weeks"]',
        "past-month":   '["past-month"]',
    }
    date_param      = filter_map.get(date_filter, '["past-week"]')
    encoded_keywords = urllib.parse.quote(hashtag_query.strip())
    encoded_date    = urllib.parse.quote(date_param)

    # Use standard search results URL
    return (
        f"https://www.linkedin.com/search/results/content/"
        f"?keywords={encoded_keywords}"
        f"&origin=GLOBAL_SEARCH_HEADER"
        f"&datePosted={encoded_date}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST DATA EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

def expand_see_more(page: Page, post_element):
    """Click 'see more' / '…see more' if present to get full post text"""
    try:
        # Try finding buttons/spans that match 'see more'
        see_more_selectors = [
            "button.feed-shared-inline-show-more-text__see-more-less-toggle",
            "button[aria-label*='see more' i]",
            "button:has-text('see more')",
            "span:has-text('…see more')",
            "span:has-text('see more')",
            ".see-more",
            "button[data-tracking-control-name*='see_more']",
        ]
        for sel in see_more_selectors:
            btn = post_element.query_selector(sel)
            if btn:
                try:
                    btn.scroll_into_view_if_needed(timeout=2000)
                    btn.click(timeout=2000)
                    human_pause(0.5, 1.0)
                    return
                except Exception:
                    # Fallback to direct JS click
                    try:
                        post_element.evaluate(f"""(el) => {{
                            const b = el.querySelector("{sel}");
                            if (b) b.click();
                        }}""")
                        human_pause(0.4, 0.8)
                        return
                    except Exception:
                        pass
    except Exception:
        pass


def extract_post_data(page: Page, post_element) -> dict | None:
    """Extract all data from a single post element"""
    try:
        data = {
            "post_text": "",
            "poster_name": "",
            "poster_profile_url": "",
            "company": "",
            "post_url": "",
            "hashtags": [],
            "scraped_at": datetime.utcnow().isoformat(),
        }

        # ── Hover over post first (human behaviour) ───────────
        human_hover_post(page, post_element)

        # ── Expand 'see more' to get full text ────────────────
        expand_see_more(page, post_element)

        # ── Post text ─────────────────────────────────────────
        for selector in [
            "[data-test-id='main-feed-activity-card__commentary']",
            ".feed-shared-update-v2__description",
            ".update-components-text",
            ".feed-shared-inline-show-more-text",
            ".feed-shared-text",
            ".break-words",
            "div.update-components-update-v2__commentary",
            "span[dir='ltr']",
        ]:
            try:
                el = post_element.query_selector(selector)
                if el:
                    text_val = el.inner_text().strip()
                    # Filter out video player accessibility overlays
                    if len(text_val) > 15 and "subtitles" not in text_val.lower() and "descriptions off" not in text_val.lower():
                        data["post_text"] = text_val
                        break
            except Exception:
                continue

        if not data["post_text"]:
            # Fallback: get entire text of element if it has sufficient content
            try:
                raw_text = post_element.inner_text().strip()
                if len(raw_text) > 20:
                    lines = [line.strip() for line in raw_text.split("\n") if line.strip() and not any(skip in line.lower() for skip in ["subtitles", "descriptions off", "dialog", "playback"])]
                    cleaned = " ".join(lines)
                    if len(cleaned) > 15:
                        data["post_text"] = cleaned
            except Exception:
                pass

        if not data["post_text"] or len(data["post_text"]) < 8:
            return None

        # ── Poster name ───────────────────────────────────────
        for selector in [
            ".update-components-actor__name",
            ".feed-shared-actor__name",
            ".app-aware-link span[aria-hidden='true']",
            "a[href*='/in/']",
        ]:
            try:
                el = post_element.query_selector(selector)
                if el:
                    name_candidate = el.inner_text().strip()
                    if name_candidate and len(name_candidate) < 60:
                        data["poster_name"] = name_candidate
                        break
            except Exception:
                continue

        # ── Poster profile URL ────────────────────────────────
        for selector in [
            ".update-components-actor__meta a",
            ".feed-shared-actor__container a",
        ]:
            try:
                el = post_element.query_selector(selector)
                if el:
                    href = el.get_attribute("href")
                    if href and "/in/" in href:
                        data["poster_profile_url"] = href.split("?")[0]
                        break
            except Exception:
                continue

        # ── Company / subtitle ────────────────────────────────
        for selector in [
            ".update-components-actor__description",
            ".feed-shared-actor__description",
        ]:
            try:
                el = post_element.query_selector(selector)
                if el:
                    data["company"] = el.inner_text().strip()[:100]
                    break
            except Exception:
                continue

        # ── Post URL ──────────────────────────────────────────
        for selector in [
            "a.app-aware-link[href*='/posts/']",
            "a[href*='ugcPost']",
            "a[href*='/feed/update/']",
        ]:
            try:
                el = post_element.query_selector(selector)
                if el:
                    href = el.get_attribute("href")
                    if href:
                        data["post_url"] = href.split("?")[0]
                        break
            except Exception:
                continue

        # ── Hashtags from text ────────────────────────────────
        data["hashtags"] = re.findall(r"#\w+", data["post_text"])

        return data

    except Exception as e:
        print(f"[Scraper] ⚠️  Post extraction error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCRAPER
# ─────────────────────────────────────────────────────────────────────────────

def _navigate_like_human(page: Page, url: str):
    """
    Navigate to URL with human-like pre/post behaviour.
    Avoids robotic instant navigation pattern.
    """
    # Occasionally move mouse before navigating
    if random.random() > 0.5:
        human_mouse_move(page)
        human_pause(0.3, 0.8)

    page.goto(url, timeout=30000, wait_until="domcontentloaded")

    # Simulate page load reading time
    human_pause(2.5, 5.0)

    # Initial mouse movement after page load
    human_mouse_move(page)
    human_pause(1.0, 2.5)


def scrape_posts_for_hashtag(page: Page, hashtag_query: str) -> list[dict]:
    """
    Scrape LinkedIn posts for a search query (hashtag or plain text keywords) with full human behaviour.
    Uses robust action-bar anchoring that works across modern LinkedIn layouts.
    """
    date_filter = Config.get_linkedin_date_filter()
    url = build_search_url(hashtag_query, date_filter)

    print(f"\n[Scraper] 🔍 Search Query: '{hashtag_query}' | Last {Config.LINKEDIN_SCRAPE_DAYS} days")

    _navigate_like_human(page, url)

    posts_data    = []
    seen_keys     = set()
    scroll_count  = 0
    max_scrolls   = (Config.MAX_POSTS_PER_SEARCH // 5) + 8
    no_new_streak = 0

    while len(posts_data) < Config.MAX_POSTS_PER_SEARCH and scroll_count < max_scrolls:

        # ── 1. Automatically click all '...more' buttons on screen ───────
        try:
            page.evaluate("""() => {
                const moreButtons = Array.from(document.querySelectorAll("button"))
                    .filter(b => b.innerText && (b.innerText.includes("more") || b.innerText.includes("…")));
                moreButtons.forEach(btn => {
                    try { btn.click(); } catch(e) {}
                });
            }""")
            human_pause(0.5, 1.0)
        except Exception:
            pass

        # ── 2. Extract cards anchored to the Like/Action bar ───────────
        try:
            extracted_batch = page.evaluate("""() => {
                const likeBtns = Array.from(document.querySelectorAll("button"))
                    .filter(b => b.innerText && b.innerText.trim() === "Like");

                return likeBtns.map(btn => {
                    let p = btn;
                    for (let i = 0; i < 20; i++) {
                        if (!p || !p.parentElement || p.parentElement.tagName === "BODY" || p.parentElement.id === "root") break;
                        const countLikes = p.parentElement.querySelectorAll("button").length;
                        const txt = p.parentElement.innerText || "";
                        if (countLikes > 15 || txt.length > 5000) break;
                        p = p.parentElement;
                    }
                    const link = p.querySelector("a[href*='/in/']");
                    const postLink = p.querySelector("a[href*='/feed/update/'], a[href*='/posts/'], a[href*='activity']");
                    return {
                        name: link ? link.innerText.trim() : "Recruiter",
                        profile_url: link ? link.href.split("?")[0] : "",
                        post_url: postLink ? postLink.href.split("?")[0] : "",
                        text: p.innerText || ""
                    };
                });
            }""")
        except Exception as e:
            extracted_batch = []

        before_count = len(posts_data)

        for raw_item in extracted_batch:
            raw_text = raw_item.get("text", "").strip()
            if not raw_text or len(raw_text) < 15:
                continue

            # Remove navigation/accessibility noise from text
            lines = [
                line.strip() for line in raw_text.split("\n")
                if line.strip() and not any(skip in line.lower() for skip in [
                    "subtitles", "descriptions off", "dialog", "playback", "feed post"
                ])
            ]
            clean_text = "\n".join(lines)

            # Deduplication key
            key = raw_item.get("post_url") or clean_text[:100]
            if key in seen_keys:
                continue
            seen_keys.add(key)

            post_record = {
                "post_text": clean_text,
                "poster_name": raw_item.get("name") or "Recruiter",
                "poster_profile_url": raw_item.get("profile_url") or "",
                "company": "",
                "post_url": raw_item.get("post_url") or "",
                "hashtags": re.findall(r"#\w+", clean_text),
                "scraped_at": datetime.utcnow().isoformat(),
            }
            posts_data.append(post_record)

            display_preview = clean_text[:70].replace('\n', ' ')
            print(f"[Scraper] 📌 Post #{len(posts_data)} collected: {post_record['poster_name']} - '{display_preview}...'")

            if len(posts_data) >= Config.MAX_POSTS_PER_SEARCH:
                break

        # ── Check if new posts were found ─────────────────────
        if len(posts_data) == before_count:
            no_new_streak += 1
            if no_new_streak >= 5:
                print("[Scraper] No new posts after several scrolls — stopping.")
                break
        else:
            no_new_streak = 0

        print(f"[Scraper] 📄 Total collected so far: {len(posts_data)} posts")

        # ── Check 'no results' indicator ──────────────────────
        if page.query_selector(".search-no-results__image"):
            print("[Scraper] LinkedIn says: no more results.")
            break

        # ── Human-like scroll down with wait ───────────────────
        print("[Scraper] ⏳ Scrolling down to load more posts...")
        human_scroll(page, direction="down", intensity="normal")
        page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 1.5))")

        wait_time = random.uniform(3.0, 5.0)
        time.sleep(wait_time)

        if random.random() < 0.3:
            random_idle_behaviour(page)

        scroll_count += 1

    print(f"[Scraper] ✅ '{hashtag_query}' → {len(posts_data)} posts scraped")
    return posts_data


def run_scraper(page: Page) -> list[dict]:
    """
    Master scraper: iterates all configured hashtags.
    Returns globally deduplicated list of all posts.
    """
    all_posts = []
    all_keys  = set()

    for i, hashtag_query in enumerate(Config.LINKEDIN_HASHTAGS):
        posts = scrape_posts_for_hashtag(page, hashtag_query)

        for post in posts:
            key = post.get("post_url") or post["post_text"][:100]
            if key not in all_keys:
                all_keys.add(key)
                all_posts.append(post)

        # Human-like gap between different searches
        if i < len(Config.LINKEDIN_HASHTAGS) - 1:
            gap = random.uniform(8.0, 18.0)
            print(f"\n[Scraper] ⏳ Waiting {gap:.1f}s before next hashtag (human behaviour)...")
            # Simulate browsing during wait — small random scrolls
            for _ in range(random.randint(1, 3)):
                human_scroll(page, intensity="slow")
                human_pause(1.0, 3.0)
            remaining = gap - 5
            if remaining > 0:
                time.sleep(remaining)

    print(f"\n[Scraper] 🎯 Total unique posts: {len(all_posts)}")
    return all_posts
