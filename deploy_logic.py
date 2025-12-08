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

class HugoDeployer:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback or print
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.repo = os.getenv("REPO")
        self.domain = os.getenv("DOMAIN")
        self.rss_query = os.getenv("RSS_QUERY", "technology")
        self.hugo_exec_path = os.getenv("HUGO_EXEC_PATH")

        if not all([self.github_token, self.repo, self.domain, self.hugo_exec_path]):
            raise ValueError("Missing required environment variables. Check your .env file.")

    def run(self):
        try:
            self.status_callback("Fetching Google News...")
            news_items = self.fetch_google_news()

            self.status_callback("Generating Hugo posts...")
            self.generate_hugo_posts(news_items)

            self.status_callback("Building Hugo site...")
            self.build_hugo_site()

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

    def generate_hugo_posts(self, items):
        posts_dir = Path("content/posts")
        posts_dir.mkdir(parents=True, exist_ok=True)
        
        for item in items:
            title = item.title.replace('"', '')
            link = item.link
            summary = item.summary if hasattr(item, "summary") else ""
            
            slug = "".join(c for c in title if c.isalnum() or c in " - ")[:60].strip().lower()
            slug = slug.replace(" ", "-")
            filename = posts_dir / f"{slug}.md"
            
            if filename.exists():
                continue

            content = f"""
---
title: "{title}"
date: {datetime.now().isoformat()}
link: "{link}" 
---

{summary}

[Read full story →]({link})
"""
            filename.write_text(content, encoding="utf-8")

    def build_hugo_site(self):
        self.status_callback("Initializing/Updating Hugo site...")
        hugo_site_path = Path("hugo-site")
        
        config_file = hugo_site_path / "hugo.toml"

        if not hugo_site_path.is_dir():
            self._run_command(f'new site "{hugo_site_path.name}"', "Failed to create new Hugo site.", is_hugo_command=True)
            
        ananke_theme_path = hugo_site_path / "themes" / "ananke"
        
        if ananke_theme_path.is_dir():
            self.status_callback("Ananke theme found. Updating...")
            self._run_command('git pull', "Failed to update Ananke theme.", cwd=ananke_theme_path)
        else:
            self.status_callback("Cloning Ananke theme...")
            self._run_command('git clone https://github.com/theNewDynamic/gohugo-theme-ananke.git themes/ananke', "Failed to clone Ananke theme.", cwd=hugo_site_path)
        
        if not config_file.exists():
             config_file.write_text("baseURL = 'https://example.org/'\nlanguageCode = 'en-us'\ntitle = 'My New Hugo Site'\n")
             self.status_callback(f"Created default Hugo config file: {config_file}")

        config_content = config_file.read_text()
        
        if not re.search(r'theme\s*=', config_content):
            config_content += '\ntheme = "ananke"\n'

        base_url_value = f"https://{self.domain}/"
        if re.search(r'baseURL\s*=', config_content):
            config_content = re.sub(r'baseURL\s*=\s*["\'].*?["\']', f'baseURL = "{base_url_value}"', config_content)
        else:
            config_content += f'\nbaseURL = "{base_url_value}"\n'
            
        config_file.write_text(config_content)
            
        index_path = hugo_site_path / "content" / "_index.md"
        if not index_path.exists():
            index_path.write_text("---\ntitle: \"Home\"\n---\n\nWelcome to our news site!", encoding="utf-8")
            
        layout_path = hugo_site_path / "layouts" / "index.html"
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        if not layout_path.exists():
            layout_path.write_text("""<!DOCTYPE html>
<html><head><title>{{ .Site.Title }}</title><style>body { font-family: sans-serif; line-height: 1.6; margin: 2em; } ul { list-style-type: none; padding: 0; } li { margin-bottom: 1.5em; } a { text-decoration: none; color: #0056b3; } a:hover { text-decoration: underline; }</style></head>
<body><h1>Welcome to {{ .Site.Title }}</h1><h2>Latest News</h2><ul>{{ range .Site.RegularPages.ByDate.Reverse | first 20 }}<li><h3><a href="{{ .Permalink }}">{{ .Title }}</a></h3><p>{{ .Summary }} <a href="{{ .Permalink }}">Read more...</a></p></li>{{ end }}</ul></body></html>""", encoding="utf-8")
            
hugo_posts_dir = hugo_site_path / "content" / "posts"
        if hugo_posts_dir.exists():
            shutil.rmtree(hugo_posts_dir)
        shutil.copytree("content/posts", hugo_posts_dir)

        self.status_callback("Building Hugo site...")
        self._run_command(f'--gc --cleanDestinationDir', "Failed to build Hugo site.", cwd=hugo_site_path, is_hugo_command=True)
        self.status_callback("Hugo site built successfully!")

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

        public_dir = Path("hugo-site") / "public"
        if not public_dir.is_dir():
            raise FileNotFoundError("Hugo public directory not found. Build may have failed.")
        
        uploadable_files = [f for f in public_dir.rglob("*") if f.is_file()]
        
        for i, file_path in enumerate(uploadable_files):
            relative_path = file_path.relative_to(public_dir).as_posix()
            self.status_callback(f"Uploading {relative_path} ({i+1}/{len(uploadable_files)})...")
            
            content_b64 = base64.b64encode(file_path.read_bytes()).decode("utf-8")
            contents_url = f"{repo_api_url}/contents/{relative_path}"
            
            sha = None
            try:
                # Use params for query string, not in URL directly
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
