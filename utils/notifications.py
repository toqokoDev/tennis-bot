from aiogram import Bot
from datetime import datetime
from services.storage import storage

async def send_subscription_reminders(bot: Bot):
    """Отправка напоминаний о скором истечении подписки"""
    users = await storage.load_users()
    current_time = datetime.now()
    
    for user_id, user_data in users.items():
        if 'subscription' in user_data and user_data['subscription'].get('active', False):
            subscription_until = user_data['subscription'].get('until')
            if subscription_until:
                try:
                    until_date = datetime.strptime(subscription_until, '%Y-%m-%d')
                    days_remaining = (until_date - current_time).days
                    
                    # Напоминание за 3 дня до истечения
                    if days_remaining == 3:
                        try:
                            await bot.send_message(
                                int(user_id),
                                f"⚠️ Ваша подписка Tennis-Play PRO истекает через 3 дня ({until_date.strftime('%d.%m.%Y')}).\n\n"
                                "Не забудьте продлить подписку для непрерывного доступа к PRO-функциям!"
                            )
                        except Exception as e:
                            print(f"Не удалось отправить напоминание пользователю {user_id}: {e}")
                            
                    # Напоминание за 1 день до истечения
                    elif days_remaining == 1:
                        try:
                            await bot.send_message(
                                int(user_id),
                                f"🔔 Ваша подписка Tennis-Play PRO истекает завтра ({until_date.strftime('%d.%m.%Y')})!\n\n"
                                "Продлите подписку сейчас, чтобы сохранить доступ ко всем функциям."
                            )
                        except Exception as e:
                            print(f"Не удалось отправить напоминание пользователю {user_id}: {e}")
                            
                except ValueError:
                    continue
