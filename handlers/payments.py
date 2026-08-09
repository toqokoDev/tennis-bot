from yookassa import Configuration
from datetime import datetime, timedelta
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import SECRET_KEY, SHOP_ID, SUBSCRIPTION_PRICE
from config.profile import get_base_keyboard
from models.states import PaymentStates
from services.payments import check_tinkoff_payment_status, generate_tinkoff_payment_link
from services.storage import storage
from utils.email import send_payment_notification_to_admin
from utils.translations import get_user_language_async, t
import logging

logger = logging.getLogger(__name__)

router = Router()


def _check_payment_keyboard(language: str) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(
        text=t("payments.check_payment_button", language),
        callback_data="check_payment",
    ))
    return builder.as_markup()


async def _save_pending_payment(user_id: int, payment_id, email: str, payment_link: str | None = None) -> None:
    users = await storage.load_users()
    user_key = str(user_id)
    if user_key not in users:
        users[user_key] = {}
    users[user_key]["pending_payment"] = {
        "payment_id": str(payment_id),
        "email": email,
        "payment_link": payment_link,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    await storage.save_users(users)


async def _clear_pending_payment(user_id: int) -> None:
    users = await storage.load_users()
    user_key = str(user_id)
    if user_key in users and "pending_payment" in users[user_key]:
        users[user_key].pop("pending_payment", None)
        await storage.save_users(users)


async def _get_pending_payment(user_id: int) -> dict | None:
    users = await storage.load_users()
    pending = users.get(str(user_id), {}).get("pending_payment")
    if not pending or not pending.get("payment_id"):
        return None
    return pending


async def _activate_subscription(user_id: int, user_email: str, payment_id) -> None:
    users = await storage.load_users()
    user_key = str(user_id)
    if user_key not in users:
        users[user_key] = {}

    users[user_key]["subscription"] = {
        "active": True,
        "until": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "activated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "email": user_email,
    }
    users[user_key].pop("pending_payment", None)
    await storage.save_users(users)

    await send_payment_notification_to_admin(
        user_id=user_id,
        profile=users[user_key],
        payment_id=payment_id,
        user_email=user_email,
        payment_amount=SUBSCRIPTION_PRICE,
    )


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
    builder.row(types.InlineKeyboardButton(
        text=t("payments.buy_subscription_button", language),
        callback_data="buy_subscription",
    ))
    builder.row(types.InlineKeyboardButton(
        text=t("payments.check_payment_button", language),
        callback_data="check_payment",
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
    
    language = await get_user_language_async(str(message.chat.id))
    if '@' not in email or '.' not in email:
        await message.answer(
            t("payments.invalid_email", language)
        )
        return
    
    await state.update_data(user_email=email)
    
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY
    
    try:
        payment_link, payment_id = await generate_tinkoff_payment_link(
            message.chat.id, 
            SUBSCRIPTION_PRICE, 
            "Оплата подписки для расширенного функционала",
            email
        )

        if not isinstance(payment_link, str) or not payment_link.startswith(("http://", "https://")):
            raise RuntimeError(f"Некорректная ссылка на оплату: {payment_link!r}")
        
        await state.update_data(payment_id=payment_id)
        await _save_pending_payment(message.chat.id, payment_id, email, payment_link)
        
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(
            text=t("payments.go_to_payment_button", language), 
            url=payment_link
        ))
        builder.row(types.InlineKeyboardButton(
            text=t("payments.confirm_payment_button", language), 
            callback_data="confirm_payment"
        ))
        builder.row(types.InlineKeyboardButton(
            text=t("payments.check_payment_button", language),
            callback_data="check_payment",
        ))
        
        language = await get_user_language_async(str(message.chat.id))
        await message.answer(
            t("payments.payment_link", language, link=payment_link, email=email),
            reply_markup=builder.as_markup()
        )
        
        await state.set_state(PaymentStates.CONFIRM_PAYMENT)
        
    except Exception as e:
        logger.exception("Ошибка при создании платежа Tinkoff для user_id=%s", message.chat.id)
        language = await get_user_language_async(str(message.chat.id))
        await message.answer(
            t("payments.payment_created_error", language, error=str(e))
        )
        await state.clear()


@router.callback_query(F.data.in_({"confirm_payment", "check_payment"}))
async def confirm_payment(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.message.chat.id
    language = await get_user_language_async(str(user_id))

    data = await state.get_data()
    pending = await _get_pending_payment(user_id)

    payment_id = data.get("payment_id") or (pending or {}).get("payment_id")
    user_email = data.get("user_email") or (pending or {}).get("email") or "не указан"

    if not payment_id:
        await callback.answer(
            t("payments.no_pending_payment", language),
            show_alert=True,
        )
        return

    try:
        payment = await check_tinkoff_payment_status(payment_id)

        if payment.get("status") == "CONFIRMED":
            users = await storage.load_users()

            if str(user_id) in users and users[str(user_id)].get("subscription", {}).get("active", False):
                subscription_until = users[str(user_id)]["subscription"].get("until")
                if subscription_until:
                    try:
                        until_date = datetime.strptime(subscription_until, "%Y-%m-%d")
                        if until_date > datetime.now():
                            profile = await storage.get_user(user_id) or {}
                            sport = profile.get("sport", "🎾Большой теннис")
                            await _clear_pending_payment(user_id)
                            await callback.message.answer(
                                t("payments.subscription_active_refund", language, date=subscription_until),
                                reply_markup=get_base_keyboard(sport, language=language),
                            )
                            await state.clear()
                            await callback.answer()
                            return
                    except ValueError:
                        pass

            profile = await storage.get_user(user_id) or {}
            sport = profile.get("sport", "🎾Большой теннис")
            await _activate_subscription(user_id, user_email, payment_id)
            await callback.message.answer(
                t("payments.payment_success", language, email=user_email),
                reply_markup=get_base_keyboard(sport, language=language),
            )
            await state.clear()
            await callback.answer()
            return

        await callback.message.answer(
            t("payments.payment_not_completed", language),
            reply_markup=_check_payment_keyboard(language),
        )
        await state.set_state(PaymentStates.CONFIRM_PAYMENT)
        await state.update_data(payment_id=payment_id, user_email=user_email)

    except Exception as e:
        logger.exception("Ошибка проверки платежа Tinkoff для user_id=%s payment_id=%s", user_id, payment_id)
        await callback.message.answer(
            t("payments.payment_check_error", language, error=str(e)),
            reply_markup=_check_payment_keyboard(language),
        )
        await state.set_state(PaymentStates.CONFIRM_PAYMENT)
        await state.update_data(payment_id=payment_id, user_email=user_email)

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
