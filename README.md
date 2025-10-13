# Tennis Bot 🎾
Telegram-бот для организации теннисных матчей и других спортивных мероприятий.

## Основные возможности

- 🎾 Организация теннисных матчей и турниров
- 👥 Поиск партнеров для игры
- 📊 Система рейтинга игроков
- 🏆 Создание и управление турнирами
- 💳 Интеграция с системой оплаты
- 🌐 **Webhook API для интеграции с веб-сайтами**

## Webhook API

Бот включает HTTP API для интеграции с внешними приложениями:
- Добавление туров пользователей
- Создание предложений игр
- Автоматическая публикация в Telegram каналы

## Быстрый старт

### Создание тома   
```docker volume create tennis-bot-data```

### Установка и запуск
```docker build -t tennis-bot . && docker run -d --name tennis-container-bot --env-file .env -v tennis-bot-data:/app/data -p 8080:8080 --restart unless-stopped tennis-bot```

> **Примечание:** Флаг `-p 8080:8080` открывает порт для Webhook API. Если вам не нужен webhook API, можете его убрать.

### Остановка и удаление контейнера
```docker stop tennis-container-bot && docker rm tennis-container-bot```

### Просмотр логов в реальном времени
```docker logs -f tennis-container-bot```

### Проверка статуса контейнера
```docker ps -a | grep tennis-container-bot```

### Просмотр списка томов
```docker volume ls```

### Создание резервной копии данных
```docker run --rm -v tennis-bot-data:/source -v $(pwd):/backup alpine tar czf /backup/tennis-bot-backup-$(date +%Y%m%d).tar.gz -C /source .```

### Полная остановка и удаление бота
```docker stop tennis-container-bot && docker rm tennis-container-bot && docker volume rm tennis-bot-data```