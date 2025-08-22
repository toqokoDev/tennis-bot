import os
import json
from config.paths import SESSIONS_DIR


def save_session(user_id: int, data: dict) -> None:
    session_file = SESSIONS_DIR / f"{user_id}.json"
    with open(session_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_session(user_id: int) -> dict:
    session_file = SESSIONS_DIR / f"{user_id}.json"
    if not session_file.exists():
        return {}
    with open(session_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def delete_session(user_id: int) -> None:
    session_file = SESSIONS_DIR / f"{user_id}.json"
    if session_file.exists():
        os.remove(session_file)
