from yookassa import Configuration, Payment
from datetime import datetime, timedelta
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import StateFilter

from config.config import SECRET_KEY, SHOP_ID, SUBSCRIPTION_PRICE, BOT_USERNAME, EMAIL_ADMIN
from config.profile import get_base_keyboard
from models.states import PaymentStates
from services.payments import create_payment
from services.storage import storage
from services.email import email_service
from utils.utils import calculate_age, remove_country_flag
from utils.translations import get_user_language_async, t
import logging

logger = logging.getLogger(__name__)

async def send_payment_notification_to_admin(
    user_id: int,
    profile: dict,
    payment_id: str,
    user_email: str,
    payment_amount: int
):
    """
    Отправляет администратору email с информацией о платеже и минимальной анкетой пользователя
    """
    try:
        # Формируем минимальные данные анкеты
        first_name = profile.get('first_name', 'Не указано')
        last_name = profile.get('last_name', 'Не указано')
        username = profile.get('username', 'Не указано')
        phone = profile.get('phone', 'Не указано')
        birth_date = profile.get('birth_date', '')
        age = 'Не указано'
        if birth_date:
            try:
                age = await calculate_age(birth_date)
                age = f"{age} лет"
            except:
                pass
        
        sport = profile.get('sport', 'Не указано')
        city = profile.get('city', 'Не указано')
        district = profile.get('district', '')
        if district:
            city = f"{city} - {district}"
        country = remove_country_flag(profile.get('country', 'Не указано'))
        gender = profile.get('gender', 'Не указано')
        role = profile.get('role', 'Не указано')
        player_level = profile.get('player_level', 'Не указано')
        rating_points = profile.get('rating_points', 0)
        
        # Формируем HTML письмо
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background-color: #4CAF50;
            color: white;
            padding: 20px;
            border-radius: 5px 5px 0 0;
            text-align: center;
        }}
        .content {{
            background-color: #f9f9f9;
            padding: 20px;
            border: 1px solid #ddd;
        }}
        .profile-section {{
            background-color: white;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
            border-left: 4px solid #4CAF50;
        }}
        .info-row {{
            margin: 8px 0;
            padding: 5px 0;
            border-bottom: 1px solid #eee;
        }}
        .info-label {{
            font-weight: bold;
            color: #555;
            display: inline-block;
            width: 150px;
        }}
        .info-value {{
            color: #333;
        }}
        .payment-info {{
            background-color: #e8f5e9;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
            border-left: 4px solid #4CAF50;
        }}
        .footer {{
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            font-size: 12px;
            color: #777;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h2>✅ Новая оплата подписки</h2>
    </div>
    
    <div class="content">
        <div class="payment-info">
            <h3>Информация о платеже</h3>
            <div class="info-row">
                <span class="info-label">ID платежа:</span>
                <span class="info-value">{payment_id}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Сумма:</span>
                <span class="info-value">{payment_amount} руб.</span>
            </div>
            <div class="info-row">
                <span class="info-label">Email пользователя:</span>
                <span class="info-value">{user_email}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Telegram ID:</span>
                <span class="info-value">{user_id}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Дата активации:</span>
                <span class="info-value">{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</span>
            </div>
        </div>
        
        <div class="profile-section">
            <h3>Минимальная анкета пользователя</h3>
            <div class="info-row">
                <span class="info-label">Имя:</span>
                <span class="info-value">{first_name} {last_name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Username:</span>
                <span class="info-value">@{username if username != 'Не указано' else 'не указан'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Телефон:</span>
                <span class="info-value">{phone}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Возраст:</span>
                <span class="info-value">{age}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Вид спорта:</span>
                <span class="info-value">{sport}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Роль:</span>
                <span class="info-value">{role}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Уровень/Рейтинг:</span>
                <span class="info-value">{player_level}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Рейтинговые очки:</span>
                <span class="info-value">{rating_points}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Страна:</span>
                <span class="info-value">{country}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Город:</span>
                <span class="info-value">{city}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Пол:</span>
                <span class="info-value">{gender}</span>
            </div>
        </div>
    </div>
    
    <div class="footer">
        <p>Это автоматическое уведомление от Tennis-Play Bot</p>
        <p>Дата отправки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>
    </div>
</body>
</html>
        """
        
        # Отправляем письмо администратору
        await email_service.send_html_email(
            to=EMAIL_ADMIN,
            subject=f"Новая оплата подписки - {first_name} {last_name}",
            html_body=html_body
        )
        
        print(f"[{datetime.now()}] Письмо администратору об оплате отправлено для пользователя {user_id}")
        
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка отправки письма администратору об оплате: {e}")

router = Router()

@router.message(F.text.in_([t("menu.payments", "ru"), t("menu.payments", "en")]))
async def handle_payments(message: types.Message, state: FSMContext):
    # Проверяем наличие активной подписки
    user_id = message.from_user.id
    users = await storage.load_users()
    
    if str(user_id) in users and users[str(user_id)].get('subscription', {}).get('active', False):
        subscription_until = users[str(user_id)]['subscription'].get('until')
        if subscription_until:
            try:
                until_date = datetime.strptime(subscription_until, '%Y-%m-%d')
                if until_date > datetime.now():
                    language = await get_user_language_async(str(user_id))
                    await message.answer(
                        t("payments.subscription_active", language, date=subscription_until),
                        parse_mode="HTML"
                    )
                    return
            except ValueError:
                pass

    language = await get_user_language_async(str(user_id))
    text = t("payments.subscription_benefits", language, price=SUBSCRIPTION_PRICE)
    
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(
        text="💰 Купить подписку", 
        callback_data="buy_subscription"
    ))
    
    await message.answer(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "buy_subscription")
async def start_payment_process(callback: types.CallbackQuery, state: FSMContext):
    # Проверяем наличие активной подписки перед началом оплаты
    user_id = callback.message.chat.id
    users = await storage.load_users()
    
    if str(user_id) in users and users[str(user_id)].get('subscription', {}).get('active', False):
        subscription_until = users[str(user_id)]['subscription'].get('until')
        if subscription_until:
            try:
                until_date = datetime.strptime(subscription_until, '%Y-%m-%d')
                if until_date > datetime.now():
                    language = await get_user_language_async(str(user_id))
                    await callback.message.answer(
                        t("payments.subscription_active", language, date=subscription_until),
                        parse_mode="HTML"
                    )
                    await callback.answer()
                    return
            except ValueError:
                pass

    # Запрашиваем email для чека
    language = await get_user_language_async(str(user_id))
    await callback.message.answer(
        t("payments.enter_email", language),
        parse_mode="HTML"
    )
    
    await state.set_state(PaymentStates.WAITING_EMAIL)
    await callback.answer()

@router.message(PaymentStates.WAITING_EMAIL, F.text)
async def process_email_input(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    # Простая валидация email
    language = await get_user_language_async(str(message.chat.id))
    if '@' not in email or '.' not in email:
        await message.answer(
            t("payments.invalid_email", language)
        )
        return
    
    # Сохраняем email и переходим к созданию платежа
    await state.update_data(user_email=email)
    
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY
    
    try:
        payment_link, payment_id = await create_payment(
            message.chat.id, 
            SUBSCRIPTION_PRICE, 
            "Оплата подписки для расширенного функционала",
            email
        )
        
        await state.update_data(payment_id=payment_id)
        
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(
            text="🔗 Перейти к оплате", 
            url=payment_link
        ))
        builder.add(types.InlineKeyboardButton(
            text="✅ Подтвердить оплату", 
            callback_data="confirm_payment"
        ))
        
        language = await get_user_language_async(str(message.chat.id))
        await message.answer(
            t("payments.payment_link", language, link=payment_link, email=email),
            reply_markup=builder.as_markup()
        )
        
        await state.set_state(PaymentStates.CONFIRM_PAYMENT)
        
    except Exception as e:
        language = await get_user_language_async(str(message.chat.id))
        await message.answer(
            t("payments.payment_created_error", language, error=str(e))
        )
        await state.clear()

@router.callback_query(PaymentStates.CONFIRM_PAYMENT, F.data == "confirm_payment")
async def confirm_payment(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    payment_id = data.get('payment_id', 'не указан')
    user_email = data.get('user_email', 'не указан')
    
    # Удаляем предыдущее сообщение с кнопками оплаты
    try:
        await callback.message.delete()
    except:
        pass
    
    try:
        payment = Payment.find_one(payment_id)
        
        if payment.status == "succeeded":
            # Дополнительная проверка перед активацией подписки
            user_id = callback.message.chat.id
            users = await storage.load_users()
            
            if str(user_id) in users and users[str(user_id)].get('subscription', {}).get('active', False):
                subscription_until = users[str(user_id)]['subscription'].get('until')
                if subscription_until:
                    try:
                        until_date = datetime.strptime(subscription_until, '%Y-%m-%d')
                        if until_date > datetime.now():
                            language = await get_user_language_async(str(user_id))
                            profile = await storage.get_user(user_id) or {}
                            sport = profile.get("sport", "🎾Большой теннис")
                            await callback.message.answer(
                                t("payments.subscription_active_refund", language, date=subscription_until),
                                reply_markup=get_base_keyboard(sport, language=language)
                            )
                            await state.clear()
                            await callback.answer()
                            return
                    except ValueError:
                        pass
            
            # Активируем подписку
            language = await get_user_language_async(str(user_id))
            profile = await storage.get_user(user_id) or {}
            sport = profile.get("sport", "🎾Большой теннис")
            await callback.message.answer(
                t("payments.payment_success", language, email=user_email),
                reply_markup=get_base_keyboard(sport, language=language)
            )
            
            # Сохраняем информацию о подписке в базе данных
            user_id = callback.message.chat.id
            users = await storage.load_users()
            if str(user_id) not in users:
                users[str(user_id)] = {}
            
            users[str(user_id)]['subscription'] = {
                'active': True,
                'until': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
                'activated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'email': user_email
            }
            await storage.save_users(users)
            
            # Отправляем письмо администратору о платеже
            await send_payment_notification_to_admin(
                user_id=user_id,
                profile=users[str(user_id)],
                payment_id=payment_id,
                user_email=user_email,
                payment_amount=SUBSCRIPTION_PRICE
            )

        else:
            language = await get_user_language_async(str(callback.message.chat.id))
            profile = await storage.get_user(callback.message.chat.id) or {}
            sport = profile.get("sport", "🎾Большой теннис")
            await callback.message.answer(
                t("payments.payment_not_completed", language),
                reply_markup=get_base_keyboard(sport, language=language)
            )
        
    except Exception as e:
        language = await get_user_language_async(str(callback.message.chat.id))
        profile = await storage.get_user(callback.message.chat.id) or {}
        sport = profile.get("sport", "🎾Большой теннис")
        await callback.message.answer(
            t("payments.payment_check_error", language, error=str(e)),
            reply_markup=get_base_keyboard(sport, language=language)
        )
    
    await state.clear()
    await callback.answer()

# Обработка отмены ввода email
@router.message(PaymentStates.WAITING_EMAIL, F.text == "/cancel")
async def cancel_email_input(message: types.Message, state: FSMContext):
    language = await get_user_language_async(str(message.chat.id))
    profile = await storage.get_user(message.chat.id) or {}
    sport = profile.get("sport", "🎾Большой теннис")
    await message.answer(
        t("payments.email_cancelled", language),
        reply_markup=get_base_keyboard(sport, language=language)
    )
    await state.clear()
