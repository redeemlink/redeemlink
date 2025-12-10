import os
import logging
import feedparser
from pathlib import Path
from datetime import datetime
import shutil
import re
import subprocess
from dotenv import load_dotenv

load_dotenv()

class LocalAstroDevServer:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback or print
        self.rss_query = os.getenv("RSS_QUERY", "technology")
        # Ensure the Astro content directory exists
        self.astro_posts_dir = Path("astro-site/src/content/posts")

    def _run_command(self, command, error_message, cwd=None):
        process = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=cwd)
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
        
        self.astro_posts_dir.mkdir(parents=True, exist_ok=True) # Ensure target exists

        for item in items:
            title = item.title.replace('"', '')
            link = item.link
            
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

            content = f"---\ntitle: \"{title}\"\ndate: {pub_date.isoformat()}\nlink: \"{link}\" \n---\n\n{item.summary}\n\n[Read full story →]({link})\n"
            filename.write_text(content, encoding="utf-8")
        
        # Copy generated posts to Astro's content directory
        if self.astro_posts_dir.exists():
            shutil.rmtree(self.astro_posts_dir)
        shutil.copytree(temp_posts_dir, self.astro_posts_dir)
        self.status_callback(f"Generated and copied {len(items)} posts to {self.astro_posts_dir}")

    def start_dev_server(self):
        self.status_callback("Starting Astro development server...")
        # Use Popen to run the dev server in the background and not block
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd="astro-site",
            shell=True # Use shell=True for Windows compatibility with npm commands
        )
        self.status_callback(f"Astro dev server started. Visit http://localhost:4321 (or the address shown by Astro). Press Ctrl+C in this terminal to stop.")
        
        # Keep the script alive while the server runs
        try:
            process.wait()
        except KeyboardInterrupt:
            self.status_callback("Stopping Astro dev server...")
            process.terminate()
            process.wait()
            self.status_callback("Astro dev server stopped.")

    def run(self):
        self.status_callback("Preparing Astro local development environment...")
        try:
            self.status_callback("Fetching Google News...")
            news_items = self.fetch_google_news()

            self.status_callback("Generating and copying posts for Astro...")
            self.generate_posts_for_astro(news_items)

            self.start_dev_server()

        except Exception as e:
            logging.error(f"Error during local dev server setup: {e}", exc_info=True)
            self.status_callback(f"Error: {e}")
            raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dev_server = LocalAstroDevServer()
    dev_server.run()
