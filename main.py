import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher
from handlers import game_offers_menu, registration, game_offers, more, payments, profile, enter_invoice, search_partner, tours
from config.config import TOKEN
from utils.json_data import load_users, write_users
from utils.notifications import send_subscription_reminders

async def check_subscriptions(bot: Bot):
    """Ежедневная проверка и обновление статуса подписок"""
    while True:
        try:
            users = load_users()
            current_time = datetime.now()
            updated = False
            
            # Проверка истечения подписок
            for user_id, user_data in users.items():
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
                write_users(users)
                print(f"[{datetime.now()}] Обновлены статусы подписок")
            else:
                print(f"[{datetime.now()}] Проверка подписок завершена, изменений нет")
                
            # Отправка напоминаний
            await send_subscription_reminders(bot)
                
        except Exception as e:
            print(f"Ошибка при проверке подписок: {e}")
        
        # Ждем 24 часа до следующей проверки
        await asyncio.sleep(24 * 60 * 60)  # 24 часа

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # Подключаем роутеры           
    dp.include_router(registration.router)
    dp.include_router(game_offers_menu.router)
    dp.include_router(game_offers.router)
    dp.include_router(more.router)
    dp.include_router(payments.router)
    dp.include_router(profile.router)
    dp.include_router(enter_invoice.router)
    dp.include_router(search_partner.router)
    dp.include_router(tours.router)

    # Запускаем фоновую задачу проверки подписок
    subscription_task = asyncio.create_task(check_subscriptions(bot))
    
    try:
        await dp.start_polling(bot)
    finally:
        # Отменяем фоновую задачу при завершении работы
        subscription_task.cancel()
        try:
            await subscription_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
