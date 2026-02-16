from datetime import datetime

from config.config import EMAIL_ADMIN
from services.email import email_service
from utils.utils import remove_country_flag


def _simple_email_style() -> str:
    """Чёрно-белые стили для писем"""
    return """
        body { font-family: Arial, sans-serif; font-size: 14px; color: #000; max-width: 500px; margin: 0 auto; padding: 16px; }
        h2 { font-size: 16px; margin: 0 0 12px 0; }
        .row { margin: 6px 0; }
        .label { font-weight: bold; }
        .footer { margin-top: 16px; font-size: 11px; color: #333; }
    """


async def send_payment_notification_to_admin(
    user_id: int,
    profile: dict,
    payment_id: str,
    user_email: str,
    payment_amount: int
):
    """Отправляет администратору email об оплате подписки — только важная инфа, ч/б."""
    try:
        first_name = profile.get('first_name', '—')
        last_name = profile.get('last_name', '—')
        phone = profile.get('phone', '—')
        username = profile.get('username', '')
        sport = profile.get('sport', '—')
        city = profile.get('city', '—')
        country = remove_country_flag(profile.get('country', '—'))
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{_simple_email_style()}</style></head>
<body>
    <h2>Оплата подписки</h2>
    <div class="row"><span class="label">Сумма:</span> {payment_amount} руб.</div>
    <div class="row"><span class="label">ID:</span> {payment_id}</div>
    <div class="row"><span class="label">Дата:</span> {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>
    <hr style="border: none; border-top: 1px solid #000;">
    <div class="row"><span class="label">Имя:</span> {first_name} {last_name}</div>
    <div class="row"><span class="label">Email:</span> {user_email}</div>
    <div class="row"><span class="label">Телефон:</span> {phone}</div>
    <div class="row"><span class="label">TG ID:</span> {user_id}</div>
    <div class="row"><span class="label">@username:</span> {('@' + username) if username else '—'}</div>
    <div class="row"><span class="label">Спорт:</span> {sport}</div>
    <div class="row"><span class="label">Город:</span> {city}, {country}</div>
    <div class="footer">Tennis-Play Bot · {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>
</body>
</html>
        """
        await email_service.send_html_email(
            to=EMAIL_ADMIN,
            subject=f"Оплата подписки — {first_name} {last_name}",
            html_body=html_body
        )
        print(f"[{datetime.now()}] Письмо об оплате подписки отправлено для {user_id}")
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка отправки письма об оплате подписки: {e}")


async def send_tournament_payment_notification_to_admin(
    user_id: int,
    profile: dict,
    payment_id: str,
    user_email: str,
    payment_amount: int,
    tournament_name: str,
    tournament_id: str
):
    """Отправляет администратору email об оплате участия в турнире — только важная инфа, ч/б."""
    try:
        first_name = profile.get('first_name', '—')
        last_name = profile.get('last_name', '—')
        phone = profile.get('phone', '—')
        username = profile.get('username', '')
        sport = profile.get('sport', '—')
        city = profile.get('city', '—')
        country = remove_country_flag(profile.get('country', '—'))
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{_simple_email_style()}</style></head>
<body>
    <h2>Оплата турнира</h2>
    <div class="row"><span class="label">Турнир:</span> {tournament_name}</div>
    <div class="row"><span class="label">ID турнира:</span> {tournament_id}</div>
    <div class="row"><span class="label">Сумма:</span> {payment_amount} руб.</div>
    <div class="row"><span class="label">ID платежа:</span> {payment_id}</div>
    <div class="row"><span class="label">Дата:</span> {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>
    <hr style="border: none; border-top: 1px solid #000;">
    <div class="row"><span class="label">Имя:</span> {first_name} {last_name}</div>
    <div class="row"><span class="label">Email:</span> {user_email}</div>
    <div class="row"><span class="label">Телефон:</span> {phone}</div>
    <div class="row"><span class="label">TG ID:</span> {user_id}</div>
    <div class="row"><span class="label">@username:</span> {('@' + username) if username else '—'}</div>
    <div class="row"><span class="label">Спорт:</span> {sport}</div>
    <div class="row"><span class="label">Город:</span> {city}, {country}</div>
    <div class="footer">Tennis-Play Bot · {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>
</body>
</html>
        """
        await email_service.send_html_email(
            to=EMAIL_ADMIN,
            subject=f"Оплата турнира — {first_name} {last_name} · {tournament_name}",
            html_body=html_body
        )
        print(f"[{datetime.now()}] Письмо об оплате турнира отправлено для {user_id}")
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка отправки письма об оплате турнира: {e}")
