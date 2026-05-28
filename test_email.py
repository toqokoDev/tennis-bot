#!/usr/bin/env python3
"""
Скрипт для тестирования отправки писем бота.

Использует те же шаблоны, что send_payment_notification_to_admin
и send_tournament_payment_notification_to_admin.

Примеры:
  python test_email.py subscription --to you@example.com
  python test_email.py subscription --to you@example.com --first-name Ivan --amount 300
  python test_email.py tournament --to you@example.com --tournament-name "Кубок весны"
  python test_email.py check-smtp --to you@example.com --smtp-password YOUR_APP_PASSWORD
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# config.py требует переменные бота — подставляем заглушки, если их нет
for _var in ("TOKEN", "BOT_USERNAME", "CHANNEL_ID", "SHOP_ID", "SECRET_KEY"):
    os.environ.setdefault(_var, "test")

import config.config as cfg
import utils.email as email_utils
from services.email import EmailService


def _build_profile(args: argparse.Namespace) -> dict:
    return {
        "first_name": args.first_name,
        "last_name": args.last_name,
        "phone": args.phone,
        "username": args.username,
        "sport": args.sport,
        "city": args.city,
        "country": args.country,
    }


def _apply_smtp_overrides(args: argparse.Namespace) -> None:
    if args.smtp_host:
        cfg.EMAIL_SMTP_HOST = args.smtp_host
    if args.smtp_port:
        cfg.EMAIL_SMTP_PORT = args.smtp_port
    if args.smtp_user:
        cfg.EMAIL_SMTP_USERNAME = args.smtp_user
    if args.smtp_password:
        cfg.EMAIL_SMTP_PASSWORD = args.smtp_password
    if args.from_address:
        cfg.EMAIL_FROM_ADDRESS = args.from_address
    if args.from_name:
        cfg.EMAIL_FROM_NAME = args.from_name

    email_utils.email_service = EmailService(
        host=cfg.EMAIL_SMTP_HOST,
        port=cfg.EMAIL_SMTP_PORT,
        username=cfg.EMAIL_SMTP_USERNAME,
        password=cfg.EMAIL_SMTP_PASSWORD,
        from_address=cfg.EMAIL_FROM_ADDRESS,
        from_name=cfg.EMAIL_FROM_NAME,
    )


def _print_smtp_config() -> None:
    print("SMTP:")
    print(f"  host:     {cfg.EMAIL_SMTP_HOST}:{cfg.EMAIL_SMTP_PORT}")
    print(f"  user:     {cfg.EMAIL_SMTP_USERNAME}")
    print(f"  password: {'*' * len(cfg.EMAIL_SMTP_PASSWORD)} ({len(cfg.EMAIL_SMTP_PASSWORD)} симв.)")
    print(f"  from:     {cfg.EMAIL_FROM_NAME} <{cfg.EMAIL_FROM_ADDRESS}>")


async def _send_with_result(coro_factory, verbose: bool = False) -> tuple[bool, str]:
    result: dict[str, Any] = {"ok": False, "response": ""}
    original = email_utils.email_service.send_html_email

    async def wrapped(*args, **kwargs):
        kwargs["return_smtp_response"] = True
        ok, response = await original(*args, **kwargs)
        result["ok"] = ok
        result["response"] = response
        return ok

    email_utils.email_service.send_html_email = wrapped
    try:
        await coro_factory()
    finally:
        email_utils.email_service.send_html_email = original

    if verbose and result["response"]:
        print(f"SMTP ответ: {result['response']}")

    return bool(result["ok"]), result["response"]


def _print_delivery_hint(recipient: str) -> None:
    print()
    print("Примечание: OK означает, что Yandex принял письмо в очередь,")
    print("но не гарантирует доставку во «Входящие».")
    print(f"- Проверьте «Спам» у {recipient}")
    print("- Проверьте info@tennis-play.com на письма от Mailer-Daemon (отбой)")
    print("- У домена tennis-play.com нет DMARC — Gmail может фильтровать жёстче")
    print("- В .env EMAIL_ADMIN=promosite1@ya.ru — бот шлёт туда, не на Gmail")


async def cmd_check_smtp(args: argparse.Namespace) -> int:
    _apply_smtp_overrides(args)
    recipient = args.to or cfg.EMAIL_ADMIN
    _print_smtp_config()
    print(f"  to:       {recipient}")
    print()

    ok, smtp_response = await email_utils.email_service.send_text_email(
        to=recipient,
        subject="TennisBot — проверка SMTP",
        text_body=(
            "Тестовое письмо.\n"
            "Если вы его получили, SMTP настроен корректно."
        ),
        return_smtp_response=True,
    )
    if smtp_response:
        print(f"SMTP ответ: {smtp_response}")
    if ok:
        print("OK: SMTP принял письмо в очередь")
        _print_delivery_hint(recipient)
        return 0
    print("FAIL: не удалось отправить письмо (см. ошибки выше)", file=sys.stderr)
    return 1


async def cmd_subscription(args: argparse.Namespace) -> int:
    _apply_smtp_overrides(args)
    recipient = args.to or cfg.EMAIL_ADMIN
    cfg.EMAIL_ADMIN = recipient
    profile = _build_profile(args)

    _print_smtp_config()
    print(f"  to:       {recipient}")
    print(f"  type:     subscription")
    print(f"  user_id:  {args.user_id}")
    print(f"  amount:   {args.amount} руб.")
    print()

    ok, smtp_response = await _send_with_result(
        lambda: email_utils.send_payment_notification_to_admin(
            user_id=args.user_id,
            profile=profile,
            payment_id=args.payment_id,
            user_email=args.user_email,
            payment_amount=args.amount,
        ),
        verbose=args.verbose,
    )
    if ok:
        print("OK: SMTP принял письмо в очередь")
        _print_delivery_hint(recipient)
        return 0
    print("FAIL: SMTP вернул ошибку", file=sys.stderr)
    return 1


async def cmd_tournament(args: argparse.Namespace) -> int:
    _apply_smtp_overrides(args)
    recipient = args.to or cfg.EMAIL_ADMIN
    cfg.EMAIL_ADMIN = recipient
    profile = _build_profile(args)

    _print_smtp_config()
    print(f"  to:       {recipient}")
    print(f"  type:     tournament")
    print(f"  user_id:  {args.user_id}")
    print(f"  amount:   {args.amount} руб.")
    print(f"  tour:     {args.tournament_name} ({args.tournament_id})")
    print()

    ok, smtp_response = await _send_with_result(
        lambda: email_utils.send_tournament_payment_notification_to_admin(
            user_id=args.user_id,
            profile=profile,
            payment_id=args.payment_id,
            user_email=args.user_email,
            payment_amount=args.amount,
            tournament_name=args.tournament_name,
            tournament_id=args.tournament_id,
        ),
        verbose=args.verbose,
    )
    if ok:
        print("OK: SMTP принял письмо в очередь")
        _print_delivery_hint(recipient)
        return 0
    print("FAIL: SMTP вернул ошибку", file=sys.stderr)
    return 1


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--to",
        help=f"Получатель (по умолчанию EMAIL_ADMIN={cfg.EMAIL_ADMIN})",
    )
    parser.add_argument("--smtp-host", help=f"SMTP host (по умолчанию {cfg.EMAIL_SMTP_HOST})")
    parser.add_argument(
        "--smtp-port",
        type=int,
        help=f"SMTP port (по умолчанию {cfg.EMAIL_SMTP_PORT})",
    )
    parser.add_argument(
        "--smtp-user",
        help=f"SMTP login (по умолчанию {cfg.EMAIL_SMTP_USERNAME})",
    )
    parser.add_argument(
        "--smtp-password",
        help="SMTP password (по умолчанию из EMAIL_SMTP_PASSWORD в .env)",
    )
    parser.add_argument(
        "--from-address",
        help=f"From address (по умолчанию {cfg.EMAIL_FROM_ADDRESS})",
    )
    parser.add_argument(
        "--from-name",
        help=f"From name (по умолчанию {cfg.EMAIL_FROM_NAME})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Показать ответ SMTP-сервера",
    )


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--user-id", type=int, default=123456789, help="Telegram user id")
    parser.add_argument("--first-name", default="Иван", help="Имя в профиле")
    parser.add_argument("--last-name", default="Петров", help="Фамилия в профиле")
    parser.add_argument("--phone", default="+375291234567", help="Телефон")
    parser.add_argument("--username", default="test_user", help="Telegram @username без @")
    parser.add_argument("--sport", default="🎾Большой теннис", help="Вид спорта")
    parser.add_argument("--city", default="Минск", help="Город")
    parser.add_argument("--country", default="🇧🇾 Беларусь", help="Страна")
    parser.add_argument("--user-email", default="payer@example.com", help="Email плательщика")
    parser.add_argument("--payment-id", default="TEST-PAYMENT-001", help="ID платежа")
    parser.add_argument("--amount", type=int, default=300, help="Сумма в рублях")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Тест отправки писем TennisBot (шаблоны как в проде)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-smtp", help="Отправить простое тестовое письмо")
    _add_common_args(check)

    sub_parser = sub.add_parser("subscription", help="Письмо об оплате подписки")
    _add_common_args(sub_parser)
    _add_profile_args(sub_parser)

    tour = sub.add_parser("tournament", help="Письмо об оплате турнира")
    _add_common_args(tour)
    _add_profile_args(tour)
    tour.add_argument("--tournament-name", default="Тестовый турнир", help="Название турнира")
    tour.add_argument("--tournament-id", default="tour-test-001", help="ID турнира")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "check-smtp": cmd_check_smtp,
        "subscription": cmd_subscription,
        "tournament": cmd_tournament,
    }
    return asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    raise SystemExit(main())
