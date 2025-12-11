import os
import logging
import base64
import requests
import feedparser
from pathlib import Path
from datetime import datetime
import subprocess
import shutil
import re
from dotenv import load_dotenv

load_dotenv()

class AstroDeployer:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback or print
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.repo = os.getenv("REPO")
        self.domain = os.getenv("DOMAIN")
        self.rss_query = os.getenv("RSS_QUERY", "technology")

        missing_vars = []
        if not self.github_token:
            missing_vars.append("GITHUB_TOKEN (from secret EXTERNAL_REPO_PAT)")
        if not self.repo:
            missing_vars.append("REPO (from secret EXTERNAL_REPO_NAME)")
        if not self.domain:
            missing_vars.append("DOMAIN (from secret DOMAIN)")

        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}. Check your repository secrets and local .env file.")

    def run(self):
        try:
            self.status_callback("Fetching Google News...")
            news_items = self.fetch_google_news()

            self.status_callback("Generating posts for Astro...")
            self.generate_posts_for_astro(news_items)

            self.status_callback("Building Astro site...")
            self.build_astro_site()

            self.status_callback("Deploying to GitHub Pages...")
            self.deploy_to_github()

            self.status_callback("DONE! Google News live on your domain!")
        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            self.status_callback(f"Error: {e}")
            raise 

    def _run_command(self, command, error_message, cwd=None, is_hugo_command=False):
        if is_hugo_command:
            full_command = f'"{self.hugo_exec_path}" {command}'
        else:
            full_command = command

        process = subprocess.run(full_command, shell=True, capture_output=True, text=True, cwd=cwd)
        if process.returncode != 0:
            log_message = f"{error_message}\nStdout: {process.stdout}\nStderr: {process.stderr}"
            logging.error(log_message)
            raise Exception(f"{error_message}. See logs for details.")
        return process.stdout

    def fetch_google_news(self):
        url = f"https://news.google.com/rss/search?q={self.rss_query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        return feed.entries[:30]

    def generate_posts_for_astro(self, items):
        # Create a temporary directory for markdown files
        temp_posts_dir = Path("content/posts") # Use the same temp dir as Hugo for consistency during generation
        if temp_posts_dir.exists():
            shutil.rmtree(temp_posts_dir)
        temp_posts_dir.mkdir(parents=True, exist_ok=True)
        
        astro_posts_dir = Path("astro-site/src/content/posts")
        if astro_posts_dir.exists():
            shutil.rmtree(astro_posts_dir) # Clear existing Astro posts
        astro_posts_dir.mkdir(parents=True, exist_ok=True) # Ensure target exists

        def clean_html(raw_html):
            cleanr = re.compile('<.*?>')
            cleantext = re.sub(cleanr, '', raw_html)
            return cleantext

        for item in items:
            title = item.title.replace('"', '')
            link = item.link
            summary = item.summary if hasattr(item, 'summary') else ''
            description = clean_html(summary).replace('"', '\\"').strip()[:155] + '...'
            
            # Use publish_date if available, otherwise current date
            pub_date = datetime.now()
            if hasattr(item, 'published_parsed'):
                try:
                    pub_date = datetime(*item.published_parsed[:6])
                except Exception:
                    pass # Fallback to now() if parsing fails

            slug = "".join(c for c in title if c.isalnum() or c in " - ")[:60].strip().lower()
            slug = slug.replace(" ", "-")
            filename = temp_posts_dir / f"{slug}.md"

            content = f"---\ntitle: \"{title}\"\ndescription: \"{description}\"\ndate: {pub_date.isoformat()}\nlink: \"{link}\" \n---\n\n{summary}\n\n[Read full story →]({link})\n"
            filename.write_text(content, encoding="utf-8")
        
        # Copy generated posts to Astro's content directory
        shutil.copytree(temp_posts_dir, astro_posts_dir, dirs_exist_ok=True)
        self.status_callback(f"Generated and copied {len(items)} posts to {astro_posts_dir}")

    def build_astro_site(self):
        self.status_callback("Building Astro site...")
        astro_site_path = Path("astro-site")

        # Ensure npm dependencies are installed
        self.status_callback("Installing Astro dependencies...")
        self._run_command("npm install", "Failed to install Astro dependencies.", cwd=astro_site_path)

        # Build the Astro site
        self.status_callback("Running Astro build...")
        self._run_command("npm run build", "Failed to build Astro site.", cwd=astro_site_path)
        self.status_callback("Astro site built successfully!")

    def deploy_to_github(self):
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        repo_api_url = f"https://api.github.com/repos/{self.repo}"
        
        branches_url = f"{repo_api_url}/branches"
        r = requests.get(branches_url, headers=headers)
        r.raise_for_status()
        if not any(branch["name"] == "gh-pages" for branch in r.json()):
            main_sha = requests.get(f"{branches_url}/main", headers=headers).json()["commit"]["sha"]
            requests.post(f"{repo_api_url}/git/refs", headers=headers, json={"ref": "refs/heads/gh-pages", "sha": main_sha}).raise_for_status()
            self.status_callback("Created gh-pages branch.")

        public_dir = Path("astro-site") / "dist"
        if not public_dir.is_dir():
            raise FileNotFoundError("Astro distribution directory not found. Build may have failed.")
        
        uploadable_files = [f for f in public_dir.rglob("*") if f.is_file()]
        
        for i, file_path in enumerate(uploadable_files):
            relative_path = file_path.relative_to(public_dir).as_posix()
            
            if relative_path == 'sitemap.xml':
                self.status_callback("Skipping sitemap.xml to keep it untouched.")
                continue

            self.status_callback(f"Uploading {relative_path} ({i+1}/{len(uploadable_files)})...")
            
            content_b64 = base64.b64encode(file_path.read_bytes()).decode("utf-8")
            contents_url = f"{repo_api_url}/contents/{relative_path}"
            
            sha = None
            try:
                sha_r = requests.get(contents_url, headers=headers, params={"ref": "gh-pages"})
                if sha_r.status_code == 200:
                    sha = sha_r.json().get("sha")
            except requests.RequestException:
                pass
            
            data = {"message": f"Update site: {relative_path}", "content": content_b64, "branch": "gh-pages"}
            if sha:
                data["sha"] = sha

            put_r = requests.put(contents_url, headers=headers, json=data)
            put_r.raise_for_status()

        self.status_callback(f"Successfully uploaded {len(uploadable_files)} site files to gh-pages branch!")
