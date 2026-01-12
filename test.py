import asyncio
from telethon import TelegramClient
from telethon.errors import PhoneNumberInvalidError, PhoneNumberUnoccupiedError
from telethon.tl.types import User

api_id = '16635892'
api_hash = '9929bdc36d6832f8502dd3210fcd2f2e'
phone_number = '+375259997565'  # Ваш номер для авторизации

async def get_username_by_phone(target_phone):
    """
    Получает username пользователя по номеру телефона
    """
    try:
        # Создаем клиент
        client = TelegramClient('session_name', api_id, api_hash)
        
        # Запускаем клиент
        await client.start(phone=phone_number)
        
        print("✓ Авторизация успешна")
        print(f"Ищу пользователя с номером: {target_phone}")
        
        try:
            # Получаем информацию о пользователе
            user = await client.get_entity(target_phone)
            
            # Проверяем, является ли объект пользователем
            if isinstance(user, User):
                print(f"\n📋 Информация о пользователе:")
                print(f"Имя: {user.first_name or 'Не указано'}")
                print(f"Фамилия: {user.last_name or 'Не указано'}")
                print(f"ID: {user.id}")
                print(f"Username: @{user.username if user.username else 'Не установлен'}")
                print(f"Номер: {user.phone}")
                
                if user.username:
                    return f"@{user.username}"
                else:
                    return "У пользователя нет username"
            else:
                return "Найденный объект не является пользователем"
                
        except ValueError:
            return "Пользователь не найден или скрыл номер"
        except PhoneNumberUnoccupiedError:
            return "Номер не зарегистрирован в Telegram"
        except Exception as e:
            return f"Ошибка: {str(e)}"
            
    except PhoneNumberInvalidError:
        return "Неверный номер телефона"
    except Exception as e:
        return f"Ошибка авторизации: {str(e)}"
    finally:
        # Закрываем соединение
        await client.disconnect()

async def main():
    # Номер для поиска
    target_phone = '13313095883'  # Замените на номер для поиска
    
    result = await get_username_by_phone(target_phone)
    print(f"\n🔍 Результат: {result}")

# Запуск
if __name__ == "__main__":
    asyncio.run(main())