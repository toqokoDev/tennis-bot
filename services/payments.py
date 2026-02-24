import uuid
import hashlib
import httpx
from yookassa import Payment

from config.config import BOT_USERNAME, TINKOFF_BASE_URL, TINKOFF_PASSWORD, TINKOFF_TERMINAL_KEY

async def generate_yookassa_payment_link(user_id, amount, description, email=None):
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

async def check_yookassa_payment_status(payment_id):
    status_result = Payment.find_one(payment_id)

    return status_result.status == "succeeded"

def generate_tinkoff_token(payload: dict) -> str:
    """
    Генерирует токен. Важно: объекты DATA и Receipt исключаются.
    """
    data_for_token = {k: v for k, v in payload.items() if k not in ("DATA", "Receipt")}
    data_for_token["Password"] = TINKOFF_PASSWORD
    
    sorted_keys = sorted(data_for_token.keys())
    token_string = "".join(str(data_for_token[key]) for key in sorted_keys)
    
    return hashlib.sha256(token_string.encode('utf-8')).hexdigest()

async def generate_tinkoff_payment_link(user_id, amount_rub, description, email=None):
    url = f"{TINKOFF_BASE_URL}/Init"
    
    amount_kopeeks = int(amount_rub * 100)
    order_id = str(uuid.uuid4())
    
    payload = {
        "TerminalKey": TINKOFF_TERMINAL_KEY,
        "Amount": amount_kopeeks,
        "OrderId": str(order_id),
        "Description": description,
        "DATA": {
            "user_id": str(user_id)
        },
        "Receipt": {
            "Email": email,
            "Taxation": "usn_income",
            "Items": [
                {
                    "Name": description,
                    "Price": amount_kopeeks,
                    "Quantity": 1.00,
                    "Amount": amount_kopeeks,
                    "Tax": "none"
                }
            ]
        }
    }
    
    payload["Token"] = generate_tinkoff_token(payload)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            data = response.json()

            if data.get("Success"):
                return data.get("PaymentURL"), data.get("PaymentId") 
            return {"success": False, "message": data.get("Message"), "details": data.get("Details")}
        except Exception as e:
            return {"success": False, "error": str(e)}
        
async def check_tinkoff_payment_status(payment_id):
    url = f"{TINKOFF_BASE_URL}/GetState"
    payload = {
        "TerminalKey": TINKOFF_TERMINAL_KEY,
        "PaymentId": str(payment_id),
    }
    payload["Token"] = generate_tinkoff_token(payload)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("Success"):
                return {
                    "success": True,
                    "status": data.get("Status"),
                    "order_id": data.get("OrderId"),
                    "amount": data.get("Amount")
                }
            return {"success": False, "message": data.get("Message")}
        except Exception as e:
            return {"success": False, "error": str(e)}
    payload = {
        "TerminalKey": TINKOFF_TERMINAL_KEY,
        "PaymentId": str(payment_id),
    }

    params_for_token = payload.copy()
    params_for_token["Password"] = TINKOFF_PASSWORD
    
    sorted_keys = sorted(params_for_token.keys())
    token_string = "".join(str(params_for_token[key]) for key in sorted_keys)
    payload["Token"] = hashlib.sha256(token_string.encode('utf-8')).hexdigest()

    try:
        response = requests.post(TINKOFF_STATUS_URL, json=payload)
        data = response.json()

        if data.get("Success"):
            return {
                "success": True,
                "status": data.get("Status"),
                "order_id": data.get("OrderId"),
                "amount": data.get("Amount")
            }
        else:
            return {
                "success": False,
                "message": data.get("Message")
            }

    except Exception as e:
        return {"success": False, "error": str(e)}
