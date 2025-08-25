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
ITEMS_PER_PAGE = 5

required_vars = ['TOKEN', 'BOT_USERNAME', 'CHANNEL_ID', 'SHOP_ID', 'SECRET_KEY']
for var in required_vars:
    if not os.getenv(var):
        raise ValueError(f"Необходимо установить переменную окружения {var}")