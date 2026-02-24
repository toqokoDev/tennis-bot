import os
import uuid
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

# Ваши константы
TINKOFF_TERMINAL_KEY = os.getenv('TINKOFF_TERMINAL_KEY', '0000')
TINKOFF_PASSWORD = os.getenv('TINKOFF_PASSWORD', '111111111')

TINKOFF_API_URL = "https://securepay.tinkoff.ru/v2/Init"
TINKOFF_STATUS_URL = "https://securepay.tinkoff.ru/v2/GetState"

def generate_tinkoff_payment_link(amount_rub, description="Оплата заказа"):
    order_id = str(uuid.uuid4())
    
    payload = {
        "TerminalKey": TINKOFF_TERMINAL_KEY,
        "Amount": int(amount_rub * 100),
        "OrderId": str(order_id),
        "Description": description,
    }

    params_for_token = payload.copy()
    params_for_token["Password"] = TINKOFF_PASSWORD
    sorted_keys = sorted(params_for_token.keys())
    
    token_string = "".join(str(params_for_token[key]) for key in sorted_keys)
    payload["Token"] = hashlib.sha256(token_string.encode('utf-8')).hexdigest()

    try:
        response = requests.post(TINKOFF_API_URL, json=payload)
        response_data = response.json()

        if response_data.get("Success"):
            return {
                "success": True,
                "payment_url": response_data.get("PaymentURL"),
                "payment_id": response_data.get("PaymentId")
            }
        else:
            return {
                "success": False, 
                "message": response_data.get("Message"),
                "details": response_data.get("Details")
            }

    except Exception as e:
        return {"success": False, "error": str(e)}
 
def check_tinkoff_payment_status(payment_id):
    """
    Проверяет текущий статус платежа по его PaymentId.
    """
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

if __name__ == "__main__":
    # result = generate_tinkoff_payment_link(100, "Тестовая")
    # print(result)
    status_result = check_tinkoff_payment_status(7983702106)
    print(f"Статус заказа: {status_result['status']}")
