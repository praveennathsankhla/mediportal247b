"""
MediPortal247 — Push to GitHub Helper
Usage:
    .\\venv\\Scripts\\python.exe push_to_github.py https://github.com/<username>/mediportal247.git
    
Or with Personal Access Token (PAT):
    .\\venv\\Scripts\\python.exe push_to_github.py https://<your_token>@github.com/<username>/mediportal247.git
"""
import sys
from dulwich import porcelain
from dulwich.repo import Repo

def main():
    if len(sys.argv) < 2:
        print("Error: Missing repository URL.")
        print("Usage: .\\venv\\Scripts\\python.exe push_to_github.py https://github.com/<username>/mediportal247.git")
        sys.exit(1)

    url = sys.argv[1].strip()
    repo = Repo(".")
    
    # Configure remote
    try:
        porcelain.remote_add(repo, "origin", url)
        print(f"Added remote origin: {url}")
    except Exception:
        # If origin exists, update it
        config = repo.get_config()
        config.set(("remote", "origin"), "url", url.encode("utf-8"))
        config.write_to_path()
        print(f"Updated remote origin: {url}")

    print("Pushing 'main' branch to GitHub...")
    try:
        porcelain.push(repo, "origin", refspecs=[b"refs/heads/main:refs/heads/main"])
        print("Successfully pushed to GitHub!")
    except Exception as e:
        print(f"Push failed: {e}")
        print("\nTip: For private repositories or GitHub 2FA, use a Personal Access Token:")
        print("https://<your_token>@github.com/<username>/mediportal247.git")

if __name__ == "__main__":
    main()
