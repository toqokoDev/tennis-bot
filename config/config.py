import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
SUBSCRIPTION_PRICE = int(os.getenv('SUBSCRIPTION_PRICE', 300))
BOT_USERNAME = os.getenv('BOT_USERNAME')
CHANNEL_ID = os.getenv('CHANNEL_ID')
SHOP_ID = os.getenv('SHOP_ID')
SECRET_KEY = os.getenv('SECRET_KEY')
ITEMS_PER_PAGE = 10
TOURNAMENT_ENTRY_FEE = int(os.getenv('TOURNAMENT_ENTRY_FEE', 500))
API_BASE_URL = os.getenv('TENNIS_API_URL', 'https://tennis-play.by/profile/api.php')
API_SECRET_TOKEN = os.getenv('TENNIS_API_TOKEN', 'qTDrzUztf2CbdH3sUad9plkmfUryMNA5JAkX1HM2uXw')

# Email настройки
EMAIL_SMTP_HOST = os.getenv('EMAIL_SMTP_HOST', 'smtp.yandex.ru')
EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', 465))
EMAIL_SMTP_USERNAME = os.getenv('EMAIL_SMTP_USERNAME', 'info@tennis-play.com')
EMAIL_SMTP_PASSWORD = os.getenv('EMAIL_SMTP_PASSWORD', '1q2w3e1q')
EMAIL_FROM_ADDRESS = os.getenv('EMAIL_FROM_ADDRESS', 'info@tennis-play.com')
EMAIL_FROM_NAME = os.getenv('EMAIL_FROM_NAME', 'Tennis-Play.com')
EMAIL_ADMIN = os.getenv('EMAIL_ADMIN', 'toqoko@gmail.com') #promosite1@ya.ru

TINKOFF_TERMINAL_KEY = "25862619DE"
TINKOFF_PASSWORD = "l*5YOP%D8XdVSu!k"
TINKOFF_API_URL = "securepay.tinkoff.ru"

required_vars = ['TOKEN', 'BOT_USERNAME', 'CHANNEL_ID', 'SHOP_ID', 'SECRET_KEY']
for var in required_vars:
    if not os.getenv(var):
        raise ValueError(f"Необходимо установить переменную окружения {var}")
