# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем системные шрифты и локали для корректного Unicode-рендеринга
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       fonts-dejavu \
       fontconfig \
       locales \
       libfreetype6 \
    && sed -i 's/^# *ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen \
    && sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && fc-cache -f -v \
    && rm -rf /var/lib/apt/lists/*

# Глобальные переменные окружения UTF-8
ENV LANG=ru_RU.UTF-8 \
    LC_ALL=ru_RU.UTF-8 \
    PYTHONIOENCODING=UTF-8

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы приложения
COPY . .

VOLUME /app/data

# Команда для запуска приложения
CMD ["python", "main.py"]