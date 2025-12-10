import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QInputDialog, QLabel, QMessageBox, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Import the refactored logic
from astro_deploy_logic import AstroDeployer

load_dotenv()

class Worker(QThread):
    """
    Runs the deployment logic in a separate thread to keep the GUI responsive.
    It emits signals to update the UI.
    """
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        # The worker creates the deployer and uses its own signal emitter as the callback
        self.deployer = AstroDeployer(status_callback=self.status.emit)

    def run(self):
        try:
            self.deployer.run()
        except Exception as e:
            logging.error(f"Error in worker thread: {e}", exc_info=True)
            self.status.emit(f"Error: {e}")
        finally:
            self.finished.emit()

class GoogleNewsAstroBlaster(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Google News Astro Blaster Pro 2025")
        self.setFixedSize(520, 400)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # Configuration and setup
        if not all([os.getenv("GITHUB_TOKEN"), os.getenv("REPO"), os.getenv("DOMAIN")]):
            self.first_time_setup()
        

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.publish_btn = QPushButton("PUBLISH GOOGLE NEWS SITE NOW!")
        self.publish_btn.setStyleSheet("font-size: 18pt; font-weight: bold; padding: 25px;")
        self.publish_btn.clicked.connect(self.start_worker)
        layout.addWidget(self.publish_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

    def first_time_setup(self):
        token, ok = QInputDialog.getText(self, "GitHub Token", "Enter GitHub Token (repo scope):")
        if not ok or not token: sys.exit()
        repo, ok = QInputDialog.getText(self, "Repo", "Enter repo (username/repo):")
        if not ok or not repo: sys.exit()
        domain, ok = QInputDialog.getText(self, "Custom Domain", "Your domain (e.g., my-news.com):")
        if not ok or not domain: sys.exit()
        query, ok = QInputDialog.getText(self, "News Topic", "Topic (e.g. technology):", text="technology")
        if not ok: query = "technology"

        env_content = f"GITHUB_TOKEN={token}\nREPO={repo}\nDOMAIN={domain}\nRSS_QUERY={query}\n"
        Path(".env").write_text(env_content)
        load_dotenv()
        self.set_status("Config saved in .env! Ready to publish.")

    def set_status(self, text):
        # Determine message level from text content for coloring
        level = "info"
        if text.startswith("Error:"):
            level = "error"
        elif text.startswith("DONE!"):
            level = "success"

        colors = {"success": "green", "error": "red", "info": "white"}
        self.status_label.setStyleSheet(f"color: {colors.get(level)}; font-weight: bold;")
        self.status_label.setText(text)

    def start_worker(self):
        # Verify configuration before starting the worker thread
        try:
            AstroDeployer() 
        except ValueError as e:
            QMessageBox.critical(self, "Configuration Error", str(e))
            return

        self.publish_btn.setEnabled(False)
        self.progress.setVisible(True)
        
        self.worker = Worker()
        self.worker.status.connect(self.set_status)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_finished(self):
        self.publish_btn.setEnabled(True)
        self.progress.setVisible(False)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, filename='app.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')
    app = QApplication(sys.argv)
    
    app.setStyleSheet("""
        QWidget { background-color: #1e1e1e; color: #ffffff; font-family: Segoe UI; }
        QPushButton { background-color: #0d6efd; padding: 15px; border-radius: 8px; font-weight: bold; }
        QPushButton:hover { background-color: #0b5ed7; }
        QProgressBar { border: 2px solid #444; border-radius: 5px; text-align: center; }
        QProgressBar::chunk { background-color: #0d6efd; }
        QLabel { font-size: 11pt; }
    """)
    
    window = GoogleNewsAstroBlaster()
    window.show()
    sys.exit(app.exec())
