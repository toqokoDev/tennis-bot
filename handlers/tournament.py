from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from datetime import datetime

from services.storage import storage

router = Router()
logger = logging.getLogger(__name__)

# Глобальные переменные для хранения состояния пагинации
tournament_pages = {}
my_tournaments_pages = {}
my_applications_pages = {}

# Команда для просмотра турниров
@router.message(F.text == "🏆 Турниры")
@router.message(Command("tournaments"))
async def tournaments_main(message: Message):
    """Главное меню турниров"""
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    text = (
        f"🏆 Турниры\n\n"
        f"Сейчас проходит: {len(active_tournaments)} активных турниров\n"
        f"Участвуйте в соревнованиях и покажите свои навыки!\n\n"
        f"📋 Вы можете просмотреть список доступных турниров, "
        f"подать заявку на участие или посмотреть свои текущие турниры."
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Просмотреть список", callback_data="view_tournaments_list:0")
    builder.button(text="📝 Мои заявки", callback_data="my_applications_list:0")
    builder.button(text="🎯 Мои турниры", callback_data="my_tournaments_list:0")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

# Просмотр списка турниров с пагинацией (по одному турниру на страницу)
@router.callback_query(F.data.startswith("view_tournaments_list:"))
async def view_tournaments_list(callback: CallbackQuery):
    """Показывает список турниров с пагинацией по одному турниру на страницу"""
    page = int(callback.data.split(':')[1])
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    if not active_tournaments:
        await callback.message.edit_text("🏆 На данный момент нет активных турниров.")
        await callback.answer()
        return
    
    # Сохраняем список турниров для пагинации
    tournament_ids = list(active_tournaments.keys())
    tournament_pages[callback.from_user.id] = tournament_ids
    
    # Вычисляем общее количество страниц
    total_pages = len(tournament_ids)
    
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    
    # Получаем турнир для текущей страницы
    tournament_id = tournament_ids[page]
    tournament_data = active_tournaments[tournament_id]
    
    # Формируем текст для текущего турнира
    text = f"🏆 Турнир {page + 1}/{total_pages}\n\n"
    text += f"👥 Участников: 8\n"
    
    if tournament_data.get('description'):
        text += f"📝 Описание:\n- Взнос за участие в турнире - 800 руб.\n"+"- Игры проходят на кортах участников турнира с оплатой корта 50/50%.\n"  +"- Время на каждый круг турнира - 1 неделя.\n"+"- Игры идут за каждое место, поэтому в турнире - 3 игры.\n"+"- Победитель в турнире получает бесплатное участие в следующем турнире.\n"
    
    if tournament_data.get('rules'):
        text += f"📋 Правила: {tournament_data.get('rules')}\n"
    
    if tournament_data.get('prize_fund'):
        text += f"💰 Призовой фонд: {tournament_data.get('prize_fund')}\n"
    
    # Проверяем, подал ли пользователь уже заявку на этот турнир
    user_id = callback.from_user.id
    applications = await storage.load_tournament_applications()
    
    existing_application = None
    for app_id, app_data in applications.items():
        if (app_data.get('user_id') == user_id and 
            app_data.get('tournament_id') == tournament_id):
            existing_application = app_data
            break
    
    # Проверяем, зарегистрирован ли пользователь уже в турнире
    is_registered = str(user_id) in tournament_data.get('participants', {})
    
    if existing_application:
        text += f"\n📋 Статус заявки: {'⏳ Ожидает рассмотрения' if existing_application.get('status') == 'pending' else '✅ Принята' if existing_application.get('status') == 'accepted' else '❌ Отклонена'}\n"
    elif is_registered:
        text += "\n✅ Вы уже зарегистрированы в этом турнире\n"
    
    # Создаем клавиатуру с пагинацией
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации
    if total_pages > 1:
        if page > 0:
            builder.button(text="⬅️ Предыдущий", callback_data=f"view_tournaments_list:{page-1}")
        if page < total_pages - 1:
            builder.button(text="Следующий ➡️", callback_data=f"view_tournaments_list:{page+1}")
    
    # Кнопка участия (только если пользователь еще не подал заявку и не зарегистрирован)
    if not existing_application and not is_registered:
        builder.button(text="✅ Участвовать", callback_data=f"apply_tournament:{tournament_id}")
    
    builder.button(text="🔙 Назад в меню", callback_data="tournaments_main_menu")
    
    # Настраиваем расположение кнопок
    if total_pages > 1:
        builder.adjust(2)  # Кнопки пагинации в одном ряду
    if not existing_application and not is_registered:
        builder.adjust(1)  # Кнопка участия в отдельном ряду
    builder.adjust(1)  # Кнопка назад в отдельном ряду
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

# Обработчик кнопки "Участвовать"
@router.callback_query(F.data.startswith("apply_tournament:"))
async def apply_tournament_handler(callback: CallbackQuery):
    """Обработчик подачи заявки на турнир"""
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    tournament_data = tournaments[tournament_id]
    
    # Проверяем, не подал ли пользователь уже заявку
    user_id = callback.from_user.id
    applications = await storage.load_tournament_applications()
    
    # Ищем существующую заявку этого пользователя на этот турнир
    existing_application = None
    for app_id, app_data in applications.items():
        if (app_data.get('user_id') == user_id and 
            app_data.get('tournament_id') == tournament_id):
            existing_application = app_data
            break
    
    if existing_application:
        await callback.answer("⚠️ Вы уже подали заявку на этот турнир")
        return
    
    # Проверяем, не зарегистрирован ли пользователь уже в турнире
    if str(user_id) in tournament_data.get('participants', {}):
        await callback.answer("✅ Вы уже зарегистрированы в этом турнире")
        return
    
    # Загружаем данные пользователя
    users = await storage.load_users()
    user_data = users.get(str(user_id), {})
    
    if not user_data:
        await callback.answer("❌ Сначала зарегистрируйтесь в системе")
        return
    
    # Создаем заявку
    application_id = f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_id}"
    
    applications[application_id] = {
        'user_id': user_id,
        'user_name': f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}",
        'phone': user_data.get('phone', 'Не указан'),
        'tournament_id': tournament_id,
        'tournament_name': tournament_data.get('name', 'Без названия'),
        'applied_at': datetime.now().isoformat(),
        'status': 'pending'
    }
    
    # Сохраняем заявку
    await storage.save_tournament_applications(applications)
    
    await callback.message.edit_text(
        f"✅ Заявка подана!\n\n"
        f"👤 Ваши данные:\n"
        f"Имя: {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"Телефон: {user_data.get('phone', 'Не указан')}\n\n"
        f"📋 Заявка будет рассмотрена администратором. Ожидайте подтверждения."
    )
    
    # Добавляем кнопку для возврата к списку турниров
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Вернуться к списку турниров", callback_data="view_tournaments_list:0")
    builder.button(text="📝 Мои заявки", callback_data="my_applications_list:0")
    builder.button(text="🔙 Назад в меню", callback_data="tournaments_main_menu")
    builder.adjust(1)
    
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

# Просмотр своих заявок с пагинацией
@router.callback_query(F.data.startswith("my_applications_list:"))
async def my_applications_list(callback: CallbackQuery):
    """Показывает заявки пользователя с пагинацией по одной заявке на страницу"""
    page = int(callback.data.split(':')[1])
    user_id = callback.from_user.id
    applications = await storage.load_tournament_applications()
    tournaments = await storage.load_tournaments()
    
    # Получаем все заявки пользователя
    user_applications = []
    for app_id, app_data in applications.items():
        if app_data.get('user_id') == user_id:
            user_applications.append(app_data)
    
    if not user_applications:
        await callback.message.edit_text("📋 У вас нет активных заявок на турниры.")
        await callback.answer()
        return
    
    # Сохраняем список заявок для пагинации
    my_applications_pages[callback.from_user.id] = user_applications
    
    # Вычисляем общее количество страниц
    total_pages = len(user_applications)
    
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    
    # Получаем заявку для текущей страницы
    application = user_applications[page]
    
    # Получаем данные турнира для дополнительной информации
    tournament_data = tournaments.get(application['tournament_id'], {})
    
    # Формируем текст для текущей заявки
    text = f"📋 Ваша заявка {page + 1}/{total_pages}\n\n"
    text += f"🎯 Турнир: {application.get('tournament_name', 'Без названия')}\n"
    
    if tournament_data:
        text += f"📅 Дата турнира: {tournament_data.get('date', 'Не указана')}\n"
        text += f"📍 Место: {tournament_data.get('location', 'Не указано')}\n"
    
    text += f"📅 Подана: {datetime.fromisoformat(application['applied_at']).strftime('%d.%m.%Y %H:%M')}\n"
    
    # Статус заявки
    status_emoji = "⏳" if application.get('status') == 'pending' else "✅" if application.get('status') == 'accepted' else "❌"
    status_text = "ожидает рассмотрения" if application.get('status') == 'pending' else "принята" if application.get('status') == 'accepted' else "отклонена"
    text += f"📊 Статус: {status_emoji} {status_text}\n"
    
    if application.get('status') == 'accepted' and application.get('accepted_at'):
        text += f"✅ Подтверждена: {datetime.fromisoformat(application['accepted_at']).strftime('%d.%m.%Y %H:%M')}\n"
    
    if application.get('status') == 'rejected' and application.get('rejected_reason'):
        text += f"📝 Причина отказа: {application.get('rejected_reason')}\n"
    
    # Информация о пользователе из заявки
    text += f"\n👤 Ваши данные в заявке:\n"
    text += f"Имя: {application.get('user_name', 'Не указано')}\n"
    text += f"Телефон: {application.get('phone', 'Не указан')}\n"
    
    # Создаем клавиатуру с пагинацией
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации
    if total_pages > 1:
        if page > 0:
            builder.button(text="⬅️ Предыдущая", callback_data=f"my_applications_list:{page-1}")
        if page < total_pages - 1:
            builder.button(text="Следующая ➡️", callback_data=f"my_applications_list:{page+1}")
    
    # Кнопка для просмотра турнира (если турнир существует)
    if tournament_data:
        builder.button(text="👀 Посмотреть турнир", callback_data=f"view_tournament:{application['tournament_id']}")
    
    builder.button(text="📋 Все турниры", callback_data="view_tournaments_list:0")
    builder.button(text="🔙 Назад в меню", callback_data="tournaments_main_menu")
    
    # Настраиваем расположение кнопок
    if total_pages > 1:
        builder.adjust(2)  # Кнопки пагинации в одном ряду
    if tournament_data:
        builder.adjust(1)  # Кнопка просмотра турнира
    builder.adjust(1)  # Остальные кнопки в отдельных рядах
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

# Просмотр турнира из заявки
@router.callback_query(F.data.startswith("view_tournament:"))
async def view_tournament_from_application(callback: CallbackQuery):
    """Показывает турнир из заявки"""
    tournament_id = callback.data.split(':')[1]
    tournaments = await storage.load_tournaments()
    
    if tournament_id not in tournaments:
        await callback.answer("❌ Турнир не найден")
        return
    
    # Находим индекс турнира в списке активных турниров
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    tournament_ids = list(active_tournaments.keys())
    
    if tournament_id not in tournament_ids:
        await callback.answer("❌ Турнир больше не активен")
        return
    
    page = tournament_ids.index(tournament_id)
    
    # Переходим к просмотру турнира
    await view_tournaments_list(CallbackQuery(
        message=callback.message,
        data=f"view_tournaments_list:{page}",
        from_user=callback.from_user,
        chat_instance=callback.chat_instance,
        id=callback.id
    ))

# Просмотр своих турниров с пагинацией
@router.callback_query(F.data.startswith("my_tournaments_list:"))
async def my_tournaments_list(callback: CallbackQuery):
    """Показывает турниры пользователя с пагинацией"""
    page = int(callback.data.split(':')[1])
    user_id = callback.from_user.id
    tournaments = await storage.load_tournaments()
    
    # Получаем все турниры пользователя
    user_tournaments = []
    for tournament_id, tournament_data in tournaments.items():
        if str(user_id) in tournament_data.get('participants', {}):
            user_tournaments.append((tournament_id, tournament_data))
    
    if not user_tournaments:
        await callback.message.edit_text("🎾 Вы пока не участвуете ни в одном турнире.")
        await callback.answer()
        return
    
    # Сохраняем список турниров для пагинации
    my_tournaments_pages[callback.from_user.id] = user_tournaments
    
    # Вычисляем общее количество страниц
    total_pages = len(user_tournaments)
    
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    
    # Получаем турнир для текущей страницы
    tournament_id, tournament_data = user_tournaments[page]
    participant_data = tournament_data['participants'][str(user_id)]
    
    # Формируем текст для текущего турнира
    text = f"🏆 Ваш турнир {page + 1}/{total_pages}\n\n"
    text += f"🎯 Название: {tournament_data.get('name', 'Без названия')}\n"
    text += f"📅 Дата: {tournament_data.get('date', 'Не указана')}\n"
    text += f"📍 Место: {tournament_data.get('location', 'Не указано')}\n"
    text += f"👥 Участников: {len(tournament_data.get('participants', {}))}\n"
    
    if tournament_data.get('description'):
        text += f"📝 Описание: {tournament_data.get('description')}\n"
    
    if tournament_data.get('rules'):
        text += f"📋 Правила: {tournament_data.get('rules')}\n"
    
    if tournament_data.get('prize_fund'):
        text += f"💰 Призовой фонд: {tournament_data.get('prize_fund')}\n"
    
    # Информация о регистрации
    if participant_data.get('accepted_at'):
        text += f"✅ Подтверждено: {datetime.fromisoformat(participant_data['accepted_at']).strftime('%d.%m.%Y %H:%M')}\n"
    
    if participant_data.get('applied_at'):
        text += f"📅 Заявка подана: {datetime.fromisoformat(participant_data['applied_at']).strftime('%d.%m.%Y %H:%M')}\n"
    
    # Создаем клавиатуру с пагинацией
    builder = InlineKeyboardBuilder()
    
    # Кнопки пагинации
    if total_pages > 1:
        if page > 0:
            builder.button(text="⬅️ Предыдущий", callback_data=f"my_tournaments_list:{page-1}")
        if page < total_pages - 1:
            builder.button(text="Следующий ➡️", callback_data=f"my_tournaments_list:{page+1}")
    
    builder.button(text="📋 Все турниры", callback_data="view_tournaments_list:0")
    builder.button(text="🔙 Назад в меню", callback_data="tournaments_main_menu")
    
    # Настраиваем расположение кнопок
    if total_pages > 1:
        builder.adjust(2)  # Кнопки пагинации в одном ряду
    builder.adjust(1)  # Остальные кнопки в отдельных рядах
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

# Возврат в главное меню турниров
@router.callback_query(F.data == "tournaments_main_menu")
async def tournaments_main_menu(callback: CallbackQuery):
    """Возврат в главное меню турниров"""
    tournaments = await storage.load_tournaments()
    active_tournaments = {k: v for k, v in tournaments.items() if v.get('status') == 'active'}
    
    text = (
        f"🏆 Турниры\n\n"
        f"Сейчас проходит: {len(active_tournaments)} активных турниров\n"
        f"Участвуйте в соревнованиях и покажите свои навыки!\n\n"
        f"📋 Вы можете просмотреть список доступных турниров, "
        f"подать заявку на участие или посмотреть свои текущие турниры."
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Просмотреть список", callback_data="view_tournaments_list:0")
    builder.button(text="📝 Мои заявки", callback_data="my_applications_list:0")
    builder.button(text="🎯 Мои турниры", callback_data="my_tournaments_list:0")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()