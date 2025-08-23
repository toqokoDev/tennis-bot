from datetime import datetime
from utils.json_data import load_users, write_users

# ---------- Вспомогательные функции для работы с играми ----------
def get_user_games(user_id: int) -> list:
    """Получить массив игр пользователя"""
    users = load_users()
    user_data = users.get(str(user_id)), {}
    return user_data.get('games', [])

def save_user_game(user_id: int, game_data: dict) -> None:
    """Сохранить новую игру пользователя"""
    users = load_users()
    user_key = str(user_id)
    
    if user_key not in users:
        return
    
    if 'games' not in users[user_key]:
        users[user_key]['games'] = []
    
    # Добавляем ID и timestamp для игры
    game_data['id'] = len(users[user_key]['games']) + 1
    game_data['created_at'] = datetime.now().isoformat(timespec="seconds")
    game_data['active'] = True
    
    users[user_key]['games'].append(game_data)
    write_users(users)

    return game_data['id']

def update_user_game(user_id: int, game_id: int, updates: dict) -> None:
    """Обновить данные игры"""
    users = load_users()
    user_key = str(user_id)
    
    if user_key not in users or 'games' not in users[user_key]:
        return
    
    for i, game in enumerate(users[user_key]['games']):
        if game.get('id') == game_id:
            users[user_key]['games'][i].update(updates)
            break
    
    write_users(users)

def deactivate_user_game(user_id: int, game_id: int) -> None:
    """Деактивировать игру"""
    update_user_game(user_id, game_id, {'active': False})
