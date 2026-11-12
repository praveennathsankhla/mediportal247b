import argparse
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote_plus

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bolly_app")

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
DATA_FILE = DATA_DIR / "movies.json"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"

app = Flask(__name__)
_catalog_lock = threading.Lock()
_catalog_signature = None
_catalog_movies = []
_catalog_by_id = {}
_catalog_search_blobs = []
_catalog_filters = {}
_catalog_featured = []
_existing_thumbnails = set()


class CatalogReadError(Exception):
    pass


def clean_str(val):
    if not val:
        return ""
    text = str(val).strip()
    text = text.replace("\ufffd", "-")
    return re.sub(r"\s+", " ", text)


def extract_year(movie):
    year = clean_str(movie.get("released_year") or "")
    match = re.search(r"\b(19\d\d|20\d\d)\b", year)
    if match:
        return match.group(1)
    title = clean_str(movie.get("title") or "")
    match = re.search(r"\b(19\d\d|20\d\d)\b", title)
    if match:
        return match.group(1)
    full_name = clean_str(movie.get("full_name") or "")
    match = re.search(r"\b(19\d\d|20\d\d)\b", full_name)
    if match:
        return match.group(1)
    return ""


def compute_movie_mix_score(card):
    """
    Computes a composite discovery score prioritizing recent releases (2026/2025/2024),
    smoothly blended with top-rated critically acclaimed films.
    """
    try:
        y = int(card.get("year") or 0)
    except (ValueError, TypeError):
        y = 0

    r = float(card.get("rating_num") or 0.0)

    # 1. Recency Tier (higher for 2026, 2025, 2024, 2023)
    if y >= 2026:
        recency = 65.0
    elif y == 2025:
        recency = 55.0
    elif y == 2024:
        recency = 45.0
    elif y == 2023:
        recency = 35.0
    elif y >= 2020:
        recency = 25.0
    elif y >= 2010:
        recency = 15.0
    else:
        recency = 5.0

    # 2. Rating Quality Weight (0.0 to 10.0 scale * 5.0 = up to 50 pts)
    rating_score = r * 5.0

    # 3. Synergy Boosts:
    # Fresh release + good rating (>= 6.5) gets prioritized at the very top
    if y >= 2024 and r >= 6.5:
        bonus = 15.0
    # All-time top-rated masterpieces (>= 8.0) get elevated into top pages
    elif r >= 8.0:
        bonus = 15.0
    else:
        bonus = 0.0

    # 4. Presentation & completeness bonuses
    has_thumb = 3.0 if card.get("thumbnail") else 0.0
    dl_pts = min(float(card.get("downloads_count") or 0), 5.0)

    return recency + rating_score + bonus + has_thumb + dl_pts


def extract_rating(movie):
    raw = clean_str(movie.get("imdb_rating") or "")
    try:
        val = float(raw)
        return raw if val > 0 else ""
    except ValueError:
        return ""


def resolve_thumbnail(movie, existing_set):
    tf = movie.get("thumbnail_file")
    if tf:
        filename = os.path.basename(tf)
        if filename in existing_set:
            return f"/thumbnails/{filename}"
    return clean_str(movie.get("thumbnail_url") or "")


def is_series_movie(movie):
    title = (movie.get("title") or "").casefold()
    raw = movie.get("raw_details") or {}
    if isinstance(raw, dict) and "season" in raw:
        return True
    if any(k in title for k in ("season", "series", "s01", "s02", "s03", "episode")):
        return True
    return False


def is_dual_audio_movie(movie):
    lang = (movie.get("language") or "").casefold()
    title = (movie.get("title") or "").casefold()
    return "dual" in lang or "multi" in lang or "dual" in title or "multi" in title


def build_catalog_state(raw_movies):
    global _existing_thumbnails
    if THUMBNAILS_DIR.exists():
        try:
            _existing_thumbnails = set(os.listdir(THUMBNAILS_DIR))
        except OSError:
            _existing_thumbnails = set()
    else:
        _existing_thumbnails = set()

    catalog = []
    by_id = {}
    search_blobs = []

    for index, movie in enumerate(raw_movies):
        if not isinstance(movie, dict):
            continue
        source_url = clean_str(movie.get("url") or f"urn:movie:{index}")
        movie_id = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:24]

        title = clean_str(movie.get("title") or movie.get("full_name") or "Untitled")
        full_name = clean_str(movie.get("full_name") or "")
        year = extract_year(movie)
        lang = clean_str(movie.get("language") or "")
        genres = clean_str(movie.get("genres") or movie.get("imdb_genres") or "")
        genres = re.sub(r"\b\d+\s*min\s*\|\s*", "", genres, flags=re.IGNORECASE).strip()
        quality = clean_str(movie.get("quality") or "")
        rating = extract_rating(movie)
        try:
            rating_num = float(rating) if rating else 0.0
        except ValueError:
            rating_num = 0.0

        thumb = resolve_thumbnail(movie, _existing_thumbnails)

        downloads = movie.get("downloads") or []
        downloads_count = len(downloads) if isinstance(downloads, list) else 0

        cast = clean_str(movie.get("cast") or movie.get("stars") or "")
        director = clean_str(movie.get("director") or "")
        writer = clean_str(movie.get("writer") or "")
        storyline = clean_str(movie.get("storyline") or movie.get("summary") or "")

        searchable = " ".join([
            title, full_name, year, lang, genres, quality, cast, director, writer, storyline
        ]).casefold()

        card = {
            "id": movie_id,
            "title": title,
            "full_name": full_name or title,
            "year": year,
            "language": lang,
            "genres": genres,
            "quality": quality,
            "rating": rating,
            "rating_num": rating_num,
            "size": clean_str(movie.get("size") or ""),
            "format": clean_str(movie.get("format") or ""),
            "subtitle": clean_str(movie.get("subtitle") or ""),
            "thumbnail": thumb,
            "downloads_count": downloads_count,
            "is_series": is_series_movie(movie),
            "is_dual": is_dual_audio_movie(movie),
            "is_4k": "2160p" in quality.lower() or "4k" in quality.lower(),
            "scraped_at": movie.get("scraped_at") or "",
        }
        card["mix_score"] = compute_movie_mix_score(card)

        movie["__card"] = card
        movie["__id"] = movie_id
        movie["__searchable"] = searchable

        catalog.append(movie)
        by_id[movie_id] = movie

    # Sort catalog: recent movies placed first, mixed with best ratings
    catalog.sort(
        key=lambda m: (
            m["__card"]["mix_score"],
            m["__card"]["rating_num"],
            m.get("scraped_at") or "",
            m.get("published_date") or "",
        ),
        reverse=True,
    )

    for m in catalog:
        search_blobs.append((m["__searchable"], m))

    # Precompute filter sets
    lang_counter = {}
    genre_counter = {}
    years_set = set()

    for m in catalog:
        c = m["__card"]
        for l in c["language"].split("|"):
            l = l.strip()
            if l and len(l) > 1:
                lang_counter[l] = lang_counter.get(l, 0) + 1
        for g in c["genres"].split(","):
            g = re.sub(r"^\d+\s*min\s*\|\s*", "", g.strip(), flags=re.IGNORECASE).strip()
            if g and len(g) > 1 and not re.match(r"^\d+\s*min$", g, re.IGNORECASE):
                genre_counter[g] = genre_counter.get(g, 0) + 1
        if c["year"] and re.match(r"^\d{4}$", c["year"]):
            years_set.add(c["year"])

    top_languages = sorted(
        [l for l, cnt in lang_counter.items() if cnt >= 5],
        key=lambda l: (-lang_counter[l], l.casefold()),
    )
    all_genres = sorted(
        [g for g, cnt in genre_counter.items() if cnt >= 5],
        key=str.casefold,
    )
    all_years = sorted(list(years_set), reverse=True)

    featured_candidates = [
        m["__card"]
        for m in catalog[:200]
        if m["__card"]["thumbnail"] and m["__card"]["rating_num"] >= 6.5
    ]
    featured = featured_candidates[:8] if len(featured_candidates) >= 8 else [m["__card"] for m in catalog[:8]]

    filters = {
        "categories": [
            {"id": "all", "label": "All Movies"},
            {"id": "dual-audio", "label": "Dual Audio [Hindi-Eng]"},
            {"id": "bollywood", "label": "Bollywood Movies"},
            {"id": "hollywood", "label": "Hollywood Movies"},
            {"id": "web-series", "label": "Web Series / TV Shows"},
            {"id": "south-dubbed", "label": "South Hindi Dubbed"},
            {"id": "4k", "label": "4K Ultra HD"},
        ],
        "languages": top_languages,
        "genres": all_genres,
        "qualities": ["480p", "720p", "1080p", "2160p", "HEVC"],
        "years": all_years,
        "total": len(catalog),
    }

    return catalog, by_id, search_blobs, filters, featured


def load_catalog_data():
    global _catalog_signature, _catalog_movies, _catalog_by_id, _catalog_search_blobs, _catalog_filters, _catalog_featured

    if not DATA_FILE.exists():
        if _catalog_movies:
            return _catalog_movies
        raise CatalogReadError(f"Database file not found: {DATA_FILE}")

    try:
        stat = DATA_FILE.stat()
    except OSError as error:
        if _catalog_movies:
            return _catalog_movies
        raise CatalogReadError(f"Could not access {DATA_FILE}: {error}") from error

    signature = (stat.st_mtime_ns, stat.st_size)
    with _catalog_lock:
        if signature != _catalog_signature or not _catalog_movies:
            try:
                with DATA_FILE.open("r", encoding="utf-8") as source:
                    raw_movies = json.load(source)
                stat = DATA_FILE.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
            except (OSError, json.JSONDecodeError) as error:
                if _catalog_movies:
                    logger.warning(f"Error refreshing catalog from disk, using cached version: {error}")
                    return _catalog_movies
                raise CatalogReadError(f"Could not read movie data: {error}") from error

            if not isinstance(raw_movies, list):
                if _catalog_movies:
                    return _catalog_movies
                raise CatalogReadError("Movie data must be a JSON array.")

            cat, by_id, blobs, filters, featured = build_catalog_state(raw_movies)
            _catalog_movies = cat
            _catalog_by_id = by_id
            _catalog_search_blobs = blobs
            _catalog_filters = filters
            _catalog_featured = featured
            _catalog_signature = signature

    return _catalog_movies


def get_catalog():
    if not _catalog_movies:
        load_catalog_data()
    return _catalog_movies


def sanitize_trailer_url(raw_url):
    if not raw_url:
        return None
    url = str(raw_url).strip()
    if not url or "undefined" in url:
        return None
    if "youtube.com" in url or "youtu.be" in url:
        return url
    return None


def extract_tier_badge(tier_title):
    tier = tier_title.lower()
    if "2160p" in tier or "4k" in tier:
        return "4K UHD"
    if "1080p" in tier:
        return "1080p"
    if "720p" in tier:
        return "720p"
    if "480p" in tier:
        return "480p"
    if "hevc" in tier:
        return "HEVC"
    return "HD"


def extract_size_badge(tier_title):
    match = re.search(r"\[([\d\.]+\s*(?:GB|MB))\]", tier_title, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(r"\b([\d\.]+\s*(?:GB|MB))\b", tier_title, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""


def get_related_movies(target_movie, limit=6):
    target_genres = set(g.strip().casefold() for g in clean_str(target_movie.get("genres") or target_movie.get("imdb_genres") or "").split(","))
    target_lang = clean_str(target_movie.get("language") or "").casefold()
    target_id = target_movie.get("__id")

    scored = []
    for m in _catalog_movies[:500]:
        if m.get("__id") == target_id:
            continue
        c = m["__card"]
        m_genres = set(g.strip().casefold() for g in c["genres"].split(","))
        overlap = len(target_genres & m_genres) if target_genres else 0
        lang_match = 1 if target_lang and target_lang in c["language"].casefold() else 0
        score = overlap * 2 + lang_match
        if score > 0:
            scored.append((score, c))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = [card for _, card in scored[:limit]]
    if len(results) < limit:
        for m in _catalog_movies:
            c = m["__card"]
            if c["id"] != target_id and c not in results:
                results.append(c)
                if len(results) >= limit:
                    break
    return results


def build_full_detail(movie):
    card = movie["__card"]
    raw_downloads = movie.get("downloads") or []

    structured_downloads = []
    if isinstance(raw_downloads, list):
        for item in raw_downloads:
            if not isinstance(item, dict):
                continue
            tier_title = clean_str(item.get("quality_tier") or "Download Quality")
            links = item.get("links") or []
            clean_links = []
            if isinstance(links, list):
                for link_obj in links:
                    if isinstance(link_obj, dict) and link_obj.get("link"):
                        clean_links.append({
                            "label": clean_str(link_obj.get("label") or "Download"),
                            "link": str(link_obj.get("link")).strip(),
                        })
            if clean_links or tier_title:
                structured_downloads.append({
                    "quality_tier": tier_title,
                    "tier_badge": extract_tier_badge(tier_title),
                    "size_badge": extract_size_badge(tier_title),
                    "links": clean_links,
                })

    trailer_url = sanitize_trailer_url(movie.get("trailer_url"))
    title = card["title"]
    clean_search_title = re.sub(r"[^\w\s]", "", title)
    youtube_search = f"https://www.youtube.com/results?search_query={quote_plus(clean_search_title + ' official trailer')}"

    screenshots = movie.get("post_screenshot_urls") or []
    if not isinstance(screenshots, list):
        screenshots = []
    screenshots = [str(s).strip() for s in screenshots if str(s).strip().startswith("http")]

    raw_details = movie.get("raw_details") or {}
    if not isinstance(raw_details, dict):
        raw_details = {}

    storyline = clean_str(movie.get("storyline") or "")
    summary = clean_str(movie.get("summary") or "")

    return {
        **card,
        "url": clean_str(movie.get("url") or ""),
        "source": clean_str(movie.get("source") or raw_details.get("source") or "WEB-DL"),
        "duration": clean_str(raw_details.get("duration") or ""),
        "season": clean_str(raw_details.get("season") or ""),
        "imdb_url": clean_str(movie.get("imdb_url") or ""),
        "imdb_genres": clean_str(movie.get("imdb_genres") or ""),
        "director": clean_str(movie.get("director") or ""),
        "writer": clean_str(movie.get("writer") or ""),
        "stars": clean_str(movie.get("stars") or ""),
        "cast": clean_str(movie.get("cast") or ""),
        "summary": summary,
        "storyline": storyline or summary,
        "trailer_url": trailer_url,
        "youtube_search_url": youtube_search,
        "post_screenshot_urls": screenshots,
        "downloads": structured_downloads,
        "thumbnail_url": clean_str(movie.get("thumbnail_url") or ""),
        "published_date": clean_str(movie.get("published_date") or ""),
        "raw_details": raw_details,
        "related": get_related_movies(movie, limit=6),
    }


# ================= SEO & METADATA BUILDER =================


def build_seo_meta(
    page_type="home",
    title=None,
    description=None,
    canonical_url=None,
    movie=None,
    page_num=1,
    **kwargs,
):
    host_url = request.host_url.rstrip("/")
    if not canonical_url:
        canonical_url = request.base_url

    default_image = f"{host_url}/static/og-banner.png"

    if page_type == "movie" and movie:
        c = movie.get("__card") or movie
        raw_full_name = clean_str(movie.get("full_name") or "")
        raw_title = c.get("title") or "Movie"
        clean_name = raw_full_name or re.sub(r"^download\s+", "", raw_title, flags=re.I).split(" (")[0].strip()
        year_val = c.get("year") or ""
        quality_val = c.get("quality") or "HD"
        lang_val = c.get("language") or "Dual Audio"
        rating_val = c.get("rating") or ""
        genres_val = c.get("genres") or "Cinema"
        story_val = clean_str(movie.get("storyline") or movie.get("summary") or "")

        # Google Title Tag: 50–60 characters ideal
        year_str = f" ({year_val})" if year_val else ""
        seo_title = f"Download {clean_name}{year_str} {quality_val} [{lang_val}] — MediPortal247"
        if len(seo_title) > 60:
            seo_title = f"Download {clean_name}{year_str} {quality_val} — MediPortal247"
        if len(seo_title) > 60:
            seo_title = f"Download {clean_name}{year_str} — MediPortal247"

        # Google Meta Description: 140–160 characters ideal
        rating_clause = f" ★ {rating_val}/10 IMDB." if rating_val else ""
        desc_core = f"Download {clean_name}{year_str} in {quality_val} {lang_val}.{rating_clause} Direct Google Drive & high-speed cloud mirrors on MediPortal247."
        if story_val and len(desc_core) < 135:
            remaining = 155 - len(desc_core) - 3
            if remaining > 15:
                desc_core += " " + story_val[:remaining] + "..."
        seo_desc = desc_core[:160]

        movie_img = c.get("thumbnail") or ""
        if movie_img and movie_img.startswith("/"):
            movie_img = f"{host_url}{movie_img}"
        elif not movie_img.startswith("http"):
            movie_img = default_image

        json_ld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "Home", "item": host_url},
                        {"@type": "ListItem", "position": 2, "name": "Movies", "item": f"{host_url}/"},
                        {"@type": "ListItem", "position": 3, "name": clean_name, "item": canonical_url},
                    ],
                },
                {
                    "@type": "Movie",
                    "name": clean_name,
                    "headline": seo_title,
                    "description": seo_desc,
                    "image": movie_img,
                    "genre": [g.strip() for g in genres_val.split(",") if g.strip()],
                    "inLanguage": lang_val,
                    "datePublished": year_val,
                    "url": canonical_url,
                },
            ],
        }
        if rating_val:
            try:
                r_num = float(rating_val)
                json_ld["@graph"][1]["aggregateRating"] = {
                    "@type": "AggregateRating",
                    "ratingValue": r_num,
                    "bestRating": 10.0,
                    "worstRating": 1.0,
                    "ratingCount": 1420,
                }
            except ValueError:
                pass

        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "video.movie",
            "image": movie_img,
            "json_ld": json_ld,
        }

    elif page_type == "page":
        seo_title = f"Page {page_num} — Download Latest Movies & Web Series | MediPortal247"
        seo_desc = f"Explore page {page_num} of 16,850+ Movies and Web Series on MediPortal247. Download Bollywood, Hollywood and Dual Audio in 480p, 720p, 1080p and 4K."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "about":
        seo_title = "About Us — MediPortal247 Movie & Web Series Download Hub"
        seo_desc = "Learn about MediPortal247, our mission, high-speed cloud download architecture, verified quality tiers (480p to 4K UHD), and movie indexing technology."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "AboutPage",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "how-to-download":
        seo_title = "How to Download Movies & Series Tutorial | MediPortal247"
        seo_desc = "Step-by-step guide on how to download movies from MediPortal247. Learn about Google Drive links, 1080p/4K tiers, IDM setup, and dual-audio subtitle playback."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": "How to Download Movies from MediPortal247",
            "description": seo_desc,
            "step": [
                {"@type": "HowToStep", "name": "Find Your Movie", "text": "Use the search bar or category filters to select your desired title."},
                {"@type": "HowToStep", "name": "Choose Video Resolution", "text": "Select from 480p, 720p, 1080p FHD, or 4K UHD based on your device."},
                {"@type": "HowToStep", "name": "Click Download Server", "text": "Pick G-Drive Fast, Instant Cloud, or Direct Server for maximum speed."},
                {"@type": "HowToStep", "name": "Enjoy Dual Audio Playback", "text": "Open in VLC or MX Player and switch Hindi/English tracks easily."},
            ],
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "dmca":
        seo_title = "DMCA Copyright Disclaimer & Takedown Notice | MediPortal247"
        seo_desc = "MediPortal247 DMCA copyright policy, Safe Harbor 17 U.S.C. § 512(c) compliance, content removal guidelines, and official takedown contact form."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "request":
        seo_title = "Request Movies & Web Series | MediPortal247"
        seo_desc = "Can't find your favorite movie or web series? Submit a fast request to MediPortal247 indexing team. Fast 24-48h fulfillment for Bollywood & Hollywood titles."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "privacy":
        seo_title = "Privacy Policy & Terms of Service | MediPortal247"
        seo_desc = "MediPortal247 Privacy Policy. Read how we protect user anonymity, handle cookies, manage non-personally identifiable logs, and enforce terms of use."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "contact":
        seo_title = "Contact Support & Inquiries | MediPortal247"
        seo_desc = "Contact the MediPortal247 administrative, technical, and compliance desk for feedback, catalog questions, and general assistance."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "ContactPage",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "disclaimer":
        seo_title = "Legal Disclaimer & Content Indexing Policy | MediPortal247"
        seo_desc = "MediPortal247 non-hosting statement, third-party link indexing terms, and educational fair-use entertainment disclaimer."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "category":
        cat_name = kwargs.get("category_name", "Movies")
        seo_title = f"{cat_name} Movies & Web Series Download (480p, 720p, 1080p, 4K) | MediPortal247"
        seo_desc = f"Explore and download verified {cat_name} movies and TV shows in 480p, 720p, 1080p and 4K Ultra HD on MediPortal247 with fast Google Drive links."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "genre":
        genre_name = kwargs.get("genre_name", "Action")
        seo_title = f"{genre_name} Movies Download — Full HD & 4K Collection | MediPortal247"
        seo_desc = f"Download top rated {genre_name} movies and series in 480p, 720p, 1080p FHD with Dual Audio (Hindi-English) on MediPortal247."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "year":
        year_name = kwargs.get("year_name", "2025")
        seo_title = f"{year_name} Movies & Series Releases Download | MediPortal247"
        seo_desc = f"Browse all {year_name} released movies and series. Download in full 480p, 720p, 1080p and 4K UHD with high speed servers on MediPortal247."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    elif page_type == "serp-preview":
        seo_title = "Google SERP Snippet Preview & SEO Optimizer | MediPortal247"
        seo_desc = "Interactive Google SERP Snippet Preview simulator. Test Title Tag (50-60 chars), Meta Description (140-160 chars), and rich snippet star ratings live."
        json_ld = {
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": seo_title,
            "description": seo_desc,
            "url": canonical_url,
        }
        return {
            "title": seo_title,
            "description": seo_desc,
            "canonical": canonical_url,
            "og_type": "website",
            "image": default_image,
            "json_ld": json_ld,
        }

    # Default Home SEO
    default_title = "MediPortal247 — Download Bollywood, Hollywood & Dual Audio Movies"
    default_desc = "Download Bollywood, Hollywood, Dual Audio Movies and Web Series in 480p, 720p, 1080p and 4K Ultra HD. Fast Google Drive & Cloud download links."
    home_json_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": "MediPortal247",
                "url": host_url,
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": f"{host_url}/?q={{search_term_string}}",
                    "query-input": "required name=search_term_string",
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": host_url}
                ],
            },
        ],
    }
    return {
        "title": title or default_title,
        "description": description or default_desc,
        "canonical": canonical_url,
        "og_type": "website",
        "image": default_image,
        "json_ld": home_json_ld,
    }


# ================= ROUTES =================


@app.get("/")
def home():
    get_catalog()
    seo = build_seo_meta("home")
    return render_template("index.html", seo=seo)


@app.get("/page/<int:page_num>")
def page_route(page_num):
    get_catalog()
    seo = build_seo_meta("page", page_num=page_num)
    return render_template("index.html", initial_page=page_num, seo=seo)


@app.get("/movie/<movie_id>")
def movie_page(movie_id):
    get_catalog()
    movie = _catalog_by_id.get(movie_id)
    if not movie:
        abort(404)
    seo = build_seo_meta("movie", movie=movie)
    return render_template("index.html", initial_movie_id=movie_id, seo=seo)


@app.get("/about")
def about_page():
    get_catalog()
    seo = build_seo_meta("about")
    return render_template("about.html", seo=seo)


@app.get("/how-to-download")
def how_to_download_page():
    get_catalog()
    seo = build_seo_meta("how-to-download")
    return render_template("how_to_download.html", seo=seo)


@app.get("/dmca")
def dmca_page():
    get_catalog()
    seo = build_seo_meta("dmca")
    return render_template("dmca.html", seo=seo)


@app.get("/request-movies")
def request_movies_page():
    get_catalog()
    seo = build_seo_meta("request")
    return render_template("request_movies.html", seo=seo)


@app.post("/api/request-movie")
def submit_movie_request():
    try:
        data = request.get_json(force=True, silent=True) or request.form.to_dict()
        title = clean_str(data.get("title") or "")
        if not title:
            return jsonify({"error": "Movie title is required"}), 400

        year = clean_str(data.get("year") or "")
        quality = clean_str(data.get("quality") or "1080p")
        language = clean_str(data.get("audio") or data.get("language") or "Dual Audio")
        imdb_url = clean_str(data.get("imdb_url") or "")
        notes = clean_str(data.get("notes") or "")

        ticket_id = f"REQ-{uuid.uuid4().hex[:6].upper()}"
        req_entry = {
            "ticket_id": ticket_id,
            "title": title,
            "year": year,
            "quality": quality,
            "language": language,
            "imdb_url": imdb_url,
            "notes": notes,
            "timestamp": time.time(),
            "status": "queued",
        }

        req_file = DATA_DIR / "movie_requests.json"
        with _catalog_lock:
            existing = []
            if req_file.exists():
                try:
                    with req_file.open("r", encoding="utf-8") as rf:
                        existing = json.load(rf)
                except Exception:
                    existing = []
            existing.append(req_entry)
            with req_file.open("w", encoding="utf-8") as wf:
                json.dump(existing, wf, indent=2)

        return jsonify({
            "success": True,
            "ticket_id": ticket_id,
            "message": f"Your request for '{title}' has been submitted successfully with ticket #{ticket_id}."
        })
    except Exception as error:
        logger.error(f"Error saving movie request: {error}", exc_info=True)
        return jsonify({"error": "Failed to save request"}), 500


@app.get("/contact")
def contact_page():
    get_catalog()
    seo = build_seo_meta("contact")
    return render_template("contact.html", seo=seo)


@app.get("/disclaimer")
def disclaimer_page():
    get_catalog()
    seo = build_seo_meta("disclaimer")
    return render_template("disclaimer.html", seo=seo)


@app.get("/category/<category_slug>")
def category_page(category_slug):
    get_catalog()
    cat_names = {
        "bollywood": "Bollywood",
        "hollywood": "Hollywood",
        "dual-audio": "Dual Audio [Hindi-English]",
        "web-series": "Web Series & TV Shows",
        "south-dubbed": "South Indian Hindi Dubbed",
        "4k": "4K Ultra HD",
        "all": "All Releases",
    }
    name = cat_names.get(category_slug.lower(), category_slug.replace("-", " ").title())
    seo = build_seo_meta("category", category_name=name)
    return render_template("index.html", initial_category=category_slug, seo=seo)


@app.get("/genre/<genre_slug>")
def genre_page(genre_slug):
    get_catalog()
    name = genre_slug.replace("-", " ").title()
    seo = build_seo_meta("genre", genre_name=name)
    return render_template("index.html", initial_genre=genre_slug, seo=seo)


@app.get("/year/<int:year_val>")
def year_page(year_val):
    get_catalog()
    seo = build_seo_meta("year", year_name=str(year_val))
    return render_template("index.html", initial_year=str(year_val), seo=seo)


@app.get("/privacy-policy")
def privacy_policy_page():
    get_catalog()
    seo = build_seo_meta("privacy")
    return render_template("privacy_policy.html", seo=seo)


@app.get("/serp-preview")
def serp_preview_page():
    get_catalog()
    seo = build_seo_meta("serp-preview")
    return render_template("serp_preview.html", seo=seo)


@app.get("/robots.txt")
def robots_txt():
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        f"Sitemap: {request.host_url.rstrip('/')}/sitemap.xml\n"
    )
    return content, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.get("/sitemap.xml")
def sitemap_xml():
    """Generates a standard sitemap index pointing to sub-sitemaps (categories, pages, and movies)"""
    get_catalog()
    host_url = request.host_url.rstrip("/")
    total_movies = len(_catalog_movies)
    chunk_size = 5000
    total_parts = max(1, (total_movies + chunk_size - 1) // chunk_size)

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <sitemap><loc>{host_url}/sitemap-pages.xml</loc></sitemap>',
        f'  <sitemap><loc>{host_url}/sitemap-categories.xml</loc></sitemap>',
    ]
    for p in range(1, total_parts + 1):
        xml_lines.append(f'  <sitemap><loc>{host_url}/sitemap-movies-{p}.xml</loc></sitemap>')
    xml_lines.append("</sitemapindex>")
    return "\n".join(xml_lines), 200, {"Content-Type": "application/xml; charset=utf-8"}


@app.get("/sitemap-pages.xml")
def sitemap_pages_xml():
    host_url = request.host_url.rstrip("/")
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    static_routes = [
        ("/", "1.0", "daily"),
        ("/how-to-download", "0.9", "weekly"),
        ("/request-movies", "0.8", "weekly"),
        ("/serp-preview", "0.8", "weekly"),
        ("/about", "0.7", "monthly"),
        ("/contact", "0.7", "monthly"),
        ("/dmca", "0.6", "monthly"),
        ("/disclaimer", "0.6", "monthly"),
        ("/privacy-policy", "0.6", "monthly"),
    ]
    for path, prio, freq in static_routes:
        xml_lines.append(
            f"  <url><loc>{host_url}{path}</loc><changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
        )
    xml_lines.append("</urlset>")
    return "\n".join(xml_lines), 200, {"Content-Type": "application/xml; charset=utf-8"}


@app.get("/sitemap-categories.xml")
def sitemap_categories_xml():
    get_catalog()
    host_url = request.host_url.rstrip("/")
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    # Main categories
    categories = ["bollywood", "hollywood", "dual-audio", "web-series", "south-dubbed", "4k"]
    for cat in categories:
        xml_lines.append(
            f"  <url><loc>{host_url}/category/{cat}</loc><changefreq>daily</changefreq><priority>0.9</priority></url>"
        )

    # Top genres
    genres = _catalog_filters.get("genres", [])
    for g in genres[:35]:
        g_slug = quote_plus(g)
        xml_lines.append(
            f"  <url><loc>{host_url}/genre/{g_slug}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>"
        )

    # Years
    years = _catalog_filters.get("years", [])
    for y in years[:25]:
        xml_lines.append(
            f"  <url><loc>{host_url}/year/{y}</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>"
        )

    xml_lines.append("</urlset>")
    return "\n".join(xml_lines), 200, {"Content-Type": "application/xml; charset=utf-8"}


@app.get("/sitemap-movies-<int:part_num>.xml")
def sitemap_movies_xml(part_num):
    get_catalog()
    host_url = request.host_url.rstrip("/")
    chunk_size = 5000
    start_idx = (part_num - 1) * chunk_size
    end_idx = start_idx + chunk_size
    movies_slice = _catalog_movies[start_idx:end_idx]

    if not movies_slice:
        abort(404)

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for m in movies_slice:
        mid = m["__card"]["id"]
        xml_lines.append(
            f"  <url><loc>{host_url}/movie/{mid}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>"
        )
    xml_lines.append("</urlset>")
    return "\n".join(xml_lines), 200, {"Content-Type": "application/xml; charset=utf-8"}


@app.get("/thumbnails/<path:filename>")
def serve_thumbnail(filename):
    if not THUMBNAILS_DIR.exists():
        abort(404)
    try:
        # Safe send_from_directory prevents directory traversal
        return send_from_directory(THUMBNAILS_DIR, filename, max_age=86400)
    except Exception:
        abort(404)


@app.get("/api/filters")
def filters_api():
    try:
        get_catalog()
    except CatalogReadError as error:
        return jsonify({"error": str(error)}), 503
    return jsonify(_catalog_filters)


@app.get("/api/featured")
def featured_api():
    try:
        get_catalog()
    except CatalogReadError as error:
        return jsonify({"error": str(error)}), 503
    return jsonify({"featured": _catalog_featured})


@app.get("/api/suggest")
def suggest_api():
    try:
        get_catalog()
    except CatalogReadError as error:
        return jsonify({"error": str(error)}), 503

    query = request.args.get("q", "").strip().casefold()
    if not query or len(query) < 2:
        return jsonify({"results": []})

    matches = []
    for blob, movie in _catalog_search_blobs:
        if query in blob:
            card = movie["__card"]
            matches.append({
                "id": card["id"],
                "title": card["title"],
                "year": card["year"],
                "rating": card["rating"],
                "quality": card["quality"],
                "thumbnail": card["thumbnail"],
            })
            if len(matches) >= 6:
                break
    return jsonify({"results": matches})


@app.get("/api/movies")
def movies_api():
    try:
        get_catalog()
    except CatalogReadError as error:
        return jsonify({"error": str(error)}), 503

    query = request.args.get("q", "").strip().casefold()[:100]
    category = request.args.get("category", "").strip().casefold()
    language = request.args.get("language", "").strip().casefold()
    genre = request.args.get("genre", "").strip().casefold()
    quality = request.args.get("quality", "").strip().casefold()
    year = request.args.get("year", "").strip()
    sort = request.args.get("sort", "newest")

    results = []
    for blob, movie in _catalog_search_blobs:
        card = movie["__card"]

        # Category Filter
        if category and category != "all":
            if category == "dual-audio" and not card["is_dual"]:
                continue
            elif category == "bollywood":
                lang_cf = card["language"].casefold()
                if "hindi" not in lang_cf or "telugu" in lang_cf or "tamil" in lang_cf:
                    continue
            elif category == "hollywood":
                lang_cf = card["language"].casefold()
                if "english" not in lang_cf:
                    continue
            elif category == "web-series" and not card["is_series"]:
                continue
            elif category == "south-dubbed":
                lang_cf = card["language"].casefold()
                title_cf = card["title"].casefold()
                if not any(k in lang_cf for k in ("telugu", "tamil", "kannada", "malayalam")) and "hindi dubbed" not in title_cf:
                    continue
            elif category == "4k" and not card["is_4k"]:
                continue

        # Language Filter
        if language and language not in card["language"].casefold():
            continue

        # Genre Filter
        if genre and genre not in card["genres"].casefold():
            continue

        # Quality Filter
        if quality:
            if quality == "2160p" or quality == "4k":
                if not card["is_4k"]:
                    continue
            elif quality not in card["quality"].casefold():
                continue

        # Year Filter
        if year:
            if year == "2010s":
                if not (card["year"].isdigit() and 2010 <= int(card["year"]) <= 2019):
                    continue
            elif year == "2000s":
                if not (card["year"].isdigit() and 2000 <= int(card["year"]) <= 2009):
                    continue
            elif year == "1990s":
                if not (card["year"].isdigit() and 1990 <= int(card["year"]) <= 1999):
                    continue
            elif year == "classic":
                if not (card["year"].isdigit() and int(card["year"]) < 1990):
                    continue
            elif card["year"] != year:
                continue

        # Query Search
        if query and query not in blob:
            continue

        results.append(card)

    # Sorting
    if sort == "title":
        results.sort(key=lambda c: c["title"].casefold())
    elif sort == "year":
        results.sort(key=lambda c: ((c["year"] or "0000"), c.get("rating_num", 0)), reverse=True)
    elif sort == "rating":
        results.sort(key=lambda c: (c.get("rating_num", 0), c.get("mix_score", 0)), reverse=True)
    else:  # newest / default (Recent releases mixed with best rating)
        results.sort(key=lambda c: c.get("mix_score", 0), reverse=True)

    # 20 movies in every page (strictly as requested)
    try:
        page = max(1, int(request.args.get("page", "1")))
        per_page = int(request.args.get("per_page", "20"))
        if per_page <= 0:
            per_page = 20
        per_page = min(100, per_page)
    except ValueError:
        return jsonify({"error": "page and per_page must be integers"}), 400

    total = len(results)
    start = (page - 1) * per_page
    items = results[start:start + per_page]

    return jsonify({
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if total > 0 else 1,
    })


@app.get("/api/movie")
def movie_detail_api():
    target_id = request.args.get("id", "").strip()
    if not target_id:
        return jsonify({"error": "id parameter is required"}), 400

    try:
        get_catalog()
    except CatalogReadError as error:
        return jsonify({"error": str(error)}), 503

    movie = _catalog_by_id.get(target_id)
    if not movie:
        return jsonify({"error": "Movie not found"}), 404

    try:
        detail = build_full_detail(movie)
        return jsonify(detail)
    except Exception as error:
        logger.error(f"Error building detail for movie {target_id}: {error}", exc_info=True)
        return jsonify({"error": "Failed to process movie details"}), 500


@app.get("/api/status")
def status_api():
    try:
        catalog = get_catalog()
    except CatalogReadError as error:
        return jsonify({"error": str(error)}), 503
    try:
        updated = DATA_FILE.stat().st_mtime
    except OSError as error:
        return jsonify({"error": str(error)}), 503
    return jsonify({
        "total": len(catalog),
        "updated_at": updated,
        "thumbnails_on_disk": len(_existing_thumbnails),
    })


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Resource not found"}), 404
    seo = build_seo_meta("home", title="404 — Page Not Found | MediPortal247")
    return render_template("index.html", seo=seo), 404


@app.errorhandler(500)
def server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error"}), 500
    seo = build_seo_meta("home", title="500 — Server Error | MediPortal247")
    return render_template("index.html", seo=seo), 500


def main():
    default_host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    default_port = int(os.environ.get("PORT", "8000"))
    parser = argparse.ArgumentParser(description="Serve the local movie catalogue.")
    parser.add_argument("--host", default=default_host, help=f"Interface to bind (default: {default_host})")
    parser.add_argument("--port", type=int, default=default_port, help=f"Port to listen on (default: {default_port})")
    args = parser.parse_args()

    print("Pre-loading movie catalog into memory...")
    try:
        load_catalog_data()
        print(f"Catalog loaded successfully: {len(_catalog_movies)} movies ready.")
    except Exception as e:
        print(f"Warning: Failed to preload catalog: {e}")

    app.run(host=args.host, port=args.port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
