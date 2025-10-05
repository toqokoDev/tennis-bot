from datetime import datetime

async def validate_date(date_str: str) -> bool:
    """Проверяет корректность даты в формате ДД.ММ.ГГГГ"""
    try:
        # Проверяем, что строка содержит ровно 2 точки
        if date_str.count('.') != 2:
            return False
            
        parts = date_str.split('.')
        
        # Проверяем, что все части состоят из цифр
        if not all(part.isdigit() for part in parts):
            return False
            
        # Проверяем, что год состоит из 4 символов
        if len(parts[2]) != 4:
            return False
            
        day, month, year = map(int, parts)
        
        # Проверяем, что дата корректна
        datetime(year=year, month=month, day=day)
        return True
        
    except (ValueError, AttributeError):
        return False

async def validate_future_date(date_str: str) -> bool:
    """Проверяет что дата в будущем"""
    try:
        day, month, year = map(int, date_str.split('.'))
        input_date = datetime(year=year, month=month, day=day)
        return input_date >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    except (ValueError, AttributeError):
        return False

async def validate_date_range(start_date: str, end_date: str) -> bool:
    """Проверяет что end_date после start_date"""
    try:
        if not start_date or not end_date:
            return False
        start = datetime.strptime(start_date, "%d.%m.%Y")
        end = datetime.strptime(end_date, "%d.%m.%Y")
        return end > start
    except (ValueError, AttributeError, TypeError):
        return False

async def validate_price(price_str: str) -> bool:
    """Проверяет что цена - положительное число"""
    try:
        price = int(price_str)
        return price > 0
    except ValueError:
        return False

async def validate_time(time_str: str) -> bool:
    """Проверяет корректность времени в формате ЧЧ:ММ"""
    try:
        hours, minutes = map(int, time_str.split(':'))
        return 0 <= hours <= 23 and 0 <= minutes <= 59
    except (ValueError, AttributeError):
        return False
