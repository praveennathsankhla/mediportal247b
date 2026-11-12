# ⚡ Cloudflare Deployment Guide (1-Click & Zero-Maintenance)

MediPortal247 is an optimized movie catalogue with **16,851 verified titles**, multi-part Google Sitemaps, rich Schema.org metadata, and responsive VegaMovies/BollyFlix style UI.

Since this application runs on Python (Flask backend serving JSON endpoints & dynamic HTML pages), here are the two recommended ways to connect and publish via Cloudflare from your GitHub repository.

---

## Option 1: Cloudflare Tunnel (`cloudflared`) — 100% Free, Zero Hosting Bill

Connect your local server or any VPS directly to your Cloudflare domain without opening any router ports or configuring SSL certificates.

### Step 1: Install `cloudflared`
- **Linux (Ubuntu/Debian):**
  ```bash
  curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  sudo dpkg -i cloudflared.deb
  ```

### Step 2: One-Click Quick Tunnel (Instant Public HTTPS)
Run the webapp:
```bash
python3 webapp.py --port 8000
```
In another terminal, start the Cloudflare tunnel:
```bash
cloudflared tunnel --url http://localhost:8000
```
Cloudflare will instantly print a secure, worldwide HTTPS link (e.g. `https://xxxx-yyyy-zzzz.trycloudflare.com`).

### Step 3: Connect Your Custom Domain (Zero Trust Dashboard)
1. Go to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/) > **Networks** > **Tunnels**.
2. Click **Create a Tunnel** (Name: `mediportal247`).
3. Select your OS and run the connector command.
4. Under **Public Hostname**, configure:
   - **Subdomain / Domain**: `movies.yourdomain.com` (or root domain)
   - **Service Type**: `HTTP`
   - **URL**: `localhost:8000`
5. Save. Your site is live worldwide behind Cloudflare's edge CDN, DDoS protection, and SSL!

---

## Option 2: 1-Click Cloud Deployment (Render / Railway / Koyeb) + Cloudflare DNS Proxy

If you want the site to remain online 24/7 in the cloud without keeping your local computer powered on:

### 1. Push Changes to GitHub
Push your cleaned repository directly to GitHub:
```bash
git add .
git commit -m "Optimize catalog, add legal pages, dynamic sitemaps, and Cloudflare config"
git push origin main
```

### 2. Connect to Free Cloud Host (Render / Railway / Koyeb)
- **Render.com**:
  1. Click **New Web Service** -> Connect `mediportal247b` repo.
  2. Build Command: `pip install -r requirements.txt`
  3. Start Command: `python webapp.py`
  4. Instant live URL: `https://mediportal247b.onrender.com`

- **Railway.app**:
  1. Click **New Project** -> **Deploy from GitHub Repo**.
  2. Auto-detects `Dockerfile` and deploys instantly.

### 3. Route Through Cloudflare (Orange Cloud ☁️)
1. In Cloudflare Dashboard, open your domain's **DNS** section.
2. Add a `CNAME` record:
   - **Name**: `@` or `movies`
   - **Target**: `mediportal247b.onrender.com` (or Railway domain)
   - **Proxy status**: **Proxied (Orange Cloud)** 🟧
3. Under **SSL/TLS**, set encryption mode to **Full (strict)**.
4. Under **Caching** > **Cache Rules**, create a rule for static assets:
   - If URI path starts with `/static/` or `/thumbnails/` -> Cache Everything (TTL: 1 month).
   - If URI path is `/sitemap` or `/sitemap-*.xml` -> Cache (TTL: 1 day).

---

## 🗺️ Search Engine Optimization (SEO) & Sitemaps Included

1. **Sitemap Index:** `/sitemap.xml`
   - **Static & Legal Pages:** `/sitemap-pages.xml`
   - **Categories & Genres:** `/sitemap-categories.xml`
   - **All 16,851 Movies in 5,000-url chunks:**
     - `/sitemap-movies-1.xml`
     - `/sitemap-movies-2.xml`
     - `/sitemap-movies-3.xml`
     - `/sitemap-movies-4.xml`
2. **Dedicated Category URLs:**
   - `/category/bollywood`
   - `/category/hollywood`
   - `/category/dual-audio`
   - `/category/web-series`
   - `/category/south-dubbed`
   - `/category/4k`
3. **Dedicated Genre URLs:**
   - `/genre/Action`, `/genre/Comedy`, `/genre/Drama`, `/genre/Sci-Fi`, `/genre/Thriller`, etc.
4. **Dedicated Year URLs:**
   - `/year/2026`, `/year/2025`, `/year/2024`, `/year/2023`, etc.
5. **Important Legal Pages:**
   - `/how-to-download` (Tutorial inspired by VegaMovies & BollyFlix)
   - `/request-movies` (Interactive user request portal)
   - `/dmca` (DMCA notice & takedown safe harbor)
   - `/disclaimer` (Non-hosting entertainment disclaimer)
   - `/about` (Site mission & quality tier standards)
   - `/contact` (Support, compliance & email contacts)
   - `/privacy-policy` (Privacy guidelines)
