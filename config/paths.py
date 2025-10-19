from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"
GAMES_FILE = DATA_DIR / 'games.json'
BANNED_USERS_FILE = DATA_DIR / 'banned_users.json'
PHOTOS_DIR = DATA_DIR / "user_photos"
SESSIONS_DIR = DATA_DIR / "sessions"
GAMES_PHOTOS_DIR = DATA_DIR / "games_photo"
TOURNAMENTS_FILE = DATA_DIR / "tournaments.json"
TOURNAMENT_APPLICATIONS_FILE = DATA_DIR / "tournament_applications.json"
BEAUTY_CONTEST_FILE = DATA_DIR / "beauty_contest.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
GAMES_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
