# MediPortal247 Scraper and Catalogue

A command-line scraper for collecting movie and series metadata, poster thumbnails, and page information from an authorized site. It uses direct HTTP requests by default for speed, with Selenium available as a browser-rendered fallback. Results are saved to JSON and CSV, with a checkpoint for normal forward runs.

> Scraping a website may be restricted by its terms of service or local law. Check the site's rules and `robots.txt`, use a responsible request delay, and only use this project where you have permission.

## Features

- Scrape catalogue pages and movie/series posts.
- Save structured records to `data/movies.json` and spreadsheet-friendly rows to `data/movies.csv`.
- Download poster thumbnails to `data/thumbnails/`.
- Resume normal forward scraping from the saved page and skip URLs already recorded.
- Scrape an inclusive page range in forward or reverse page order.
- Split a bounded page range across multiple independent workers.
- Fast direct-HTTP scraping by default; use Selenium when a page requires browser rendering.
- Limit the number of new records in a run and configure the delay between movie requests.
- Run Chrome headless by default or show browser windows for troubleshooting.

## Requirements

- Python 3.10 or newer
- Python dependencies from `requirements.txt`
- A supported browser only when using `--transport browser`: Chrome, Edge, or Firefox
- Internet access

Selenium Manager in Selenium 4 manages the matching browser driver when the scraper starts. Install each browser you plan to use with browser transport.

## Installation

Clone or download this repository, then open a terminal in the project folder.

### Windows (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell prevents activation, run the commands using `.\.venv\Scripts\python.exe` instead of activating the environment.

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Quick start

Start or resume normal forward scraping:

```bash
python main.py
```

Direct HTTP is used by default, so Chrome is not needed for normal runs. Stop with `Ctrl+C`; completed records are saved as the scraper runs. Start the same command again to resume.

## Command-line options

```text
python main.py [options]

--transport MODE     http (fast, default) or browser (Selenium)
--headless           Run selected browser(s) without visible windows (default)
--no-headless        Show selected browser windows
--start-page N       First page in the selected range (inclusive)
--end-page N         Last page in the selected range (inclusive)
--reverse            Traverse the selected page range from high to low
--browsers N         Number of parallel workers/browser instances (default: 1)
--browser N          Alias for --browsers
--instances N        Alias for --browsers
--browser-types LIST Browser per instance: chrome,firefox,edge (default: chrome)
--limit N            Stop after N new movies/series have been saved
--delay SECONDS      Base delay between movie requests (default: 0.5)
--reset              Remove the saved page checkpoint before starting
-h, --help           Show all options
```

### Examples

Scrape pages 10 through 20 in normal ascending order:

```bash
python main.py --start-page 10 --end-page 20
```

Scrape the same inclusive range from page 20 down to page 10:

```bash
python main.py --start-page 10 --end-page 20 --reverse
```

Divide pages 1 through 100 between four browser instances:

```bash
python main.py --start-page 1 --end-page 100 --browsers 4
```

HTTP mode (default) uses the same number of instances as concurrent HTTP workers. No browser processes or drivers are started:

```powershell
python main.py --start-page 99 --end-page 200 --browser 4 --delay 0.5
```

Use Selenium only if the site requires JavaScript-rendered content:

```bash
python main.py --transport browser --start-page 1 --end-page 20 --browsers 2
```

Use Chrome, Firefox, and Edge for three separate page-range workers:

```bash
python main.py --transport browser --start-page 1 --end-page 100 --browsers 3 --browser-types chrome,firefox,edge
```

Run two instances using Firefox for both:

```bash
python main.py --transport browser --start-page 1 --end-page 100 --browsers 2 --browser-types firefox
```

Show the Selenium browser while scraping a small range:

```bash
python main.py --transport browser --start-page 1 --end-page 3 --no-headless
```

Stop after 50 new records and use a longer delay:

```bash
python main.py --limit 50 --delay 5
```

## MediPortal247 Movie Download Website

Start the responsive movie download website:

```powershell
.\venv\Scripts\python.exe webapp.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

### Features
- **Inspired by BollyFlix, VegaMovies, and Movies4u**: Modern dark cinematic UI with neon cyan, gold, and emerald highlights.
- **Uses Every Piece of Data**: Full movie metadata, technical specs, storyline, YouTube trailer player, post screenshots gallery with fullscreen lightbox, and structured download tiers (Google Drive, Fast Cloud, Download Links).
- **Strictly 20 Movies Per Page**: Clean pagination bar with Prev/Next, numbered links, and direct page jump.
- **Fast Navigation & Categories**: Quick pills and navbar filters for Bollywood, Hollywood, Dual Audio, Web Series, South Dubbed, and 4K Ultra HD.
- **Instant Search & Autocomplete**: Real-time dropdown preview showing poster, title, year, quality, and IMDb rating as you type.
- **Local Poster Serving**: 17,380+ local thumbnail images served directly from `data/thumbnails/` with HTTP caching and remote fallback.
- **Deep Linking**: Direct URLs for individual movies (`/movie/<id>`) and bookmarkable filter states.

### Page ranges and parallel browsers

Page numbers are inclusive. `--start-page` defaults to the saved resume page for a normal, unbounded forward run. When `--reverse` is set and no start page is supplied, the range begins at page 1; provide `--end-page` to set its upper bound.

Reverse scraping and multiple workers require `--end-page`. The scraper divides the selected range into contiguous, non-overlapping chunks. Each worker traverses its own chunk in the selected direction. Since workers run concurrently, the overall completion order across chunks is not guaranteed to be strictly descending or ascending.

Use a bounded range when running multiple instances. More workers can increase load on both your computer and the website; choose a modest number and a responsible `--delay`. In HTTP mode, each instance is a lightweight HTTP worker. `--browser-types` applies only to Selenium browser transport; it accepts one browser name (used for every browser instance) or one comma-separated name per instance. Supported names are `chrome`, `firefox`, and `edge`. Each selected browser must be installed on the machine.

### Resume and reset

A normal run without page-range options resumes from the page stored in `data/state.json` and skips URLs already present in the saved records. Explicit page ranges are useful for targeted runs and do not update the normal resume page checkpoint.

`--reset` removes the saved state checkpoint. It does not delete `movies.json`, `movies.csv`, or thumbnails; URLs already present in `movies.json` remain recognized as scraped.

## Output files

```text
data/
├── movies.json       # Structured records, including nested download links
├── movies.csv        # Flat, spreadsheet-friendly records
├── state.json        # Resume checkpoint and scraped URL list
├── attempted_urls.json # URLs claimed for scraping; prevents duplicate attempts
├── scraper.lock      # Cross-process persistence lock
└── thumbnails/       # Downloaded poster images
```

The output directory is created automatically. Scraper workers, separate scraper processes, and the local catalogue website sharing this `data` directory coordinate through the lock and URL ledger, so each movie URL is claimed at most once across page ranges and runs.

For strict at-most-once behavior, a URL is recorded in `attempted_urls.json` before scraping begins. If the process exits or scraping fails after the URL is claimed, it will be skipped on later runs rather than attempted a second time. This ledger is intentionally preserved by `--reset`; remove it manually only if you explicitly want to allow previously attempted URLs to be scraped again.

## Collected fields

The scraper records available information from each post, including:

- Title, post URL, and publication date
- IMDb rating, URL, genres, summary, director, writer, and stars when available
- Movie/series name, language, release year, size, quality, source, genres, cast, format, and subtitles
- Storyline, trailer URL, and embedded sample-image URLs
- Download tiers and their links
- Poster URL, local thumbnail path, and scrape timestamp

Some fields may be empty when the source page does not provide them or the page structure changes.

## Troubleshooting

- **HTTP requests fail:** Check network access, the URL, and whether the site is responding. HTTP requests are retried with a short backoff.
- **Windows reports access denied replacing `movies.json`:** Writes retry temporary sharing violations while the website and scraper coordinate through `data/scraper.lock`. If another program still holds the file, close duplicate scraper processes or JSON editors; the error reports the preserved temporary recovery file.
- **Browser driver fails to start:** Confirm that the selected browser is installed and that Selenium Manager can download/find its matching driver.
- **Browser renderer times out:** Switch to the default HTTP transport if the site can be read without JavaScript. Otherwise reduce the number of Selenium instances and increase `--delay`.
- **No posts are found:** Check network access and whether the catalogue is reachable; the site's page structure or URLs may have changed.
- **Need to inspect browser behavior:** Retry with `--no-headless`.
- **Scraping too quickly:** Increase `--delay`, for example `--delay 5`.

## License

No license is currently specified. Add a `LICENSE` file before redistributing this project if you intend to grant others permission to use, modify, or distribute it.
