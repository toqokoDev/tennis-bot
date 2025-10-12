"""
Сервис для работы с Web API сайта Tennis-Play
"""

import aiohttp
import asyncio
import logging
from typing import Optional, Dict

from config.config import API_BASE_URL, API_SECRET_TOKEN

logger = logging.getLogger(__name__)


class WebAPIClient:
    """Клиент для работы с Web API"""
    
    def __init__(self):
        self.base_url = API_BASE_URL
        self.token = API_SECRET_TOKEN
        # URLs для разных доменов
        self.domain_urls = {
            'com': 'https://tennis-play.com/profile/api.php',
            'by': 'https://tennis-play.by/profile/api.php'
        }
    
    async def get_user_data(self, user_id: str, domain: str = 'com') -> Optional[Dict]:
        """
        Получает данные пользователя с сайта
        
        Args:
            user_id: ID пользователя на сайте
            domain: Домен сайта ('com' или 'by')
        """
        try:
            # Выбираем URL в зависимости от домена
            api_url = self.domain_urls.get(domain, self.base_url)
            
            async with aiohttp.ClientSession() as session:
                params = {
                    'action': 'get_user',
                    'user_id': user_id,
                    'token': self.token
                }
                
                async with session.get(
                    api_url,
                    params=params
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('success'):
                            return result.get('data')
                    elif response.status == 404:
                        logger.warning(f"Пользователь {user_id} не найден на сайте")
                    elif response.status == 403:
                        logger.error("Ошибка авторизации API: неверный токен")
                    else:
                        logger.error(f"Ошибка API: статус {response.status}")
                    
                    return None
                    
        except asyncio.TimeoutError:
            logger.error(f"Таймаут при запросе данных пользователя {user_id}")
            return None
        except Exception as e:
            logger.error(f"Ошибка получения данных пользователя {user_id}: {e}")
            return None
    
    async def download_photo(self, photo_url: str, save_path: str) -> bool:
        """
        Скачивает фото с сайта и сохраняет в указанный путь
        
        Args:
            photo_url: URL фото на сайте
            save_path: Путь для сохранения файла
            
        Returns:
            True если успешно, False иначе
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as response:
                    if response.status == 200:
                        with open(save_path, 'wb') as f:
                            f.write(await response.read())
                        logger.info(f"Фото успешно скачано: {save_path}")
                        return True
                    else:
                        logger.error(f"Ошибка скачивания фото: статус {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Ошибка скачивания фото {photo_url}: {e}")
            return False
    
    def convert_web_user_to_params(self, web_user: Dict) -> Dict:
        # Разбиваем имя на имя и фамилию
        name = web_user.get('name', '')
        name_parts = name.strip().split(' ', 1)
        fname = name_parts[0] if len(name_parts) > 0 else ''
        lname = name_parts[1] if len(name_parts) > 1 else ''
        
        # Форматируем дату рождения из формата БД в ДД.ММ.ГГГГ
        birthdate = web_user.get('birthdate', '')
        if birthdate and birthdate != '0000-00-00 00:00:00':
            try:
                from datetime import datetime
                dt = datetime.strptime(birthdate, '%Y-%m-%d %H:%M:%S')
                bdate = dt.strftime('%d.%m.%Y')
            except:
                bdate = ''
        else:
            bdate = ''
        
        # Пол: "Мужской" → "male", "Женский" → "female"
        gender = web_user.get('sex', 'Мужской')
        
        # Тип спорта: "Настольный теннис" → "tabletennis"
        sport = web_user.get('game_type', '')
        
        # Роль: уже текст "Игрок" или "Тренер", нужно конвертировать
        role = web_user.get('role', 'Игрок')
        
        # Способ оплаты: уже текст, конвертируем в короткие коды
        payment = web_user.get('court', 'Пополам')
        
        # Получаем названия страны, города и района прямо из API
        # API теперь возвращает и ID и названия
        country_name = web_user.get('country_name', '')
        city_name = web_user.get('city_name', '')
        district_name = web_user.get('district_name', '')
        # Обработка game_level: если это целое число, добавляем ".0"
        raw_level = web_user.get('game_level', '')
        level_str = str(raw_level)
        try:
            if level_str and float(level_str).is_integer():
                # если это целое число (например, 4, 3), делаем '4.0'
                level_str = f"{int(float(level_str))}.0"
        except Exception:
            # если не число, оставляем как есть
            pass
        # Формируем параметры
        params = {
            'phone': web_user.get('phone', '').replace('+', ''),
            'sport': sport,
            'fname': fname,
            'lname': lname,
            'bdate': bdate,
            'gender': gender,
            'role': role,
            'level': level_str,
            'price': None if str(web_user.get('hour_cost', '')) == '0' else int(web_user.get('hour_cost', '')),
            'payment': payment,
            'comment': web_user.get('about', '')
        }
        
        # Добавляем country - приоритет названию из API, fallback на маппинг
        if country_name:
            params['country'] = country_name
        
        # Добавляем city - приоритет названию из API, fallback на маппинг
        if city_name:
            params['city'] = city_name
        
        # Добавляем район если есть
        if district_name:
            params['district'] = district_name
        
        # Добавляем фото
        photo = web_user.get('photo', '')
        photo_url = web_user.get('photo_url', '')
        photo_url_large = web_user.get('photo_url_large', '')
        
        if photo:
            params['photo'] = photo
        if photo_url:
            params['photo_url'] = photo_url
        if photo_url_large:
            params['photo_url_large'] = photo_url_large
        
        # Убираем пустые значения
        params = {k: v for k, v in params.items() if v}
        
        return params

# Создаем глобальный экземпляр клиента
web_api_client = WebAPIClient()
