"""
Сервис для отправки email-сообщений
"""

import logging
import re
import ssl
from typing import Optional, List, Tuple
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


def _html_to_plain_text(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?(p|div|tr|li|h[1-6])[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip() or "HTML-версия письма"


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
        bcc: Optional[List[str]] = None,
        return_smtp_response: bool = False,
    ) -> bool | Tuple[bool, str]:
        """
        Отправка email-сообщения
        
        Args:
            to: Email получателя или список получателей
            subject: Тема письма
            body: Текст письма (HTML или plain text)
            html: Если True, тело будет отправлено как HTML
            cc: Список получателей копии
            bcc: Список получателей скрытой копии
            return_smtp_response: Вернуть ответ SMTP-сервера
            
        Returns:
            True если SMTP принял письмо, False иначе.
            При return_smtp_response=True — кортеж (успех, ответ сервера).
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
                message.attach(MIMEText(_html_to_plain_text(body), 'plain', charset))
                message.attach(MIMEText(body, 'html', charset))
            else:
                message.attach(MIMEText(body, 'plain', charset))
            
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
                smtp_response = await smtp_client.send_message(
                    message,
                    sender=self.from_address,
                    recipients=recipients
                )
                
            finally:
                try:
                    await smtp_client.quit()
                except:
                    pass  # Игнорируем ошибки при закрытии соединения

            server_message = ""
            if isinstance(smtp_response, tuple) and len(smtp_response) == 2:
                server_message = str(smtp_response[1])

            logger.info(
                "Email принят SMTP-сервером. Тема: %s, получатели: %s, ответ: %s",
                subject,
                ", ".join(to_list),
                server_message or "ok",
            )
            if return_smtp_response:
                return True, server_message
            return True
            
        except aiosmtplib.SMTPException as e:
            logger.error(f"Ошибка SMTP при отправке email: {e}")
            if return_smtp_response:
                return False, str(e)
            return False
        except Exception as e:
            logger.error(f"Ошибка отправки email на {to}: {e}", exc_info=True)
            if return_smtp_response:
                return False, str(e)
            return False
    
    async def send_html_email(
        self,
        to: str | List[str],
        subject: str,
        html_body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        return_smtp_response: bool = False,
    ) -> bool | Tuple[bool, str]:
        return await self.send_email(
            to=to,
            subject=subject,
            body=html_body,
            html=True,
            cc=cc,
            bcc=bcc,
            return_smtp_response=return_smtp_response,
        )
    
    async def send_text_email(
        self,
        to: str | List[str],
        subject: str,
        text_body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        return_smtp_response: bool = False,
    ) -> bool | Tuple[bool, str]:
        return await self.send_email(
            to=to,
            subject=subject,
            body=text_body,
            html=False,
            cc=cc,
            bcc=bcc,
            return_smtp_response=return_smtp_response,
        )


# Создаем глобальный экземпляр сервиса
email_service = EmailService()
