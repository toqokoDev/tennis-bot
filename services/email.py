"""
Сервис для отправки email-сообщений
"""

import logging
import ssl
from typing import Optional, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib

from config.config import (
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_USERNAME,
    EMAIL_SMTP_PASSWORD,
    EMAIL_FROM_ADDRESS,
    EMAIL_FROM_NAME
)

logger = logging.getLogger(__name__)


class EmailService:
    """Сервис для отправки email через SMTP"""
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        username: str = None,
        password: str = None,
        from_address: str = None,
        from_name: str = None,
        use_tls: bool = True
    ):
        """
        Инициализация сервиса email
        
        Args:
            host: SMTP сервер
            port: Порт SMTP сервера
            username: Логин для SMTP
            password: Пароль для SMTP
            from_address: Email адрес отправителя
            from_name: Имя отправителя
            use_tls: Использовать TLS/SSL
        """
        self.host = host or EMAIL_SMTP_HOST
        self.port = port or EMAIL_SMTP_PORT
        self.username = username or EMAIL_SMTP_USERNAME
        self.password = password or EMAIL_SMTP_PASSWORD
        self.from_address = from_address or EMAIL_FROM_ADDRESS
        self.from_name = from_name or EMAIL_FROM_NAME
        self.use_tls = use_tls
    
    async def send_email(
        self,
        to: str | List[str],
        subject: str,
        body: str,
        html: bool = True,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> bool:
        """
        Отправка email-сообщения
        
        Args:
            to: Email получателя или список получателей
            subject: Тема письма
            body: Текст письма (HTML или plain text)
            html: Если True, тело будет отправлено как HTML
            cc: Список получателей копии
            bcc: Список получателей скрытой копии
            
        Returns:
            True если отправка успешна, False иначе
        """
        try:
            # Нормализуем список получателей
            if isinstance(to, str):
                to_list = [to]
            else:
                to_list = to
            
            # Создаем сообщение
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = f"{self.from_name} <{self.from_address}>"
            message['To'] = ', '.join(to_list)
            
            if cc:
                message['Cc'] = ', '.join(cc)
            
            # Добавляем тело письма
            charset = 'utf-8'
            if html:
                part = MIMEText(body, 'html', charset)
            else:
                part = MIMEText(body, 'plain', charset)
            message.attach(part)
            
            # Собираем всех получателей
            recipients = to_list.copy()
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)
            
            # Определяем параметры подключения
            # Для порта 465 используем TLS с самого начала (use_tls=True)
            # Для порта 587 используем STARTTLS (start_tls=True)
            
            if self.port == 465:
                # SSL/TLS соединение с самого начала
                smtp_client = aiosmtplib.SMTP(
                    hostname=self.host,
                    port=self.port,
                    use_tls=True,  # SSL/TLS с самого начала
                    tls_context=ssl.create_default_context(),
                    start_tls=False
                )
            elif self.port == 587:
                # STARTTLS (сначала обычное соединение, потом апгрейд)
                smtp_client = aiosmtplib.SMTP(
                    hostname=self.host,
                    port=self.port,
                    use_tls=False,  # Без TLS изначально
                    start_tls=True  # Используем STARTTLS
                )
            else:
                # Для других портов настройте по необходимости
                smtp_client = aiosmtplib.SMTP(
                    hostname=self.host,
                    port=self.port
                )
            
            try:
                await smtp_client.connect()
                
                # Для порта 587 нужно явно вызвать STARTTLS
                if self.port == 587:
                    await smtp_client.starttls()
                
                if self.username and self.password:
                    await smtp_client.login(self.username, self.password)
                
                # Отправляем всем получателям
                await smtp_client.send_message(
                    message, 
                    sender=self.from_address,
                    recipients=recipients
                )
                
            finally:
                try:
                    await smtp_client.quit()
                except:
                    pass  # Игнорируем ошибки при закрытии соединения
            
            logger.info(f"Email успешно отправлен. Тема: {subject} на {', '.join(to_list)}")
            return True
            
        except aiosmtplib.SMTPException as e:
            logger.error(f"Ошибка SMTP при отправке email: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка отправки email на {to}: {e}", exc_info=True)
            return False
    
    async def send_html_email(
        self,
        to: str | List[str],
        subject: str,
        html_body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> bool:
        """
        Отправка HTML email (удобный метод-обертка)
        
        Args:
            to: Email получателя или список получателей
            subject: Тема письма
            html_body: HTML содержимое письма
            cc: Список получателей копии
            bcc: Список получателей скрытой копии
            
        Returns:
            True если отправка успешна, False иначе
        """
        return await self.send_email(
            to=to,
            subject=subject,
            body=html_body,
            html=True,
            cc=cc,
            bcc=bcc
        )
    
    async def send_text_email(
        self,
        to: str | List[str],
        subject: str,
        text_body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> bool:
        """
        Отправка plain text email (удобный метод-обертка)
        
        Args:
            to: Email получателя или список получателей
            subject: Тема письма
            text_body: Текстовое содержимое письма
            cc: Список получателей копии
            bcc: Список получателей скрытой копии
            
        Returns:
            True если отправка успешна, False иначе
        """
        return await self.send_email(
            to=to,
            subject=subject,
            body=text_body,
            html=False,
            cc=cc,
            bcc=bcc
        )


# Создаем глобальный экземпляр сервиса
email_service = EmailService()
