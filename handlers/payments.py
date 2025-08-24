from yookassa import Configuration, Payment
from datetime import datetime, timedelta
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import SECRET_KEY, SHOP_ID, SUBSCRIPTION_PRICE
from config.profile import base_keyboard
from models.states import PaymentStates
from utils.json_data import load_users, write_users
from utils.payment import create_payment

router = Router()

@router.message(F.text == "💳 Платежи")
async def handle_payments(message: types.Message, state: FSMContext):
    # Проверяем наличие активной подписки
    user_id = message.from_user.id
    users = load_users()
    
    if str(user_id) in users and users[str(user_id)].get('subscription', {}).get('active', False):
        subscription_until = users[str(user_id)]['subscription'].get('until')
        if subscription_until:
            try:
                until_date = datetime.strptime(subscription_until, '%Y-%m-%d')
                if until_date > datetime.now():
                    await message.answer(
                        f"✅ У вас уже есть активная подписка до {subscription_until}\n\n"
                        "Все PRO-функции уже доступны!",
                        parse_mode="HTML"
                    )
                    return
            except ValueError:
                # Если формат даты некорректный, продолжаем показ предложения
                pass

    text = (
        "🌟 <b>Преимущества подписки Tennis-Play PRO:</b>\n\n"
        "• Внесение результатов матча\n"
        "• Просмотр анкет всех игроков\n"
        "• Просмотр история игр игроков\n"
        "• Безлимитные заявки на игры\n\n"
        f"Стоимость: <b>{SUBSCRIPTION_PRICE} руб./месяц</b>"
    )
    
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
    users = load_users()
    
    if str(user_id) in users and users[str(user_id)].get('subscription', {}).get('active', False):
        subscription_until = users[str(user_id)]['subscription'].get('until')
        if subscription_until:
            try:
                until_date = datetime.strptime(subscription_until, '%Y-%m-%d')
                if until_date > datetime.now():
                    await callback.message.answer(
                        f"❌ У вас уже есть активная подписка до {subscription_until}\n\n"
                        "Невозможно купить подписку повторно, пока текущая активна.",
                        parse_mode="HTML"
                    )
                    await callback.answer()
                    return
            except ValueError:
                # Если формат даты некорректный, продолжаем процесс оплаты
                pass

    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY
    
    payment_link, payment_id = create_payment(callback.message.chat.id, SUBSCRIPTION_PRICE, "Оплата подписки для расширенего функционала")

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
    
    await callback.message.answer(
        f"💳 Для оплаты перейдите по ссылке:\n{payment_link}\n\n"
        "После успешной оплаты нажмите 'Подтвердить оплату'",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(PaymentStates.CONFIRM_PAYMENT)
    await callback.answer()

@router.callback_query(PaymentStates.CONFIRM_PAYMENT, F.data == "confirm_payment")
async def confirm_payment(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    payment_id = data.get('payment_id', 'не указан')
    
    payment = Payment.find_one(payment_id)
    
    # Удаляем предыдущее сообщение с кнопками оплаты
    try:
        await callback.message.delete()
    except:
        pass
    
    if payment.status == "succeeded":
        # Дополнительная проверка перед активацией подписки
        user_id = callback.message.chat.id
        users = load_users()
        
        if str(user_id) in users and users[str(user_id)].get('subscription', {}).get('active', False):
            subscription_until = users[str(user_id)]['subscription'].get('until')
            if subscription_until:
                try:
                    until_date = datetime.strptime(subscription_until, '%Y-%m-%d')
                    if until_date > datetime.now():
                        await callback.message.answer(
                            f"❌ У вас уже есть активная подписка до {subscription_until}\n\n"
                            "Деньги будут возвращены в течение 3-5 рабочих дней.",
                            reply_markup=base_keyboard
                        )
                        await state.clear()
                        await callback.answer()
                        return
                except ValueError:
                    # Если формат даты некорректный, продолжаем активацию
                    pass
        
        # Активируем подписку
        await callback.message.answer(
            "🎉 Поздравляем! Подписка успешно активирована.\n\n"
            "Доступ к PRO-функциям открыт на 30 дней.",
            reply_markup=base_keyboard
        )
        
        # Сохраняем информацию о подписке в базе данных
        user_id = callback.message.chat.id
        users = load_users()
        if str(user_id) not in users:
            users[str(user_id)] = {}
        
        users[str(user_id)]['subscription'] = {
            'active': True,
            'until': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'activated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        write_users(users)
    else:
        await callback.message.answer(
            "❌ Оплата не завершена, попробуйте снова",
            reply_markup=base_keyboard
        )
    
    await state.clear()
    await callback.answer()
