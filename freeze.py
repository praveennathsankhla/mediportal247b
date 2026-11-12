import json
import os
import shutil
from pathlib import Path
from flask_frozen import Freezer
import webapp

BUILD_DIR = Path(__file__).resolve().parent / "public"

webapp.app.config["FREEZER_DESTINATION"] = str(BUILD_DIR)
webapp.app.config["FREEZER_REMOVE_EXTRA_FILES"] = False
webapp.app.config["FREEZER_IGNORE_MIMETYPE_WARNINGS"] = True

class CustomFreezer(Freezer):
    def no_argument_rules_urls(self):
        ignored_endpoints = {
            "movie_detail_api",
            "movies_api",
            "suggest_api",
            "submit_movie_request",
            "status_api",
            "filters_api",
            "featured_api",
            "serve_thumbnail",
            "movie_page",
        }
        for rule in self.app.url_map.iter_rules():
            if not rule.arguments and "GET" in rule.methods and rule.endpoint not in ignored_endpoints:
                yield rule.endpoint, {}

freezer = CustomFreezer(webapp.app)


@freezer.register_generator
def sitemap_movies_xml():
    webapp.load_catalog_data()
    total_movies = len(webapp._catalog_movies)
    chunk_size = 5000
    total_parts = max(1, (total_movies + chunk_size - 1) // chunk_size)
    for p in range(1, total_parts + 1):
        yield {"part_num": p}


@freezer.register_generator
def category_page():
    categories = ["bollywood", "hollywood", "dual-audio", "web-series", "south-dubbed", "4k", "all"]
    for cat in categories:
        yield {"category_slug": cat}


@freezer.register_generator
def genre_page():
    webapp.load_catalog_data()
    genres = webapp._catalog_filters.get("genres", [])
    for g in genres[:40]:
        if "/" in g or "\\" in g:
            continue
        yield {"genre_slug": g}


@freezer.register_generator
def year_page():
    webapp.load_catalog_data()
    years = webapp._catalog_filters.get("years", [])
    for y in years[:30]:
        if y.isdigit():
            yield {"year_val": int(y)}


@freezer.register_generator
def page_route():
    for p in range(1, 11):
        yield {"page_num": p}


def export_client_catalog():
    """
    Builds the SPA client catalog and detail chunks into the public directory
    so the site stays well within Cloudflare Pages 20,000 files limit.
    """
    print("[*] Generating client JSON catalog for Cloudflare...")
    api_dir = BUILD_DIR / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    details_dir = api_dir / "details"
    details_dir.mkdir(parents=True, exist_ok=True)

    # Clean old individual movie files if any existed
    old_movie_dir = api_dir / "movie"
    if old_movie_dir.exists():
        shutil.rmtree(old_movie_dir)

    # 1. Export filters
    with (api_dir / "filters.json").open("w", encoding="utf-8") as f:
        json.dump(webapp._catalog_filters, f)

    # 2. Export featured
    with (api_dir / "featured.json").open("w", encoding="utf-8") as f:
        json.dump(webapp._catalog_featured, f)

    # 3. Export compact cards index
    compact_catalog = []
    for m in webapp._catalog_movies:
        card = m["__card"]
        compact_catalog.append(card)

    with (api_dir / "movies_all.json").open("w", encoding="utf-8") as f:
        json.dump(compact_catalog, f, separators=(",", ":"))

    # 4. Group details into 17 chunks of 1000 movies + mapping index
    chunk_size = 1000
    total_movies = len(webapp._catalog_movies)
    chunks_count = (total_movies + chunk_size - 1) // chunk_size
    print(f"[*] Exporting {total_movies} movie details into {chunks_count} chunk files...")

    mapping = {}
    for chunk_idx in range(chunks_count):
        start = chunk_idx * chunk_size
        end = min(start + chunk_size, total_movies)
        chunk_slice = webapp._catalog_movies[start:end]

        chunk_dict = {}
        for m in chunk_slice:
            movie_id = m["__card"]["id"]
            mapping[movie_id] = chunk_idx
            chunk_dict[movie_id] = {
                "id": movie_id,
                "url": webapp.clean_str(m.get("url") or ""),
                "title": webapp.clean_str(m.get("title") or ""),
                "full_name": webapp.clean_str(m.get("full_name") or ""),
                "published_date": webapp.clean_str(m.get("published_date") or ""),
                "imdb_rating": webapp.clean_str(m.get("imdb_rating") or ""),
                "imdb_url": webapp.clean_str(m.get("imdb_url") or ""),
                "director": webapp.clean_str(m.get("director") or ""),
                "writer": webapp.clean_str(m.get("writer") or ""),
                "stars": webapp.clean_str(m.get("stars") or m.get("cast") or ""),
                "summary": webapp.clean_str(m.get("summary") or ""),
                "storyline": webapp.clean_str(m.get("storyline") or ""),
                "language": webapp.clean_str(m.get("language") or ""),
                "released_year": webapp.clean_str(m.get("released_year") or ""),
                "size": webapp.clean_str(m.get("size") or ""),
                "quality": webapp.clean_str(m.get("quality") or ""),
                "genres": webapp.clean_str(m.get("genres") or m.get("imdb_genres") or ""),
                "trailer_url": webapp.clean_str(m.get("trailer_url") or ""),
                "post_screenshot_urls": m.get("post_screenshot_urls") or [],
                "downloads": m.get("downloads") or [],
                "thumbnail_url": webapp.clean_str(m.get("thumbnail_url") or ""),
            }

        with (details_dir / f"chunk_{chunk_idx}.json").open("w", encoding="utf-8") as f:
            json.dump(chunk_dict, f, separators=(",", ":"))

    with (api_dir / "details_map.json").open("w", encoding="utf-8") as f:
        json.dump(mapping, f, separators=(",", ":"))

    print("[✓] Client JSON catalog successfully generated.")


if __name__ == "__main__":
    print("[*] Loading catalog data into memory...")
    webapp.load_catalog_data()
    print("[*] Freezing Flask app into static HTML & assets...")
    freezer.freeze()
    export_client_catalog()
    print(f"[✓] Deployment build complete! Files written to {BUILD_DIR}")
