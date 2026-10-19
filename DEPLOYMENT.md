# MediPortal247 — Deployment & Publishing Guide

This guide covers both **instant live public access** and **permanent cloud deployment** (Render, Railway, Docker, VPS).

---

## 1. Instant Live Public Access (Available Right Now)

Your local instance is already published and accessible over public HTTPS on the internet:

* **Live Public URL**: [https://ugly-rat-63.loca.lt](https://ugly-rat-63.loca.lt)
* **First-Visit Password**: `157.48.242.228`  
  *(When opening the link, localtunnel displays a one-time anti-abuse verification box. Enter `157.48.242.228` and click "Click to Submit" to view the full website).*

---

## 2. Deploy to Cloud (Render.com — Recommended Free Hosting)

[Render.com](https://render.com) offers free cloud hosting for Python web apps. A pre-configured `render.yaml` blueprint has been included in the repository.

### Steps:
1. **Push your repository to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "MediPortal247 Movie Hub initial release"
   git branch -M main
   git remote add origin https://github.com/<your-username>/mediportal247.git
   git push -u origin main
   ```
2. **Connect to Render**:
   - Go to [dashboard.render.com](https://dashboard.render.com) and log in.
   - Click **New +** > **Web Service**.
   - Select your GitHub repository.
3. **Configure Service**:
   - **Name**: `mediportal247`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python webapp.py`
   - **Plan**: `Free`
4. Click **Create Web Service**. Render will build and deploy your site with a free `https://mediportal247.onrender.com` SSL domain.

---

## 3. Deploy to Railway.app

[Railway.app](https://railway.app) provides instantaneous deployments with support for Docker and Python Procfiles:

1. Go to [railway.app](https://railway.app) and click **Start a New Project**.
2. Select **Deploy from GitHub repo**.
3. Choose your repository.
4. Railway will automatically detect the included `Dockerfile` and `Procfile`.
5. Under service settings, click **Generate Domain** to get a public HTTPS URL.

---

## 4. Deploy with Docker (Any VPS / Ubuntu Server)

A multi-stage production `Dockerfile` and `.dockerignore` are included in the project root.

### Build and Run:
```bash
# Build the Docker image
docker build -t mediportal247 .

# Run the container in background on port 8000
docker run -d \
  --name mediportal247 \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --restart always \
  mediportal247
```

To run with Nginx reverse proxy and custom domain:
```nginx
server {
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 5. Production Configuration Summary

| Component | Setting |
| :--- | :--- |
| **App Entrypoint** | `webapp.py` (reads `$PORT` and `$HOST` environment variables automatically) |
| **Dependencies** | Listed in `requirements.txt` (`Flask`, `waitress`, `gunicorn`, etc.) |
| **Catalog Database** | `data/movies.json` (16,851 movies pre-loaded into memory with O(1) lookups) |
| **Poster Storage** | `data/thumbnails/` (17,384 local images delivered via `/thumbnails/<name>`) |
| **Pagination** | 20 movies per page strictly maintained |
| **Sorting** | Recent releases (2026/2025/2024) dynamically blended with top IMDb-rated titles |
