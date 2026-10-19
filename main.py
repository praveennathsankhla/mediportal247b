import os
import re
import csv
import json
import time
import sys
import signal
import random
import argparse
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# UTF-8 output for Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


# ==========================================
# FILE PATHS & CONFIGURATION
# ==========================================
BASE_URL = "https://bollyflix.af/"
DATA_DIR = "data"
THUMBNAILS_DIR = os.path.join(DATA_DIR, "thumbnails")
CSV_FILE = os.path.join(DATA_DIR, "movies.csv")
JSON_FILE = os.path.join(DATA_DIR, "movies.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
ATTEMPTED_URLS_FILE = os.path.join(DATA_DIR, "attempted_urls.json")
PERSISTENCE_LOCK_FILE = os.path.join(DATA_DIR, "scraper.lock")

STOP_REQUESTED = False
PERSISTENCE_LOCK = threading.RLock()

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def sigint_handler(signum, frame):
    global STOP_REQUESTED
    if not STOP_REQUESTED:
        print("\n\n[!] Ctrl+C detected. Finishing current movie then stopping...")
        print("[!] State saved. Run again anytime to resume.")
        STOP_REQUESTED = True
    else:
        print("\n[!] Force exit.")
        sys.exit(0)


signal.signal(signal.SIGINT, sigint_handler)


@contextmanager
def persistence_file_lock():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PERSISTENCE_LOCK_FILE, "a+b") as lock_file:
        if os.name == "nt":
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            while True:
                lock_file.seek(0)
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def write_json_atomically(path: str, data: object, *, ensure_ascii: bool = True, indent: int = 4):
    temporary_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    replace_error = None
    try:
        with open(temporary_path, "w", encoding="utf-8") as output_file:
            json.dump(data, output_file, ensure_ascii=ensure_ascii, indent=indent)
            output_file.flush()
            os.fsync(output_file.fileno())
        for attempt in range(8):
            try:
                os.replace(temporary_path, path)
                return
            except PermissionError as error:
                replace_error = error
                if attempt == 7:
                    break
                time.sleep(min(0.1 * (2 ** attempt), 2.0))
        raise PermissionError(
            f"Could not replace {path} after 8 attempts because another process "
            f"has the file open. Temporary data was preserved at {temporary_path}."
        ) from replace_error
    except Exception:
        if os.path.exists(temporary_path):
            if replace_error is None:
                os.remove(temporary_path)
        raise


# ==========================================
# ANTI-DETECTION STEALTH CDP SCRIPT
# ==========================================
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
if (navigator.__proto__) { delete navigator.__proto__.webdriver; }
window.chrome = {
    app: { isInstalled: false },
    runtime: {},
    csi: function(){},
    loadTimes: function(){}
};
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbheakpkgapgdpbchnfheiajmtffo', description: '' },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
    ]
});
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
try {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel(R) UHD Graphics 630';
        return getParameter.apply(this, [parameter]);
    };
} catch(e) {}
"""


def sanitize_filename(name: str, max_len: int = 70) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:max_len]


def init_driver(headless: bool = True, browser_type: str = "chrome") -> webdriver.Remote:
    if browser_type == "chrome":
        options = ChromeOptions()
        options.page_load_strategy = "eager"
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        options.add_argument("--lang=en-US,en")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": STEALTH_JS})
    elif browser_type == "edge":
        options = EdgeOptions()
        options.page_load_strategy = "eager"
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Edge(options=options)
    elif browser_type == "firefox":
        options = FirefoxOptions()
        options.page_load_strategy = "eager"
        if headless:
            options.add_argument("-headless")
        driver = webdriver.Firefox(options=options)
    else:
        raise ValueError(f"Unsupported browser type: {browser_type}")

    driver.set_page_load_timeout(25)
    return driver


class BrowserSession:
    def __init__(self, headless: bool, browser_type: str = "chrome"):
        self.headless = headless
        self.browser_type = browser_type
        self.driver = init_driver(headless=headless, browser_type=browser_type)

    def __getattr__(self, name):
        return getattr(self.driver, name)

    def restart(self):
        try:
            self.driver.quit()
        except WebDriverException:
            pass
        self.driver = init_driver(headless=self.headless, browser_type=self.browser_type)

    def quit(self):
        try:
            self.driver.quit()
        except WebDriverException:
            pass


class HttpScraperSession:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def get_soup(self, page_url: str, retries: int = 3) -> BeautifulSoup:
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                response = self.session.get(page_url, timeout=(10, 25))
                response.raise_for_status()
                return BeautifulSoup(response.content, "html.parser")
            except requests.RequestException as error:
                last_error = error
                message = str(error).splitlines()[0]
                print(f"  [retry {attempt}/{retries}] HTTP page load failed: {message}")
                if attempt < retries:
                    time.sleep(min(attempt, 3))
        raise RuntimeError(
            f"Failed to fetch {page_url} after {retries} HTTP attempts: {last_error}"
        ) from last_error

    def close(self):
        self.session.close()


# ==========================================
# RESUME / STATE
# ==========================================
def load_state() -> dict:
    with persistence_file_lock():
        state = {"current_page": 1, "scraped_urls": [], "total_scraped": 0}
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    state.update(json.load(f))
            except Exception:
                pass
        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, "r", encoding="utf-8") as f:
                    for movie in json.load(f):
                        url = movie.get("url")
                        if url and url not in state["scraped_urls"]:
                            state["scraped_urls"].append(url)
                state["total_scraped"] = len(state["scraped_urls"])
            except Exception:
                pass
        return state


def save_state(state: dict):
    with PERSISTENCE_LOCK, persistence_file_lock():
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    saved_state = json.load(f)
                state["scraped_urls"] = sorted(
                    set(state.get("scraped_urls", [])) | set(saved_state.get("scraped_urls", []))
                )
                state["total_scraped"] = len(state["scraped_urls"])
            except (OSError, json.JSONDecodeError):
                pass
        state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        write_json_atomically(STATE_FILE, state)


# ==========================================
# PERSIST MOVIE RECORD IMMEDIATELY
# ==========================================
def append_movie_record(movie_data: dict):
    with PERSISTENCE_LOCK, persistence_file_lock():
        _append_movie_record(movie_data)


def _append_movie_record(movie_data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    # JSON
    all_movies = []
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                all_movies = json.load(f)
        except Exception:
            pass
    idx = next((i for i, m in enumerate(all_movies) if m.get("url") == movie_data["url"]), -1)
    if idx >= 0:
        all_movies[idx] = movie_data
    else:
        all_movies.append(movie_data)
    write_json_atomically(JSON_FILE, all_movies, ensure_ascii=False)

    # CSV (flat row)
    row = dict(movie_data)
    dl_summary = []
    for d in row.get("downloads", []):
        links_str = ", ".join([f"{l['label']}: {l['link']}" for l in d.get("links", [])])
        dl_summary.append(f"[{d['quality_tier']}] -> {links_str}")
    row["downloads_summary"] = " | ".join(dl_summary)
    row["post_screenshot_urls"] = ", ".join(row.get("post_screenshot_urls", []))
    row.pop("downloads", None)
    row.pop("raw_details", None)

    file_exists = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0
    with open(CSV_FILE, "a" if file_exists else "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def claim_movie_url(movie_url: str, scraped: set, in_progress: set) -> bool:
    with persistence_file_lock():
        if movie_url in scraped or movie_url in in_progress:
            return False

        attempted_urls = set()
        if os.path.exists(ATTEMPTED_URLS_FILE):
            with open(ATTEMPTED_URLS_FILE, "r", encoding="utf-8") as f:
                attempted_urls = set(json.load(f))
        if movie_url in attempted_urls:
            return False

        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                if any(movie.get("url") == movie_url for movie in json.load(f)):
                    scraped.add(movie_url)
                    return False

        attempted_urls.add(movie_url)
        write_json_atomically(ATTEMPTED_URLS_FILE, sorted(attempted_urls))
        in_progress.add(movie_url)
        return True


# ==========================================
# THUMBNAIL DOWNLOADER (2 strategies)
# ==========================================
def download_thumbnail(driver: webdriver.Remote, image_url: str, save_filename: str) -> str:
    """Try urllib first, fallback to Selenium element screenshot."""
    os.makedirs(THUMBNAILS_DIR, exist_ok=True)
    dest_path = os.path.join(THUMBNAILS_DIR, f"{save_filename}.jpg")

    # Strategy 1: Direct HTTP via urllib (fast, works for CDN images)
    if image_url:
        try:
            req = urllib.request.Request(
                image_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": BASE_URL
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            if len(data) > 500:
                with open(dest_path, "wb") as f:
                    f.write(data)
                return os.path.abspath(dest_path)
        except Exception:
            pass

    # Strategy 2: Screenshot the rendered img element in browser
    # Selenium requires .png extension — save as .png then rename to .jpg
    tmp_png = dest_path.replace(".jpg", "_tmp.png")
    try:
        selectors = [
            ".featured-thumbnail img",
            "img.wp-post-image",
            ".post-image img",
            ".single_post img"
        ]
        for sel in selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                try:
                    if el.is_displayed() and el.size["width"] > 50:
                        el.screenshot(tmp_png)
                        if os.path.exists(tmp_png) and os.path.getsize(tmp_png) > 500:
                            os.replace(tmp_png, dest_path)
                            return os.path.abspath(dest_path)
                except Exception:
                    continue
    except Exception:
        pass
    finally:
        if os.path.exists(tmp_png):
            try:
                os.remove(tmp_png)
            except Exception:
                pass

    return ""


# ==========================================
# SCRAPING LOGIC
# ==========================================
def get_page_movie_links(driver: BrowserSession, page_url: str, retries: int = 3) -> list:
    print(f"[PAGE] {page_url}")
    for attempt in range(1, retries + 1):
        try:
            driver.get(page_url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article.latestPost, .not-found"))
            )
            break
        except (TimeoutException, WebDriverException) as e:
            message = getattr(e, "msg", str(e)).splitlines()[0]
            print(f"  [retry {attempt}/{retries}] Page load failed: {message}")
            if attempt < retries:
                print("  [!] Restarting browser before retry.")
                driver.restart()
                time.sleep(min(attempt * 2, 4))
            else:
                raise WebDriverException(
                    f"Failed to load catalogue page {page_url} after {retries} attempts."
                ) from e

    posts = []
    for art in driver.find_elements(By.CSS_SELECTOR, "article.latestPost"):
        try:
            link_el = art.find_element(By.CSS_SELECTOR, "h2.title a")
            href = link_el.get_attribute("href")
            title = link_el.text.strip()
            thumb = ""
            imgs = art.find_elements(By.CSS_SELECTOR, ".featured-thumbnail img, .post-image img")
            if imgs:
                thumb = imgs[0].get_attribute("src") or ""
            if href:
                posts.append({"title": title, "url": href, "thumbnail": thumb})
        except Exception:
            continue
    print(f"  -> Found {len(posts)} posts.")
    return posts


def get_page_movie_links_http(session: HttpScraperSession, page_url: str) -> list[dict]:
    print(f"[PAGE] {page_url}")
    soup = session.get_soup(page_url)
    posts = []
    for article in soup.select("article.latestPost"):
        link = article.select_one("h2.title a")
        if not link or not link.get("href"):
            continue
        image = article.select_one(".featured-thumbnail img, .post-image img")
        posts.append({
            "title": link.get_text(" ", strip=True),
            "url": urljoin(page_url, link["href"]),
            "thumbnail": (
                image.get("data-src")
                or image.get("data-lazy-src")
                or image.get("src")
                if image else ""
            ),
        })
    print(f"  -> Found {len(posts)} posts.")
    return posts


def download_thumbnail_http(
    session: HttpScraperSession, image_url: str, save_filename: str
) -> str:
    if not image_url:
        return ""

    os.makedirs(THUMBNAILS_DIR, exist_ok=True)
    dest_path = os.path.join(THUMBNAILS_DIR, f"{save_filename}.jpg")
    try:
        response = session.session.get(
            image_url, headers={"Referer": BASE_URL}, timeout=(10, 20)
        )
        response.raise_for_status()
        if len(response.content) <= 500:
            return ""
        with open(dest_path, "wb") as image_file:
            image_file.write(response.content)
        return os.path.abspath(dest_path)
    except requests.RequestException as error:
        print(f"  [!] Thumbnail download failed: {error}")
        return ""


def scrape_movie_http(
    session: HttpScraperSession, movie_url: str, thumb_hint: str, count: int
) -> dict | None:
    print(f"\n[{count}] {movie_url}")
    soup = session.get_soup(movie_url)
    data = {
        "url": movie_url,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": "", "published_date": "",
        "imdb_rating": "", "imdb_url": "", "imdb_genres": "",
        "director": "", "writer": "", "stars": "", "summary": "",
        "full_name": "", "language": "", "released_year": "", "size": "",
        "quality": "", "source": "", "genres": "", "cast": "", "format": "",
        "subtitle": "", "storyline": "", "trailer_url": "",
        "post_screenshot_urls": [], "downloads": [],
        "thumbnail_url": "", "thumbnail_file": ""
    }

    title = soup.select_one("h1.entry-title, h1.single-title, h1")
    data["title"] = title.get_text(" ", strip=True) if title else (
        soup.title.get_text(" ", strip=True) if soup.title else ""
    )

    date = soup.select_one(".post-info .thetime, span.date")
    if date:
        data["published_date"] = date.get_text(" ", strip=True)

    element = soup.find(id="imdb_rating")
    if element:
        data["imdb_rating"] = element.get_text(" ", strip=True)
    element = soup.select_one("a[href*='imdb.com/title']")
    if element:
        data["imdb_url"] = element.get("href", "")
    element = soup.find(id="genres")
    if element:
        data["imdb_genres"] = element.get_text(" ", strip=True)
    for element in soup.select(".imdb_general span, span#imdb_general"):
        text = element.get_text(" ", strip=True)
        for label, key in (("Director:", "director"), ("Writer:", "writer"), ("Stars:", "stars")):
            if label in text:
                data[key] = text.replace(label, "", 1).strip()
    element = soup.find(id="summary")
    if element:
        data["summary"] = element.get_text(" ", strip=True).replace("Summary:", "", 1).strip()

    details = {}
    for item in soup.select(".thecontent ul li"):
        text = item.get_text(" ", strip=True)
        if ":" in text:
            key, value = text.split(":", 1)
            details[key.strip().lower().replace(" ", "_")] = value.strip()
    for key in (
        "full_name", "language", "released_year", "size", "quality",
        "source", "genres", "cast", "format", "subtitle"
    ):
        data[key] = details.get(key, "")
    data["raw_details"] = details

    for heading in soup.select(".thecontent h2"):
        if "storyline" in heading.get_text(" ", strip=True).lower():
            paragraph = heading.find_next_sibling("p")
            if paragraph:
                data["storyline"] = paragraph.get_text(" ", strip=True)
            break

    trailer = soup.select_one("iframe.responsive-iframe, iframe[src*='youtube']")
    if trailer:
        data["trailer_url"] = trailer.get("src", "")

    for image in soup.select(".thecontent p img"):
        src = image.get("src")
        if src and ("googleusercontent" in src or "vlcsnap" in src):
            data["post_screenshot_urls"].append(urljoin(movie_url, src))

    for heading in soup.select(".thecontent h5"):
        tier_title = heading.get_text(" ", strip=True)
        paragraph = heading.find_next_sibling("p")
        if not tier_title or not paragraph:
            continue
        links = []
        for anchor in paragraph.select("a[href]"):
            links.append({
                "label": anchor.get_text(" ", strip=True),
                "link": urljoin(movie_url, anchor["href"]),
            })
        if links:
            data["downloads"].append({"quality_tier": tier_title, "links": links})

    image_meta = soup.select_one("meta[property='og:image']")
    thumbnail_url = image_meta.get("content", "") if image_meta else thumb_hint
    if not thumbnail_url:
        image = soup.select_one(".featured-thumbnail img, img.wp-post-image")
        if image:
            thumbnail_url = (
                image.get("data-src")
                or image.get("data-lazy-src")
                or image.get("src", "")
            )
    data["thumbnail_url"] = urljoin(movie_url, thumbnail_url) if thumbnail_url else ""

    slug = f"{count:04d}_{sanitize_filename(data['title'] or f'movie_{count}')}"
    data["thumbnail_file"] = download_thumbnail_http(session, data["thumbnail_url"], slug)
    if data["thumbnail_file"]:
        print(f"  [+] Thumbnail: {os.path.basename(data['thumbnail_file'])}")
    print(f"  [+] Title   : {data['title'][:70]}")
    print(f"  [+] Quality : {data['quality']} | Size: {data['size']}")
    print(f"  [+] Downloads: {len(data['downloads'])} tiers")
    return data


def scrape_movie(driver: BrowserSession, movie_url: str, thumb_hint: str, count: int) -> dict:
    print(f"\n[{count}] {movie_url}")

    loaded = False
    for attempt in range(3):
        try:
            driver.get(movie_url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .thecontent"))
            )
            loaded = True
            break
        except (TimeoutException, WebDriverException) as e:
            message = getattr(e, "msg", str(e)).splitlines()[0]
            print(f"  [retry {attempt+1}/3] Movie page load failed: {message}")
            if attempt < 2:
                print("  [!] Restarting browser before retry.")
                driver.restart()
                time.sleep(min((attempt + 1) * 2, 4))

    if not loaded:
        print(f"  [SKIP] Failed to load.")
        return None

    time.sleep(random.uniform(0.8, 1.5))

    data = {
        "url": movie_url,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": "", "published_date": "",
        "imdb_rating": "", "imdb_url": "", "imdb_genres": "",
        "director": "", "writer": "", "stars": "", "summary": "",
        "full_name": "", "language": "", "released_year": "", "size": "",
        "quality": "", "source": "", "genres": "", "cast": "", "format": "",
        "subtitle": "", "storyline": "", "trailer_url": "",
        "post_screenshot_urls": [], "downloads": [],
        "thumbnail_url": "", "thumbnail_file": ""
    }

    # Title
    try:
        els = driver.find_elements(By.CSS_SELECTOR, "h1.entry-title, h1.single-title, h1")
        data["title"] = els[0].text.strip() if els else driver.title
    except Exception:
        data["title"] = driver.title

    # Date
    try:
        els = driver.find_elements(By.CSS_SELECTOR, ".post-info .thetime, span.date")
        if els:
            data["published_date"] = els[0].text.strip()
    except Exception:
        pass

    # IMDb box
    try:
        els = driver.find_elements(By.ID, "imdb_rating")
        if els:
            data["imdb_rating"] = els[0].text.strip()
        els = driver.find_elements(By.CSS_SELECTOR, "a[href*='imdb.com/title']")
        if els:
            data["imdb_url"] = els[0].get_attribute("href")
        els = driver.find_elements(By.ID, "genres")
        if els:
            data["imdb_genres"] = els[0].text.strip()
        for gen in driver.find_elements(By.CSS_SELECTOR, ".imdb_general span, span#imdb_general"):
            txt = gen.text.strip()
            if "Director:" in txt:
                data["director"] = txt.replace("Director:", "").strip()
            elif "Writer:" in txt:
                data["writer"] = txt.replace("Writer:", "").strip()
            elif "Stars:" in txt:
                data["stars"] = txt.replace("Stars:", "").strip()
        els = driver.find_elements(By.ID, "summary")
        if els:
            data["summary"] = els[0].text.replace("Summary:", "").strip()
    except Exception:
        pass

    # Details list
    details = {}
    try:
        for li in driver.find_elements(By.CSS_SELECTOR, ".thecontent ul li"):
            text = li.text.strip()
            if ":" in text:
                k, v = text.split(":", 1)
                details[k.strip().lower().replace(" ", "_")] = v.strip()
    except Exception:
        pass

    for key in ["full_name", "language", "released_year", "size", "quality",
                "source", "genres", "cast", "format", "subtitle"]:
        data[key] = details.get(key, "")
    data["raw_details"] = details

    # Storyline
    try:
        hs = driver.find_elements(By.XPATH, "//h2[contains(., 'Storyline')]")
        if hs:
            ps = hs[0].find_elements(By.XPATH, "following-sibling::p[1]")
            if ps:
                data["storyline"] = ps[0].text.strip()
    except Exception:
        pass

    # Trailer
    try:
        iframes = driver.find_elements(By.CSS_SELECTOR, "iframe.responsive-iframe, iframe[src*='youtube']")
        if iframes:
            data["trailer_url"] = iframes[0].get_attribute("src") or ""
    except Exception:
        pass

    # Post screenshot URLs (embedded sample images in the post body)
    try:
        for img in driver.find_elements(By.CSS_SELECTOR, ".thecontent p img"):
            src = img.get_attribute("src")
            if src and ("googleusercontent" in src or "vlcsnap" in src):
                data["post_screenshot_urls"].append(src)
    except Exception:
        pass

    # Download links
    try:
        for h5 in driver.find_elements(By.CSS_SELECTOR, ".thecontent h5"):
            tier_title = h5.text.strip()
            if not tier_title:
                continue
            try:
                p_el = h5.find_element(By.XPATH, "following-sibling::p[1]")
                links = []
                for a in p_el.find_elements(By.TAG_NAME, "a"):
                    href = a.get_attribute("href")
                    if href:
                        links.append({"label": a.text.strip(), "link": href})
                if links:
                    data["downloads"].append({"quality_tier": tier_title, "links": links})
            except Exception:
                pass
    except Exception:
        pass

    # Thumbnail URL detection
    thumb_url = thumb_hint
    try:
        og = driver.find_elements(By.CSS_SELECTOR, "meta[property='og:image']")
        if og and og[0].get_attribute("content"):
            thumb_url = og[0].get_attribute("content")
        elif not thumb_url:
            imgs = driver.find_elements(By.CSS_SELECTOR, ".featured-thumbnail img, img.wp-post-image")
            if imgs and imgs[0].get_attribute("src"):
                thumb_url = imgs[0].get_attribute("src")
    except Exception:
        pass

    data["thumbnail_url"] = thumb_url

    # Download thumbnail
    slug = f"{count:04d}_{sanitize_filename(data['title'] or f'movie_{count}')}"
    thumb_file = download_thumbnail(driver, thumb_url, slug)
    data["thumbnail_file"] = thumb_file
    if thumb_file:
        print(f"  [+] Thumbnail: {os.path.basename(thumb_file)}")
    else:
        print(f"  [-] Thumbnail: not available")

    print(f"  [+] Title   : {data['title'][:70]}")
    print(f"  [+] Quality : {data['quality']} | Size: {data['size']}")
    print(f"  [+] Downloads: {len(data['downloads'])} tiers")

    return data


# ==========================================
# MAIN
# ==========================================
def partition_page_range(
    start_page: int, end_page: int, workers: int, reverse: bool = False
) -> list[tuple[int, int]]:
    page_count = end_page - start_page + 1
    worker_count = min(workers, page_count)
    base_size, remainder = divmod(page_count, worker_count)
    ranges = []
    next_page = start_page
    for worker_index in range(worker_count):
        range_size = base_size + (1 if worker_index < remainder else 0)
        range_end = next_page + range_size - 1
        ranges.append((next_page, range_end))
        next_page = range_end + 1
    return list(reversed(ranges)) if reverse else ranges


def scrape_page_range(
    worker_id: int,
    transport: str,
    browser_type: str,
    start_page: int,
    end_page: int | None,
    reverse: bool,
    headless: bool,
    delay: float,
    limit: int | None,
    track_resume: bool,
    scraped: set,
    in_progress: set,
    state: dict,
    counters: dict,
):
    global STOP_REQUESTED

    driver = (
        HttpScraperSession()
        if transport == "http"
        else BrowserSession(headless=headless, browser_type=browser_type)
    )
    worker_name = f"HTTP worker {worker_id}" if transport == "http" else (
        f"Browser {worker_id} ({browser_type})"
    )
    print(f"[*] {worker_name} started for pages {start_page}..{end_page or '∞'}.")
    step = -1 if reverse else 1
    page_num = end_page if reverse else start_page

    try:
        while page_num is not None and not STOP_REQUESTED:
            page_url = BASE_URL if page_num == 1 else f"{BASE_URL}page/{page_num}/"
            print(f"\n{'='*65}\n[{worker_name}]")
            posts = (
                get_page_movie_links_http(driver, page_url)
                if transport == "http"
                else get_page_movie_links(driver, page_url)
            )
            if not posts:
                print(f"[{worker_name}] No posts found on page {page_num}; stopping this range.")
                break

            with PERSISTENCE_LOCK:
                new_on_page = [post for post in posts if post["url"] not in scraped]
            print(f"[*] {len(new_on_page)} new / {len(posts)} total on page {page_num}.")

            for post in posts:
                if STOP_REQUESTED:
                    break
                with PERSISTENCE_LOCK:
                    if post["url"] in scraped:
                        print(f"  [skip] {post['title'][:55]}...")
                        continue
                    if limit is not None and counters["new_count"] + len(in_progress) >= limit:
                        STOP_REQUESTED = True
                        break
                    if not claim_movie_url(post["url"], scraped, in_progress):
                        print(f"  [skip] Already scraped or claimed: {post['title'][:55]}...")
                        continue
                    counters["total"] += 1
                    count = counters["total"]

                movie_data = None
                try:
                    if transport == "http":
                        movie_data = scrape_movie_http(
                            driver,
                            post["url"],
                            thumb_hint=post.get("thumbnail", ""),
                            count=count,
                        )
                    else:
                        movie_data = scrape_movie(
                            driver, post["url"],
                            thumb_hint=post.get("thumbnail", ""),
                            count=count
                        )
                    if movie_data:
                        with PERSISTENCE_LOCK:
                            append_movie_record(movie_data)
                            scraped.add(post["url"])
                            state["scraped_urls"] = sorted(scraped)
                            state["total_scraped"] = len(scraped)
                            counters["new_count"] += 1
                            save_state(state)
                            print(f"  [SAVED] #{count} | new this run: {counters['new_count']}")
                            if limit is not None and counters["new_count"] >= limit:
                                print(f"\n[*] Reached --limit {limit}. Stopping.")
                                STOP_REQUESTED = True
                finally:
                    with PERSISTENCE_LOCK:
                        in_progress.discard(post["url"])

                if STOP_REQUESTED:
                    break
                time.sleep(random.uniform(delay * 0.8, delay * 1.3))

            if STOP_REQUESTED:
                break

            page_num += step
            with PERSISTENCE_LOCK:
                if track_resume:
                    state["current_page"] = page_num
                    save_state(state)
            if end_page is not None:
                if (step > 0 and page_num > end_page) or (step < 0 and page_num < start_page):
                    break
            page_pause = (0.4, 1.0) if transport == "http" else (2.5, 4.0)
            print(f"[*] {worker_name} moving to page {page_num}...")
            time.sleep(random.uniform(*page_pause))
    finally:
        driver.close() if transport == "http" else driver.quit()


def main():
    global STOP_REQUESTED

    parser = argparse.ArgumentParser(
        description="BollyFlix scraper with resumable, ranged, reverse, and parallel page downloads."
    )
    parser.add_argument(
        "--transport", choices=("http", "browser"), default="http",
        help="Scraping engine: direct HTTP (fast, default) or Selenium browser"
    )
    parser.add_argument(
        "--headless", action="store_true", default=True,
        help="Run selected browser headless (default: True)"
    )
    parser.add_argument(
        "--no-headless", dest="headless", action="store_false",
        help="Open visible browser window"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear saved progress and restart from page 1"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after scraping this many NEW movies (default: no limit)"
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Base seconds to wait between movie requests (default: 0.5)"
    )
    parser.add_argument(
        "--start-page", type=int, default=None,
        help="First page in the range (inclusive); defaults to the resume page"
    )
    parser.add_argument(
        "--end-page", type=int, default=None,
        help="Last page in the range (inclusive); required for reverse or multiple workers"
    )
    parser.add_argument(
        "--reverse", action="store_true",
        help="Download the selected page range from highest page to lowest"
    )
    parser.add_argument(
        "--browsers", "--browser", "--instances", dest="browsers", type=int, default=1,
        help="Number of parallel workers/browser instances (default: 1)"
    )
    parser.add_argument(
        "--browser-types",
        default="chrome",
        help="Comma-separated browser types by instance: chrome, firefox, edge (default: chrome)"
    )
    args = parser.parse_args()

    if args.start_page is not None and args.start_page < 1:
        parser.error("--start-page must be at least 1")
    if args.end_page is not None and args.end_page < 1:
        parser.error("--end-page must be at least 1")
    if args.start_page is not None and args.end_page is not None and args.start_page > args.end_page:
        parser.error("--start-page must not be greater than --end-page")
    if args.reverse and args.end_page is None:
        parser.error("--reverse requires --end-page to define the upper page bound")
    if args.browsers < 1:
        parser.error("--browsers must be at least 1")
    if args.browsers > 1 and args.end_page is None:
        parser.error("--end-page is required when using multiple workers")
    browser_types = [browser.strip().lower() for browser in args.browser_types.split(",")]
    supported_browsers = {"chrome", "firefox", "edge"}
    if args.transport == "browser" and (
        not browser_types or any(not browser for browser in browser_types)
    ):
        parser.error("--browser-types must be a comma-separated list of browser names")
    unsupported_browsers = sorted(set(browser_types) - supported_browsers)
    if args.transport == "browser" and unsupported_browsers:
        parser.error(
            f"unsupported browser type(s): {', '.join(unsupported_browsers)} "
            "(choose chrome, firefox, or edge)"
        )
    if args.delay < 0:
        parser.error("--delay must not be negative")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    print("=" * 65)
    print("     BOLLYFLIX SCRAPER  |  Ctrl+C to pause, re-run to resume")
    print("=" * 65)

    os.makedirs(THUMBNAILS_DIR, exist_ok=True)

    if args.reset and os.path.exists(STATE_FILE):
        with PERSISTENCE_LOCK, persistence_file_lock():
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
        print("[!] Progress reset.")

    state = load_state()
    scraped = set(state.get("scraped_urls", []))
    resume_page = state.get("current_page", 1)
    total = len(scraped)
    in_progress = set()
    counters = {"total": total, "new_count": 0}

    start_page = args.start_page if args.start_page is not None else resume_page
    if args.reverse:
        start_page = args.start_page if args.start_page is not None else 1
    if args.end_page is not None and start_page > args.end_page:
        parser.error("the resolved start page must not be greater than --end-page")
    track_resume = args.start_page is None and args.end_page is None and not args.reverse
    print(f"[*] Starting at page {start_page} | Already scraped: {total}")
    print(f"[*] Transport: {args.transport}")
    if args.transport == "browser":
        print(f"[*] Headless: {args.headless}")
    print(f"[*] Limit: {args.limit or 'unlimited'} | Delay: {args.delay}s")
    print(f"[*] Instances: {args.browsers} | Order: {'descending' if args.reverse else 'ascending'}")
    print("=" * 65)

    if args.end_page is None:
        page_ranges = [(start_page, None)]
    else:
        page_ranges = partition_page_range(start_page, args.end_page, args.browsers, args.reverse)
    if args.transport == "http":
        browser_types = ["chrome"] * len(page_ranges)
    elif len(browser_types) == 1:
        browser_types *= len(page_ranges)
    elif len(browser_types) != len(page_ranges):
        parser.error(
            f"--browser-types specifies {len(browser_types)} browsers, but "
            f"this run creates {len(page_ranges)} instances"
        )
    STOP_REQUESTED = False
    try:
        with ThreadPoolExecutor(max_workers=len(page_ranges)) as executor:
            futures = [
                executor.submit(
                    scrape_page_range,
                    index + 1,
                    args.transport,
                    browser_types[index],
                    range_start,
                    range_end,
                    args.reverse,
                    args.headless,
                    args.delay,
                    args.limit,
                    track_resume,
                    scraped,
                    in_progress,
                    state,
                    counters,
                )
                for index, (range_start, range_end) in enumerate(page_ranges)
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    STOP_REQUESTED = True
                    print(f"\n[!] Browser worker failed: {error}")
                    raise
    except KeyboardInterrupt:
        STOP_REQUESTED = True
        print("\n[!] Stop requested. Waiting for active movies to finish...")
    except Exception as error:
        print(f"\n[!] Scraping stopped due to an error: {error}")
    finally:
        with PERSISTENCE_LOCK:
            state["scraped_urls"] = sorted(scraped)
            state["total_scraped"] = len(scraped)
            save_state(state)

        print("\n" + "=" * 65)
        status = "PAUSED" if STOP_REQUESTED else "FINISHED"
        print(f"[{status}] Total saved: {len(scraped)} | New this run: {counters['new_count']}")
        print(f"[*] CSV        : {os.path.abspath(CSV_FILE)}")
        print(f"[*] JSON       : {os.path.abspath(JSON_FILE)}")
        print(f"[*] Thumbnails : {os.path.abspath(THUMBNAILS_DIR)}")
        print(f"[*] Next run   : python main.py  (resumes from page {state.get('current_page', resume_page)})")
        print("=" * 65)


if __name__ == "__main__":
    main()