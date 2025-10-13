# Webhook API Documentation

Документация по использованию вебхуков для добавления туров и предложений игр.

## Базовый URL

По умолчанию сервер запускается на порту `8080`:
```
http://localhost:8080
```

## Авторизация

Все запросы должны содержать заголовок Authorization с токеном:
```
Authorization: Bearer YOUR_API_SECRET_TOKEN
```

Токен берется из переменной окружения `TENNIS_API_TOKEN`.

## Endpoints

### 1. Добавление тура

**POST** `/webhook/tour`

Добавляет информацию о туре пользователя и публикует её в канал.

#### Тело запроса (JSON):
```json
{
  "user_id": "123456789",
  "vacation_tennis": true,
  "vacation_start": "25.10.2025",
  "vacation_end": "25.11.2025",
  "vacation_country": "🇷🇺 Россия",
  "vacation_city": "Москва",
  "vacation_district": "",
  "vacation_comment": "Ищу партнёров для игры"
}
```

#### Параметры:
- `user_id` (string, обязательно) - Telegram ID пользователя
- `vacation_tennis` (boolean, опционально) - Флаг теннисного тура (по умолчанию `true`)
- `vacation_start` (string, обязательно) - Дата начала тура (формат: DD.MM.YYYY)
- `vacation_end` (string, обязательно) - Дата окончания тура (формат: DD.MM.YYYY)
- `vacation_country` (string, обязательно) - Страна тура
- `vacation_city` (string, обязательно) - Город тура
- `vacation_district` (string, опционально) - Район города
- `vacation_comment` (string, опционально) - Комментарий к туру

#### Пример запроса (curl):
```bash
curl -X POST http://localhost:8080/webhook/tour \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_SECRET_TOKEN" \
  -d '{
    "user_id": "123456789",
    "vacation_tennis": true,
    "vacation_start": "25.10.2025",
    "vacation_end": "25.11.2025",
    "vacation_country": "🇷🇺 Россия",
    "vacation_city": "Москва",
    "vacation_comment": "Ищу партнёров для игры"
  }'
```

#### Успешный ответ (200):
```json
{
  "status": "success",
  "message": "Tour data saved and posted to channel"
}
```

#### Ошибки:
- **401 Unauthorized** - Неверный токен авторизации
- **400 Bad Request** - Отсутствует user_id
- **404 Not Found** - Пользователь не найден
- **500 Internal Server Error** - Ошибка сервера

---

### 2. Добавление предложения игры

**POST** `/webhook/game_offer`

Добавляет предложение игры к профилю пользователя и публикует её в канал.

#### Тело запроса (JSON):
```json
{
  "user_id": "123456789",
  "sport": "🎾Большой теннис",
  "country": "🇧🇾 Беларусь",
  "city": "Могилёв",
  "district": null,
  "comment": "Жду на корте!",
  "date": "14.10",
  "time": "20:00",
  "type": "Одиночная",
  "payment_type": "Пополам",
  "competitive": true,
  "id": 1,
  "active": true
}
```

#### Параметры:
- `user_id` (string, обязательно) - Telegram ID пользователя
- `sport` (string, опционально) - Вид спорта (по умолчанию берется из профиля пользователя)
- `country` (string, обязательно) - Страна
- `city` (string, обязательно) - Город
- `district` (string, опционально) - Район города
- `comment` (string, опционально) - Комментарий к игре
- `date` (string, обязательно) - Дата игры (формат: DD.MM или YYYY-MM-DD)
- `time` (string, обязательно) - Время игры (формат: HH:MM)
- `type` (string, опционально) - Тип игры (по умолчанию "Одиночная")
- `payment_type` (string, опционально) - Тип оплаты (по умолчанию "Пополам")
- `competitive` (boolean, опционально) - Игра на счёт (по умолчанию `false`)
- `id` (number, опционально) - ID игры (по умолчанию генерируется автоматически)
- `created_at` (string, опционально) - Время создания (ISO формат, по умолчанию текущее время)
- `active` (boolean, опционально) - Активность игры (по умолчанию `true`)

#### Пример запроса (curl):
```bash
curl -X POST http://localhost:8080/webhook/game_offer \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_SECRET_TOKEN" \
  -d '{
    "user_id": "123456789",
    "country": "🇧🇾 Беларусь",
    "city": "Могилёв",
    "comment": "Жду на корте!",
    "date": "14.10",
    "time": "20:00",
    "type": "Одиночная",
    "payment_type": "Пополам",
    "competitive": true
  }'
```

#### Успешный ответ (200):
```json
{
  "status": "success",
  "message": "Game offer saved and posted to channel",
  "game_id": 1728842874
}
```

#### Ошибки:
- **401 Unauthorized** - Неверный токен авторизации
- **400 Bad Request** - Отсутствует user_id
- **404 Not Found** - Пользователь не найден
- **500 Internal Server Error** - Ошибка сервера

---

## Примеры использования (Python)

### Добавление тура:
```python
import requests

url = "http://localhost:8080/webhook/tour"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_API_SECRET_TOKEN"
}
data = {
    "user_id": "123456789",
    "vacation_start": "25.10.2025",
    "vacation_end": "25.11.2025",
    "vacation_country": "🇷🇺 Россия",
    "vacation_city": "Москва",
    "vacation_comment": "Ищу партнёров для игры"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

### Добавление предложения игры:
```python
import requests

url = "http://localhost:8080/webhook/game_offer"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_API_SECRET_TOKEN"
}
data = {
    "user_id": "123456789",
    "country": "🇧🇾 Беларусь",
    "city": "Могилёв",
    "date": "14.10",
    "time": "20:00",
    "type": "Одиночная",
    "payment_type": "Пополам",
    "competitive": True
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

## Примеры использования (PHP)

### Добавление тура:
```php
<?php
$url = 'http://localhost:8080/webhook/tour';
$data = [
    'user_id' => '123456789',
    'vacation_start' => '25.10.2025',
    'vacation_end' => '25.11.2025',
    'vacation_country' => '🇷🇺 Россия',
    'vacation_city' => 'Москва',
    'vacation_comment' => 'Ищу партнёров для игры'
];

$options = [
    'http' => [
        'header' => [
            'Content-Type: application/json',
            'Authorization: Bearer YOUR_API_SECRET_TOKEN'
        ],
        'method' => 'POST',
        'content' => json_encode($data)
    ]
];

$context = stream_context_create($options);
$result = file_get_contents($url, false, $context);
echo $result;
?>
```

### Добавление предложения игры:
```php
<?php
$url = 'http://localhost:8080/webhook/game_offer';
$data = [
    'user_id' => '123456789',
    'country' => '🇧🇾 Беларусь',
    'city' => 'Могилёв',
    'date' => '14.10',
    'time' => '20:00',
    'type' => 'Одиночная',
    'payment_type' => 'Пополам',
    'competitive' => true
];

$options = [
    'http' => [
        'header' => [
            'Content-Type: application/json',
            'Authorization: Bearer YOUR_API_SECRET_TOKEN'
        ],
        'method' => 'POST',
        'content' => json_encode($data)
    ]
];

$context = stream_context_create($options);
$result = file_get_contents($url, false, $context);
echo $result;
?>
```

## Замечания

1. Webhook сервер запускается автоматически вместе с ботом
2. По умолчанию используется порт 8080
3. Все данные автоматически публикуются в соответствующие Telegram каналы
4. Пользователь с указанным `user_id` должен быть уже зарегистрирован в боте
5. Прошедшие игры автоматически удаляются из списка раз в 24 часа

