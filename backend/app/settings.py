from pathlib import Path


# Central project settings. Keeping these values in one file avoids hidden
# configuration spread across route handlers and services.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "recordings"
DEFAULT_TRANSCRIPT_DIR = PROJECT_ROOT / "transcripts"
DATABASE_PATH = DEFAULT_OUTPUT_DIR / "radiowatch.db"
# Radio Browser API — free, open, no key required.
# https://api.radio-browser.info/
RADIO_BROWSER_FALLBACK_SERVERS = [
    "de1.api.radio-browser.info",
    "nl1.api.radio-browser.info",
    "at1.api.radio-browser.info",
]
RADIO_BROWSER_USER_AGENT = "RadioWatch/2.0 (https://github.com/radiowatch)"

