import json
from typing import Dict, List
from config.paths import DATA_DIR, USERS_FILE

def save_games(games_data: List):
    with open('data/games.json', 'w', encoding='utf-8') as f:
        json.dump(games_data, f, ensure_ascii=False, indent=2)

def load_games() -> List:
    try:
        with open('data/games.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_users(users_data: Dict):
    with open('data/users.json', 'w', encoding='utf-8') as f:
        json.dump(users_data, f, ensure_ascii=False, indent=2)

def load_json(filename: str):
    path = DATA_DIR / filename
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_users() -> dict:
    if not USERS_FILE.exists():
        USERS_FILE.write_text("{}", encoding="utf-8")
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def write_users(users: dict) -> None:
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

def is_user_registered(user_id: int) -> bool:
    users = load_users()
    return str(user_id) in users

def save_user_to_json(user_id: int, user_data: dict) -> None:
    users = load_users()
    users[str(user_id)] = user_data
    write_users(users)

def get_user_profile_from_storage(user_id: int) -> dict | None:
    users = load_users()
    return users.get(str(user_id))
