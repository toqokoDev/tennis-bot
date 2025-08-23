# Tennis Bot 🎾
Telegram-бот для организации теннисных матчей и других спортивных мероприятий.

## Quick Start

### Installation & Deployment
```docker build -t tennis-bot . && docker run -d -p 8850:8850 --name tennis-container-bot tennis-bot```

### Stop and remove container
```docker stop tennis-container-bot && docker rm tennis-container-bot```

### Monitor logs
```docker logs -f tennis-container-bot```

### Check status
```docker ps -a | grep tennis-container-bot```
