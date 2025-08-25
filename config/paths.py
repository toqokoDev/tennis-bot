from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"
GAMES_FILE = DATA_DIR / 'games.json'
BANNED_USERS_FILE = DATA_DIR / 'banned_users.json'
PHOTOS_DIR = DATA_DIR / "user_photos"
SESSIONS_DIR = DATA_DIR / "sessions"
GAMES_PHOTOS_DIR = DATA_DIR / "games_photo"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
GAMES_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
