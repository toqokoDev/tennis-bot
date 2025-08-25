import uuid
from yookassa import Payment

from config.config import BOT_USERNAME

async def create_payment(user_id, amount, description, email=None):
    """
    Создает платеж и возвращает ссылку для оплаты
    """
    payment_data = {
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
    }
    
    # Добавляем чек, если есть email
    if email:
        payment_data["receipt"] = {
            "customer": {
                "email": email
            },
            "items": [
                {
                    "description": description[:128],
                    "quantity": "1",
                    "amount": {
                        "value": amount,
                        "currency": "RUB"
                    },
                    "vat_code": 1,  # НДС 20%
                    "payment_mode": "full_payment",
                    "payment_subject": "service"
                }
            ]
        }
    
    payment = Payment.create(payment_data)
    
    # Получаем ссылку для оплаты
    confirmation_url = payment.confirmation.confirmation_url
    payment_id = payment.id
    
    return confirmation_url, payment_id
