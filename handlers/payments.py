from yookassa import Configuration, Payment
from datetime import datetime, timedelta
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import StateFilter

from config.config import SECRET_KEY, SHOP_ID, SUBSCRIPTION_PRICE
from config.profile import base_keyboard
from models.states import PaymentStates
from services.payments import create_payment
from services.storage import storage

router = Router()

@router.message(F.text == "💳 Платежи")
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
                    await message.answer(
                        f"✅ У вас уже есть активная подписка до {subscription_until}\n\n"
                        "Все PRO-функции уже доступны!",
                        parse_mode="HTML"
                    )
                    return
            except ValueError:
                pass

    text = (
        "🌟 <b>Преимущества подписки Tennis-Play PRO:</b>\n\n"
        "• Внесение результатов матча\n"
        "• Просмотр анкет всех игроков\n"
        "• Просмотр история игр игроков\n"
        "• Безлимитные заявки на игры\n\n"
        f"Стоимость: <b>{SUBSCRIPTION_PRICE} руб./месяц</b>\n\n"
        "Также вы можете получить подписку бесплатно, пригласив 10 друзей.\n"
        "Ваша персональная ссылка для приглашений доступна в разделе «🔗 Пригласить друга».\n\n"
        "💡 <i>Для оформления чека потребуется ваш email</i>"
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
    users = await storage.load_users()
    
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
                pass

    # Запрашиваем email для чека
    await callback.message.answer(
        "📧 Для оформления электронного чека укажите ваш email:\n\n"
        "<i>На этот email будет отправлен чек об оплате</i>",
        parse_mode="HTML"
    )
    
    await state.set_state(PaymentStates.WAITING_EMAIL)
    await callback.answer()

@router.message(PaymentStates.WAITING_EMAIL, F.text)
async def process_email_input(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    # Простая валидация email
    if '@' not in email or '.' not in email:
        await message.answer(
            "❌ Неверный формат email. Пожалуйста, введите корректный email:\n\n"
            "Пример: example@mail.ru"
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
        
        await message.answer(
            f"💳 Для оплаты перейдите по ссылке:\n{payment_link}\n\n"
            "После успешной оплаты нажмите 'Подтвердить оплату'\n\n"
            f"📧 Чек будет отправлен на: {email}",
            reply_markup=builder.as_markup()
        )
        
        await state.set_state(PaymentStates.CONFIRM_PAYMENT)
        
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при создании платежа: {str(e)}\n\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку."
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
                            await callback.message.answer(
                                f"❌ У вас уже есть активная подписка до {subscription_until}\n\n"
                                "Деньги будут возвращены в течение 3-5 рабочих дней.",
                                reply_markup=base_keyboard
                            )
                            await state.clear()
                            await callback.answer()
                            return
                    except ValueError:
                        pass
            
            # Активируем подписку
            await callback.message.answer(
                f"🎉 Поздравляем! Подписка успешно активирована.\n\n"
                f"Доступ к PRO-функциям открыт на 30 дней.\n"
                f"📧 Чек отправлен на: {user_email}",
                reply_markup=base_keyboard
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
        else:
            await callback.message.answer(
                "❌ Оплата не завершена или еще обрабатывается.\n\n"
                "Пожалуйста, подождите несколько минут и попробуйте снова.",
                reply_markup=base_keyboard
            )
        
    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка при проверке платежа: {str(e)}\n\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку.",
            reply_markup=base_keyboard
        )
    
    await state.clear()
    await callback.answer()

# Обработка отмены ввода email
@router.message(PaymentStates.WAITING_EMAIL, F.text == "/cancel")
async def cancel_email_input(message: types.Message, state: FSMContext):
    await message.answer(
        "❌ Ввод email отменен.\n\n"
        "Вы можете вернуться к оплате позже.",
        reply_markup=base_keyboard
    )
    await state.clear()
