from datetime import datetime
from services.storage import storage

# ---------- Вспомогательные функции для работы с играми ----------
async def get_user_games(user_id: int) -> list:
    """Получить массив игр пользователя"""
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    return user_data.get('games', [])

async def save_user_game(user_id: int, game_data: dict) -> None:
    """Сохранить новую игру пользователя"""
    users = await storage.load_users()
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
    await storage.save_users(users)

    return game_data['id']

async def update_user_game(user_id: int, game_id: int, updates: dict) -> None:
    """Обновить данные игры"""
    users = await storage.load_users()
    user_key = str(user_id)
    
    if user_key not in users or 'games' not in users[user_key]:
        return
    
    for i, game in enumerate(users[user_key]['games']):
        if game.get('id') == game_id:
            users[user_key]['games'][i].update(updates)
            break
    
    await storage.save_users(users)

async def deactivate_user_game(user_id: int, game_id: int) -> None:
    """Деактивировать игру"""
    await update_user_game(user_id, game_id, {'active': False})
