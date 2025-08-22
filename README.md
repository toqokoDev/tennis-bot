Tennis-bot
Телеграмм бот для игры в теннис и не только

команда для запуска:
docker build -t tennis-bot . && docker run -d -p 8850:8850 --name tennis-container-bot tennis-bot

команда для удаления:
docker stop tennis-container-bot && docker rm tennis-container-bot

просмотр логов:
docker logs -f tennis-container-bot