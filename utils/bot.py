from config.paths import BASE_DIR
from utils.admin import is_admin
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from utils.utils import calculate_age, remove_country_flag
from utils.translations import get_user_language_async, t
from config.profile import (
    get_sport_translation, get_country_translation, get_city_translation, get_district_translation,
    get_gender_translation, get_payment_type_translation, get_sport_config, get_sport_texts,
)
from services.storage import storage

# ---------- Вспомогательная отправка единого "текущего" сообщения ----------
async def show_current_data(message: types.Message, state: FSMContext, text: str,
                            reply_markup=None, parse_mode="HTML"):
    user_data = await state.get_data()
    prev_msg_id = user_data.get('prev_msg_id')
    try:
        msg = await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except:
        try: 
            if prev_msg_id:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=prev_msg_id)
        except:
            pass
        msg = await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)

    await state.update_data(prev_msg_id=msg.message_id)
    await storage.save_session(message.from_user.id, await state.get_data())

async def show_profile(message: types.Message, profile: dict, back_button=False):
    caption_lines = []
    language = await get_user_language_async(str(message.chat.id))
    
    first_name = profile.get('first_name', '')
    last_name = profile.get('last_name', '')
    name_text = t("profile.view.name", language, first_name=first_name, last_name=last_name)
    caption_lines.append(f"\n<b>{name_text}</b>")
    
    if profile.get('birth_date'):
        age = await calculate_age(profile['birth_date'])
        if age > 0:
            caption_lines.append(t("profile.view.age", language, age=age))
    
    # Получаем конфигурацию для вида спорта
    sport = profile.get('sport', '🎾Большой теннис')
    config = get_sport_config(sport)
    sport_translated = get_sport_translation(sport, language)
    
    # Показываем роль только если она нужна для данного вида спорта
    if config.get("has_role", True):
        role_raw = profile.get('role', '—')
        if "Тренер" in role_raw:
            role_view = t("config.roles.trainer", language)
        elif "Игрок" in role_raw:
            role_view = t("config.roles.player", language)
        else:
            role_view = role_raw
        caption_lines.append(t("profile.view.role", language, role=role_view))
    
    # Показываем уровень только если он нужен для данного вида спорта
    if config.get("has_level", True) and profile.get('player_level'):
        if sport == "🏓Настольный теннис":
            caption_lines.append(t("profile.view.table_tennis_rating", language, rating=profile.get('player_level')))
        else:
            caption_lines.append(t("profile.view.level", language, level=profile.get('player_level'), points=profile.get('rating_points', 0)))
    
    # Показываем стоимость только если она нужна для данного вида спорта
    if config.get("has_payment", True) and profile.get('price') is not None:
        caption_lines.append(t("profile.view.training_price", language, price=profile.get('price')))
    
    caption_lines.append(t("profile.view.country", language, country=get_country_translation(profile.get('country', '—'), language)))
    city = get_city_translation(profile.get('city', '—'), language)
    district_raw = profile.get('district', None)
    district = get_district_translation(district_raw, language) if district_raw else None
    if district:
        caption_lines.append(t("profile.view.city_district", language, city=city, district=district))
    else:
        caption_lines.append(t("profile.view.city", language, city=city))
    caption_lines.append(t("profile.view.sport", language, sport=sport_translated))

    gender_raw = profile.get('gender', '—')
    gender_view = get_gender_translation(gender_raw, language)
    caption_lines.append(t("profile.view.gender", language, gender=gender_view))
    
    # Показываем статистику игр только для спортивных видов
    if sport not in ["☕️Бизнес-завтрак", "🍻По пиву", "🍒Знакомства"]:
        games_played = profile.get('games_played', 0)
        games_wins = profile.get('games_wins', 0)
        caption_lines.append(t("profile.view.stats_title", language))
        caption_lines.append(t("profile.view.stats_played", language, count=games_played))
        caption_lines.append(t("profile.view.stats_wins", language, count=games_wins))
        
        if games_played > 0:
            percent = int((games_wins / games_played) * 100) if games_played > 0 else 0
            caption_lines.append(t("profile.view.stats_winrate", language, percent=percent))
    
    # Показываем оплату корта только если она нужна для данного вида спорта
    if config.get("has_payment", True) and profile.get('default_payment'):
        payment_raw = profile.get('default_payment', '—')
        payment_view = get_payment_type_translation(payment_raw, language)
        caption_lines.append(t("profile.view.court_payment", language, payment=payment_view))
    
    # Показываем поиск партнера на отдых только если это нужно для данного вида спорта
    if config.get("has_vacation", True) and profile.get('vacation_tennis', False):
        caption_lines.append(t("profile.view.vacation_title", language))
        caption_lines.append(t("profile.view.vacation_dates", language, start=profile.get('vacation_start', '—'), end=profile.get('vacation_end', '—')))
        if profile.get('vacation_comment'):
            caption_lines.append(t("profile.view.vacation_comment", language, comment=profile.get('vacation_comment')))
    
    # Специальные поля для знакомств
    if sport == "🍒Знакомства":
        goal_key = profile.get("dating_goal_key")
        goal = profile.get("dating_goal")
        if goal_key:
            caption_lines.append(t("profile.view.dating_goal", language, goal=t(f"config.dating_goals.{goal_key}", language)))
        elif goal:
            caption_lines.append(t("profile.view.dating_goal", language, goal=goal))
        
        interests_keys = profile.get("dating_interests_keys")
        interests = profile.get('dating_interests', [])
        if interests_keys and isinstance(interests_keys, list) and interests_keys:
            caption_lines.append(t("profile.view.dating_interests", language, interests=", ".join([t(f"config.dating_interests.{k}", language) for k in interests_keys])))
        elif isinstance(interests, list) and interests:
            caption_lines.append(t("profile.view.dating_interests", language, interests=", ".join(interests)))
        
        if profile.get('dating_additional'):
            caption_lines.append(t("profile.view.dating_additional", language, text=profile.get('dating_additional')))
    
    # Специальные поля для встреч
    if sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
        if profile.get('meeting_time'):
            caption_lines.append(t("profile.view.meeting_time", language, text=profile.get('meeting_time')))
    
    # Показываем "О себе" только если это нужно для данного вида спорта
    if config.get("has_about_me", True) and profile.get('profile_comment'):
        caption_lines.append(t("profile.view.about_me", language, text=profile.get('profile_comment', '—')))
    
    is_user_admin = await is_admin(message.chat.id)
    profile_user_id = profile.get('telegram_id')


    if is_user_admin:
        partner_links = {
            'com': 'https://tennis-play.com/partner/user/',
            'by': 'https://tennis-play.by/partner/user/',
            'kz': 'https://tennis-play.kz/partner/user/',
            'padeltennis': 'https://padeltennis-play.com/partner/user/',
            'tabletennis': 'https://tabletennis-play.com/partner/user/',
            'tournaments': 'https://tennis-tournaments.com/partner/user/'
        }
        web_user_id = profile.get('web_user_id', '')
        web_domain = profile.get('web_domain')
        
        if web_domain:
            partner_link = partner_links.get(web_domain)
            if partner_link:
                full_link = f"{partner_link}{web_user_id}/"
                caption_lines.append(f"\n\n{t('profile.view.website_link', language, link=full_link)}")

    caption = "\n".join(caption_lines) if caption_lines else t("profile.view.unavailable", language)

    admin_buttons = [
        [InlineKeyboardButton(text=t("admin.buttons.delete_user", language), callback_data=f"admin_select_user:{profile_user_id}")],
        [InlineKeyboardButton(text=t("admin.buttons.delete_subscription", language), callback_data=f"admin_select_subscription:{profile_user_id}")],
        [InlineKeyboardButton(text=t("admin.buttons.ban_user", language), callback_data=f"admin_ban_user:{profile_user_id}")],
        [InlineKeyboardButton(text=t("admin.buttons.delete_vacation", language), callback_data=f"admin_confirm_delete_vacation:{profile_user_id}")]
    ]
    
    if message.chat.id == profile_user_id:
        # Клавиатура для своего профиля в зависимости от вида спорта
        keyboard_buttons = [
            [InlineKeyboardButton(text=t("profile.view.buttons.edit_profile", language), callback_data="edit_profile")]
        ]
        
        # Получаем тексты для вида спорта
        texts = get_sport_texts(sport, language)
        
        # Получаем тексты кнопок с проверкой
        my_offers_text = texts.get("my_offers_button", "")
        offer_text = texts.get("offer_button", "")
        
        # Если тексты пустые, None, или это ключ перевода (содержит точки и начинается с "game_offers"), используем значения по умолчанию
        # Ключ перевода обычно содержит точки и не содержит эмодзи в начале
        def is_translation_key(text):
            if not text or not isinstance(text, str):
                return False
            # Если текст содержит точки и начинается с известных префиксов ключей - это ключ
            if "." in text and (text.startswith("game_offers.") or text.startswith("profile.") or text.startswith("config.")):
                return True
            # Если текст не содержит эмодзи и содержит только латиницу/кириллицу с точками - возможно ключ
            if "." in text and len(text) > 20 and not any(ord(c) > 127 for c in text[:5]):
                return True
            return False
        
        if not my_offers_text or my_offers_text.strip() == "" or is_translation_key(my_offers_text):
            my_offers_text = "📋 Мои предложения" if language == "ru" else "📋 My offers"
        if not offer_text or offer_text.strip() == "" or is_translation_key(offer_text):
            offer_text = "🎾 Предложить игру" if language == "ru" else "🎾 Offer game"
        
        # Добавляем кнопки в зависимости от вида спорта
        if sport not in ["☕️Бизнес-завтрак", "🍻По пиву", "🍒Знакомства"]:
            # Для спортивных видов
            if config.get("has_vacation", True):
                keyboard_buttons.append([InlineKeyboardButton(text=t("profile.view.buttons.find_vacation_partner", language), callback_data="createTour")])
            
            keyboard_buttons.extend([
                [InlineKeyboardButton(text=my_offers_text, callback_data="my_offers")],
                [InlineKeyboardButton(text=offer_text, callback_data="new_offer")],
                [InlineKeyboardButton(text=t("profile.view.buttons.my_game_history", language), callback_data=f"game_history:{message.chat.id}")]
            ])
        else:
            # Для неспортивных видов
            keyboard_buttons.append([InlineKeyboardButton(text=my_offers_text, callback_data="my_offers")])
            keyboard_buttons.append([InlineKeyboardButton(text=offer_text, callback_data="new_offer")])
        
        keyboard_buttons.append([InlineKeyboardButton(text=t("profile.view.buttons.delete_profile", language), callback_data="1delete_profile")])
        keyboard_buttons.append([InlineKeyboardButton(text=t("profile.view.buttons.main_menu", language), callback_data="main_menu")])
        
        # Если админ смотрит свой профиль - добавляем админские кнопки
        if is_user_admin:
            keyboard_buttons = admin_buttons + keyboard_buttons
            
    else:
        # Клавиатура для чужого профиля в зависимости от вида спорта
        keyboard_buttons = []

        keyboard_buttons.append([
            InlineKeyboardButton(
                text=t("profile.view.buttons.contact", language),
                callback_data=f"profile_contact:{profile_user_id}"
            )
        ])

        
        # Добавляем кнопки в зависимости от вида спорта
        if sport not in ["☕️Бизнес-завтрак", "🍻По пиву", "🍒Знакомства"]:
            # Для спортивных видов
            keyboard_buttons.append([InlineKeyboardButton(text=t("profile.view.buttons.view_match_history", language), callback_data=f"game_history:{profile_user_id}")])
        elif sport in ["☕️Бизнес-завтрак", "🍻По пиву"]:
            keyboard_buttons.append([InlineKeyboardButton(text=t("profile.view.buttons.view_meeting_offers", language), callback_data=f"game_history:{profile_user_id}")])
        elif sport == "🍒Знакомства":
            keyboard_buttons.append([InlineKeyboardButton(text=t("profile.view.buttons.view_profiles", language), callback_data=f"game_history:{profile_user_id}")])
        
        keyboard_buttons.append([InlineKeyboardButton(text=t("profile.view.buttons.main_menu", language), callback_data="main_menu")])
        
        # Если админ смотрит чужой профиль - добавляем админские кнопки
        if is_user_admin:
            admin_buttons.append([InlineKeyboardButton(text=t("admin.buttons.edit_other_profile", language), callback_data=f"admin_edit_profile:{profile_user_id}")])
            keyboard_buttons = admin_buttons + keyboard_buttons

    if back_button:
        keyboard_buttons.append([InlineKeyboardButton(text=t("common.back", language), callback_data="partner_back_to_results")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    photo_path = profile.get("photo_path")
    if photo_path and (BASE_DIR / photo_path).exists():
        await message.answer_photo(
            FSInputFile(BASE_DIR / photo_path), 
            caption=caption, 
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            caption, 
            parse_mode="HTML",
            reply_markup=keyboard
        )
        