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
            raise Exception(f"{error_message}. See logs for details. STDOUT: {process.stdout}")
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
        
        astro_posts_dir = Path("astro-site/src/content/blog")
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

            content = f"---\ntitle: \"{title}\"\ndescription: \"{description}\"\npubDate: {pub_date.isoformat()}\nlink: \"{link}\" \n---\n\n{summary}\n\n[Read full story →]({link})\n"
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
        self.status_callback("Deploying to GitHub Pages using Git...")

        temp_deploy_dir = Path("temp_gh_pages_deploy")
        if temp_deploy_dir.exists():
            shutil.rmtree(temp_deploy_dir)
        temp_deploy_dir.mkdir()

        repo_url = f"https://github.com/{self.repo}.git"
        auth_repo_url = f"https://oauth2:{self.github_token}@github.com/{self.repo}.git"
        branch_name = "gh-pages"

        cname_content = None
        sitemap_content = None

        try:
            # Try cloning gh-pages branch
            self.status_callback(f"Attempting to clone '{branch_name}' branch...")
            self._run_command(f"git clone --branch {branch_name} --single-branch {auth_repo_url} {temp_deploy_dir}",
                              f"Failed to clone '{branch_name}' branch directly.",
                              cwd=Path("."))
            self.status_callback(f"Cloned existing '{branch_name}' branch.")

            # Preserve CNAME and sitemap.xml if they exist in the cloned branch
            cname_path_cloned = temp_deploy_dir / "CNAME"
            if cname_path_cloned.exists():
                cname_content = cname_path_cloned.read_text(encoding="utf-8")
                self.status_callback("Preserving existing CNAME file.")

            sitemap_path_cloned = temp_deploy_dir / "sitemap.xml"
            if sitemap_path_cloned.exists():
                sitemap_content = sitemap_path_cloned.read_text(encoding="utf-8")
                self.status_callback("Preserving existing sitemap.xml file.")

        except Exception as e:
            self.status_callback(f"'{branch_name}' branch might not exist or another cloning error occurred: {e}")
            self.status_callback(f"Cloning 'main' branch and creating '{branch_name}'...")
            if temp_deploy_dir.exists():
                shutil.rmtree(temp_deploy_dir)
            temp_deploy_dir.mkdir()

            self._run_command(f"git clone --single-branch {auth_repo_url} {temp_deploy_dir}",
                              "Failed to clone 'main' branch.",
                              cwd=Path("."))
            self._run_command(f"git checkout -b {branch_name}", f"Failed to create {branch_name} branch.", cwd=temp_deploy_dir)
            self._run_command(f"git push -u origin {branch_name}", f"Failed to push new {branch_name} branch.", cwd=temp_deploy_dir)
            self.status_callback(f"Created and pushed new '{branch_name}' branch.")
            # No CNAME or sitemap.xml to preserve if the branch was just created

        # Clear existing content in the temporary deployment directory (except .git)
        self.status_callback("Cleaning temporary deployment directory (excluding .git)...")
        for item in temp_deploy_dir.iterdir():
            if item.name != ".git":
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        # Copy new build files to the temporary deployment directory
        self.status_callback("Copying new build files from astro-site/dist...")
        public_dir = Path("astro-site") / "dist"
        if not public_dir.is_dir():
            raise FileNotFoundError("Astro distribution directory not found. Build may have failed.")
        
        for item in public_dir.iterdir():
            if item.is_dir():
                shutil.copytree(item, temp_deploy_dir / item.name, dirs_exist_ok=True)
            else:
                shutil.copy2(item, temp_deploy_dir / item.name)

        # Restore preserved CNAME and sitemap.xml files
        if cname_content:
            (temp_deploy_dir / "CNAME").write_text(cname_content, encoding="utf-8")
            self.status_callback("Restored CNAME file.")
        elif self.domain: # Only create CNAME if not preserved and domain is set
            (temp_deploy_dir / "CNAME").write_text(self.domain.strip(), encoding="utf-8")
            self.status_callback(f"Created CNAME file with domain: {self.domain}")

        if sitemap_content:
            (temp_deploy_dir / "sitemap.xml").write_text(sitemap_content, encoding="utf-8")
            self.status_callback("Restored sitemap.xml file.")


        # Git operations: add, commit, force push
        self.status_callback("Staging, committing, and pushing changes...")
        self._run_command("git add .", "Failed to stage files for commit.", cwd=temp_deploy_dir)
        self._run_command('git config user.name "Astro Deploy Bot"', "Failed to set git user name.", cwd=temp_deploy_dir)
        self._run_command('git config user.email "deploy-bot@example.com"', "Failed to set git user email.", cwd=temp_deploy_dir)
        
        try:
            self._run_command("git commit -m 'Deploy Astro site'", "Failed to commit changes.", cwd=temp_deploy_dir)
        except Exception as e:
            if "nothing to commit, working tree clean" in str(e):
                self.status_callback("No changes detected in the build output. Skipping commit and push.")
                shutil.rmtree(temp_deploy_dir)
                return
            else:
                raise

        self._run_command(f"git push --force origin {branch_name}", f"Failed to force push to {branch_name} branch.", cwd=temp_deploy_dir)
        self.status_callback("Successfully deployed to GitHub Pages!")

        # Clean up temporary directory
        shutil.rmtree(temp_deploy_dir)
