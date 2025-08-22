from pathlib import Path

async def download_photo_to_path(bot, file_id: str, dest_path: Path) -> bool:
    try:
        file = await bot.get_file(file_id)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await bot.download(file, destination=dest_path)
        except Exception:
            await bot.download_file(file.file_path, destination=dest_path)
        return True
    except Exception:
        return False
    
async def save_media_file(bot, file_id, media_type: str, game_id: str) -> str:
    # Получаем информацию о файле
    file = await bot.get_file(file_id)
    file_extension = file.file_path.split('.')[-1] if file.file_path else 'jpg'
    
    # Формируем имя файла
    filename = f"{game_id}_{media_type}.{file_extension}"
    file_path = f"data/games_photo/{filename}"
    
    # Скачиваем файл
    await bot.download_file(file.file_path, file_path)
    
    return filename
