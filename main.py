import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Filter
from handlers import game_offers_menu, registration, game_offers, more, payments, profile, enter_invoice, search_partner, tours, admin, admin_edit, tournament, invite, tournament_score
from config.config import TOKEN
from utils.admin import is_user_banned
from utils.notifications import send_subscription_reminders
from services.storage import storage

class BannedUserFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        """Фильтр для проверки забаненных пользователей"""
        user_id = str(message.from_user.id)
        banned_users = await storage.load_banned_users()
        return user_id in banned_users

async def ban_check_handler(message: Message):
    """Обработчик для забаненных пользователей"""
    user_id = str(message.from_user.id)
    
    # Дополнительная проверка на случай, если фильтр не сработал
    if await is_user_banned(user_id):
        await message.answer(
            "🚫 Ваш аккаунт заблокирован.\n\n"
            "Вы не можете использовать функции бота.\n"
            "По вопросам разблокировки обратитесь к администратору."
        )
        return True
    return False

async def cleanup_expired_game_offers(bot: Bot):
    """Очистка прошедших предложенных игр"""
    try:
        users = await storage.load_users()
        current_time = datetime.now()
        updated = False
        expired_count = 0
        
        for user_id, user_data in users.items():
            # Пропускаем забаненных пользователей
            if await is_user_banned(user_id):
                continue
                
            # Проверяем игры пользователя
            if 'games' in user_data and user_data['games']:
                games_to_keep = []
                
                for game in user_data['games']:
                    if game.get('active', True) and game.get('date') and game.get('time'):
                        try:
                            # Парсим дату и время игры
                            game_date_str = game.get('date')
                            game_time_str = game.get('time')
                            
                            # Парсим дату (может быть в разных форматах)
                            if 'T' in game_date_str:
                                # ISO формат: 2025-01-15T10:30
                                game_datetime = datetime.fromisoformat(game_date_str)
                            elif '.' in game_date_str and len(game_date_str.split('.')) == 2:
                                # Формат: 20.09 (день.месяц) с текущим годом
                                day, month = game_date_str.split('.')
                                current_year = current_time.year
                                game_date = datetime.strptime(f"{day}.{month}.{current_year}", '%d.%m.%Y').date()
                                game_time = datetime.strptime(game_time_str, '%H:%M').time()
                                game_datetime = datetime.combine(game_date, game_time)
                            else:
                                # Простой формат: 2025-01-15
                                game_date = datetime.strptime(game_date_str, '%Y-%m-%d').date()
                                game_time = datetime.strptime(game_time_str, '%H:%M').time()
                                game_datetime = datetime.combine(game_date, game_time)
                            
                            # Если игра уже прошла (более 1 часа назад), удаляем её
                            if game_datetime < current_time:
                                expired_count += 1
                                print(f"Удалена прошедшая игра пользователя {user_id}: {game_date_str} {game_time_str}")
                            else:
                                games_to_keep.append(game)
                                
                        except (ValueError, TypeError) as e:
                            # Если не удается распарсить дату/время, оставляем игру
                            print(f"Не удалось распарсить дату игры пользователя {user_id}: {e}")
                            games_to_keep.append(game)
                    else:
                        # Неактивные игры или игры без даты/времени оставляем
                        games_to_keep.append(game)
                
                # Обновляем список игр пользователя, если что-то изменилось
                if len(games_to_keep) != len(user_data['games']):
                    users[user_id]['games'] = games_to_keep
                    updated = True
        
        if updated:
            await storage.save_users(users)
            print(f"[{datetime.now()}] Очищено прошедших предложенных игр: {expired_count}")
        else:
            print(f"[{datetime.now()}] Проверка прошедших игр завершена, изменений нет")
            
    except Exception as e:
        print(f"Ошибка при очистке прошедших игр: {e}")

async def check_subscriptions(bot: Bot):
    """Ежедневная проверка и обновление статуса подписок"""
    while True:
        try:
            users = await storage.load_users()
            current_time = datetime.now()
            updated = False
            
            # Проверка истечения подписок
            for user_id, user_data in users.items():
                # Пропускаем забаненных пользователей
                if await is_user_banned(user_id):
                    continue
                    
                if 'subscription' in user_data and user_data['subscription'].get('active', False):
                    subscription_until = user_data['subscription'].get('until')
                    if subscription_until:
                        try:
                            until_date = datetime.strptime(subscription_until, '%Y-%m-%d')
                            if until_date < current_time:
                                # Подписка истекла
                                users[user_id]['subscription']['active'] = False
                                users[user_id]['subscription']['expired'] = True
                                updated = True
                                
                                # Отправляем уведомление пользователю
                                try:
                                    await bot.send_message(
                                        int(user_id),
                                        "❌ Ваша подписка Tennis-Play PRO истекла.\n\n"
                                        "Для продолжения доступа к PRO-функциям продлите подписку в разделе '💳 Платежи'"
                                    )
                                except Exception as e:
                                    print(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
                                
                        except ValueError:
                            # Некорректный формат даты
                            users[user_id]['subscription']['active'] = False
                            users[user_id]['subscription']['error'] = 'invalid_date_format'
                            updated = True
            
            if updated:
                await storage.save_users(users)
                print(f"[{datetime.now()}] Обновлены статусы подписок")
            else:
                print(f"[{datetime.now()}] Проверка подписок завершена, изменений нет")
                
            # Очистка прошедших предложенных игр
            await cleanup_expired_game_offers(bot)
                
            # Отправка напоминаний (только для незабаненных пользователей)
            await send_subscription_reminders(bot)
                
        except Exception as e:
            print(f"Ошибка при проверке подписок: {e}")
        
        # Ждем 24 часа до следующей проверки
        await asyncio.sleep(24 * 60 * 60)  # 24 часа

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # Добавляем обработчик для забаненных пользователей в самом начале
    dp.message.register(ban_check_handler, BannedUserFilter())
    
    # Подключаем роутеры       
    dp.include_router(admin.admin_router)
    dp.include_router(admin_edit.admin_edit_router) 
    dp.include_router(registration.router)
    dp.include_router(game_offers_menu.router)
    dp.include_router(game_offers.router)
    dp.include_router(more.router)
    dp.include_router(profile.router)
    dp.include_router(tournament_score.router)
    dp.include_router(enter_invoice.router)
    dp.include_router(search_partner.router)
    dp.include_router(tours.router)
    dp.include_router(tournament.router)
    dp.include_router(invite.router)
    dp.include_router(payments.router)

    # Запускаем фоновые задачи
    subscription_task = asyncio.create_task(check_subscriptions(bot))
    
    try:
        await dp.start_polling(bot)
    finally:
        # Отменяем фоновые задачи при завершении работы
        subscription_task.cancel()
        
        try:
            await subscription_task
        except asyncio.CancelledError:
            pass
        
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
