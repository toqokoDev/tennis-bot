# Tennis Bot 🎾
Telegram-бот для организации теннисных матчей и других спортивных мероприятий.

## Быстрый старт

### Создание тома   
```docker volume create tennis-bot-data```

### Установка и запуск
```docker build -t tennis-bot . && docker run -d --name tennis-container-bot --env-file .env -v tennis-bot-data:/app/data --restart unless-stopped tennis-bot```

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