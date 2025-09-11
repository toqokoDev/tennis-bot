import asyncio
import json
import aiofiles
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging
from contextlib import asynccontextmanager

from config.paths import BANNED_USERS_FILE, GAMES_FILE, SESSIONS_DIR, USERS_FILE, TOURNAMENTS_FILE, TOURNAMENT_APPLICATIONS_FILE

logger = logging.getLogger(__name__)

@dataclass
class StorageConfig:
    users_file: Path = USERS_FILE
    games_file: Path = GAMES_FILE
    banned_file: Path = BANNED_USERS_FILE
    sessions_dir: Path = SESSIONS_DIR
    tournaments_file: Path = TOURNAMENTS_FILE
    tournament_applications_file: Path = TOURNAMENT_APPLICATIONS_FILE

class AsyncJSONStorage:
    def __init__(self, config: StorageConfig = None):
        self.config = config or StorageConfig()
        self._cache = {}
        self._lock = asyncio.Lock()
    
    async def _read_file(self, filepath: Path, default: Any = None) -> Any:
        """Асинхронное чтение файла с кэшированием"""
        try:
            async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content) if content else (default if default is not None else {})
        except FileNotFoundError:
            return default if default is not None else {}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in {filepath}: {e}")
            return default if default is not None else {}
        except Exception as e:
            logger.error(f"Error reading {filepath}: {e}")
            return default if default is not None else {}
    
    async def _write_file(self, filepath: Path, data: Any) -> None:
        """Асинхронная запись файла"""
        try:
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error(f"Error writing to {filepath}: {e}")
            raise
    
    @asynccontextmanager
    async def _transaction(self, filepath: Path, default: Any = None):
        """Контекстный менеджер для атомарных операций"""
        async with self._lock:
            data = await self._read_file(filepath, default)
            yield data
            await self._write_file(filepath, data)
    
    # Users methods
    async def load_users(self) -> Dict[str, Any]:
        """Загрузка всех пользователей"""
        return await self._read_file(self.config.users_file, {})
    
    async def save_users(self, users_data: Dict[str, Any]) -> None:
        """Сохранение всех пользователей"""
        await self._write_file(self.config.users_file, users_data)
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получение данных пользователя по ID"""
        users = await self.load_users()
        return users.get(str(user_id), {})
    
    async def save_user(self, user_id: int, user_data: Dict) -> None:
        """Сохранение данных пользователя (атомарно)"""
        async with self._transaction(self.config.users_file, {}) as users:
            users[str(user_id)] = user_data
    
    async def is_user_registered(self, user_id: int) -> bool:
        """Проверка регистрации пользователя"""
        users = await self.load_users()
        return str(user_id) in users
    
    async def update_user_field(self, user_id: int, field: str, value: Any) -> None:
        """Обновление конкретного поля пользователя"""
        async with self._transaction(self.config.users_file, {}) as users:
            user_id_str = str(user_id)
            if user_id_str not in users:
                users[user_id_str] = {}
            users[user_id_str][field] = value
    
    # Games methods
    async def load_games(self) -> List[Any]:
        """Загрузка всех игр"""
        return await self._read_file(self.config.games_file, [])
    
    async def save_games(self, games_data: List[Any]) -> None:
        """Сохранение всех игр"""
        await self._write_file(self.config.games_file, games_data)
    
    async def add_game(self, game_data: Dict) -> None:
        """Добавление новой игры"""
        async with self._transaction(self.config.games_file, []) as games:
            games.append(game_data)
    
    # Banned users methods
    async def load_banned_users(self) -> Dict[str, Any]:
        """Загрузка забаненных пользователей"""
        return await self._read_file(self.config.banned_file, {})
    
    async def save_banned_users(self, banned_data: Dict[str, Any]) -> None:
        """Сохранение забаненных пользователей"""
        await self._write_file(self.config.banned_file, banned_data)
    
    # Session methods
    async def save_session(self, user_id: int, session_data: Dict) -> None:
        """Сохранение сессии пользователя"""
        session_file = self.config.sessions_dir / f"{user_id}.json"
        await self._write_file(session_file, session_data)
    
    async def load_session(self, user_id: int) -> Dict:
        """Загрузка сессии пользователя"""
        session_file = self.config.sessions_dir / f"{user_id}.json"
        return await self._read_file(session_file, {})
    
    async def delete_session(self, user_id: int) -> None:
        """Удаление сессии пользователя"""
        session_file = self.config.sessions_dir / f"{user_id}.json"
        try:
            if session_file.exists():
                session_file.unlink()
        except Exception as e:
            logger.error(f"Error deleting session {user_id}: {e}")
    
    async def load_tournaments(self) -> Dict[str, Any]:
        """Загрузка турниров"""
        return await self._read_file(self.config.tournaments_file, {})

    async def save_tournaments(self, tournaments_data: Dict[str, Any]) -> None:
        """Сохранение турниров"""
        await self._write_file(self.config.tournaments_file, tournaments_data)

    async def load_tournament_applications(self) -> Dict[str, Any]:
        """Загрузка заявок на турниры"""
        return await self._read_file(self.config.tournament_applications_file, {})

    async def save_tournament_applications(self, applications_data: Dict[str, Any]) -> None:
        """Сохранение заявок на турниры"""
        await self._write_file(self.config.tournament_applications_file, applications_data)

# Создаем глобальный экземпляр хранилища
storage = AsyncJSONStorage()
