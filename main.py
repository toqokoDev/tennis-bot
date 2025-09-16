import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Filter
from handlers import game_offers_menu, registration, game_offers, more, payments, profile, enter_invoice, search_partner, tours, admin, admin_edit, tournament, invite
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
