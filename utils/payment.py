from yookassa import Payment
import uuid

from config.config import BOT_USERNAME

def create_payment(user_id, amount, description):
    """
    Создает платеж и возвращает ссылку для оплаты
    """
    payment = Payment.create({
        "amount": {
            "value": amount,
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{BOT_USERNAME}"
        },
        "capture": True,
        "description": description,
        "metadata": {
            "user_id": user_id,
            "order_id": str(uuid.uuid4())
        }
    })
    
    # Получаем ссылку для оплаты
    confirmation_url = payment.confirmation.confirmation_url
    payment_id = payment.id
    
    return confirmation_url, payment_id
