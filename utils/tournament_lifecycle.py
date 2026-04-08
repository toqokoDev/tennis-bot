"""
Сбор взноса при полном составе (24ч), снятие неоплативших, напоминания по круговой системе.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from aiogram import Bot

from config.config import BOT_USERNAME, TOURNAMENT_ENTRY_FEE
from services.storage import storage

logger = logging.getLogger(__name__)


def tournament_entry_fee(td: dict) -> int:
    return int(td.get("entry_fee", TOURNAMENT_ENTRY_FEE) or TOURNAMENT_ENTRY_FEE)


def is_roster_full(td: dict) -> bool:
    max_p = int(td.get("participants_count", 0) or 0)
    cur = len(td.get("participants", {}) or {})
    return max_p > 0 and cur >= max_p


def admin_sort_tournament_items(items: List[Tuple[str, dict]]) -> List[Tuple[str, dict]]:
    """Собранные по слотам (N>=max) и активные — выше в списке."""

    def key(it: Tuple[str, dict]):
        tid, td = it
        max_p = int(td.get("participants_count", 0) or 0)
        cur = len(td.get("participants", {}) or {})
        full = max_p > 0 and cur >= max_p
        st = td.get("status", "active")
        prio = 0 if full and st in ("active", "started") else 1
        return (prio, -cur, str(tid))

    return sorted(items, key=key)


def participants_count_label(td: dict) -> str:
    cur = len(td.get("participants", {}) or {})
    max_p = td.get("participants_count")
    if max_p is None or max_p == "":
        return str(cur)
    return f"{cur}/{max_p}"


def pay_tournament_deeplink(tournament_id: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=pay_tournament_{tournament_id}"


def view_tournament_deeplink(tournament_id: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=view_tournament_{tournament_id}"


async def maybe_begin_payment_collection_batch(bot: Bot | None, tournaments: Dict[str, dict]) -> None:
    """Один проход по уже загруженному словарю турниров (без лишних чтений с диска)."""
    if not bot:
        return
    changed = False
    for tid in list(tournaments.keys()):
        td = tournaments.get(tid)
        if not td or td.get("status") != "active":
            continue
        if tournament_entry_fee(td) <= 0:
            continue
        if not is_roster_full(td):
            continue
        participants = td.get("participants", {}) or {}
        payments = td.get("payments", {}) or {}
        unpaid = [uid for uid in participants if payments.get(str(uid), {}).get("status") != "succeeded"]
        if not unpaid:
            td.pop("payment_window", None)
            tournaments[tid] = td
            changed = True
            continue
        pw = td.get("payment_window") or {}
        if pw.get("active"):
            continue
        deadline = datetime.now() + timedelta(hours=24)
        td["payment_window"] = {
            "active": True,
            "deadline_at": deadline.isoformat(),
            "created_at": datetime.now().isoformat(),
        }
        tournaments[tid] = td
        changed = True
        await _notify_payment_window_opened(bot, tid, td, deadline)
    if changed:
        await storage.save_tournaments(tournaments)


async def maybe_clear_payment_window_if_resolved(tournament_id: str) -> None:
    """После успешной оплаты: закрыть окно 24ч, если все взносы оплачены."""
    tournaments = await storage.load_tournaments()
    td = tournaments.get(tournament_id)
    if not td:
        return
    participants = td.get("participants", {}) or {}
    payments = td.get("payments", {}) or {}
    fee = tournament_entry_fee(td)
    if fee <= 0:
        td.pop("payment_window", None)
        tournaments[tournament_id] = td
        await storage.save_tournaments(tournaments)
        return
    if not participants:
        return
    if all(payments.get(str(u), {}).get("status") == "succeeded" for u in participants):
        td.pop("payment_window", None)
        tournaments[tournament_id] = td
        await storage.save_tournaments(tournaments)


async def maybe_begin_payment_collection(bot: Bot | None, tournament_id: str) -> None:
    """Когда ростер полон и есть взнос — открыть 24-часовое окно оплаты и уведомить всех."""
    if not bot:
        return
    tournaments = await storage.load_tournaments()
    td = tournaments.get(tournament_id)
    if not td or td.get("status") != "active":
        return
    if tournament_entry_fee(td) <= 0:
        return
    if not is_roster_full(td):
        return
    participants = td.get("participants", {}) or {}
    payments = td.get("payments", {}) or {}
    unpaid = [uid for uid in participants if payments.get(str(uid), {}).get("status") != "succeeded"]
    if not unpaid:
        td.pop("payment_window", None)
        tournaments[tournament_id] = td
        await storage.save_tournaments(tournaments)
        return
    pw = td.get("payment_window") or {}
    if pw.get("active"):
        return
    deadline = datetime.now() + timedelta(hours=24)
    td["payment_window"] = {
        "active": True,
        "deadline_at": deadline.isoformat(),
        "created_at": datetime.now().isoformat(),
    }
    tournaments[tournament_id] = td
    await storage.save_tournaments(tournaments)
    await _notify_payment_window_opened(bot, tournament_id, td, deadline)


async def _notify_payment_window_opened(bot: Bot, tournament_id: str, td: dict, deadline: datetime) -> None:
    name = td.get("name", "Турнир")
    view = view_tournament_deeplink(tournament_id)
    pay = pay_tournament_deeplink(tournament_id)
    fee = tournament_entry_fee(td)
    deadline_str = deadline.strftime("%d.%m.%Y %H:%M")
    text = (
        "Здравствуйте!\n\n"
        f"Турнир «{name}», на который вы заявились, <b>собрался</b>.\n"
        f"Карточка турнира: <a href=\"{view}\">открыть в боте</a>\n\n"
        f"Для участия необходимо оплатить взнос за турнир ({fee} ₽): "
        f"<a href=\"{pay}\">перейти к оплате</a>\n\n"
        f"На оплату даётся <b>24 часа</b> (до {deadline_str}).\n\n"
        "Если не успеете оплатить в срок, заявка может быть снята с турнира, "
        "и тогда нужно будет записаться заново.\n\n"
        "Если за сутки оплатят не все, с турнира снимается самый ранний по времени заявки "
        "участник среди тех, кто <b>не оплатил</b>; остальные остаются. Когда снова наберётся "
        "полный состав, всем участникам снова будет отправлен запрос на оплату."
    )
    for uid in td.get("participants", {}) or {}:
        try:
            await bot.send_message(int(uid), text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logger.warning("payment window notify failed uid=%s: %s", uid, e)


async def process_payment_windows(bot: Bot | None) -> None:
    """По истечении 24ч снимает одного неоплатившего (самый ранний added_at среди неоплативших)."""
    if not bot:
        return
    tournaments = await storage.load_tournaments()
    changed = False
    now = datetime.now()
    for tid in list(tournaments.keys()):
        td = tournaments.get(tid)
        if not td:
            continue
        pw = td.get("payment_window") or {}
        if not pw.get("active"):
            continue
        if td.get("status") != "active":
            td.pop("payment_window", None)
            tournaments[tid] = td
            changed = True
            continue
        try:
            deadline = datetime.fromisoformat(pw["deadline_at"])
        except Exception:
            td.pop("payment_window", None)
            tournaments[tid] = td
            changed = True
            continue
        participants = td.get("participants", {}) or {}
        payments = td.get("payments", {}) or {}
        all_paid = all(
            payments.get(str(u), {}).get("status") == "succeeded" for u in participants
        )
        if now < deadline:
            if all_paid:
                td.pop("payment_window", None)
                tournaments[tid] = td
                changed = True
            continue
        if tournament_entry_fee(td) <= 0 or all_paid:
            td.pop("payment_window", None)
            tournaments[tid] = td
            changed = True
            continue
        unpaid = [u for u in participants if payments.get(str(u), {}).get("status") != "succeeded"]
        if not unpaid:
            td.pop("payment_window", None)
            tournaments[tid] = td
            changed = True
            continue

        def added_at_key(uid: str) -> str:
            return participants[uid].get("added_at") or "9999-12-31"

        victim = min(unpaid, key=added_at_key)
        del participants[victim]
        payments.pop(str(victim), None)
        td["participants"] = participants
        td["payments"] = payments
        td.pop("payment_window", None)
        tournaments[tid] = td
        changed = True
        tname = td.get("name", "Турнир")
        try:
            await bot.send_message(
                int(victim),
                f"Вы сняты с турнира «{tname}»: не оплачен взнос в течение 24 часов "
                f"(среди не оплативших снимается самый ранний по времени заявки участник). "
                f"Когда освободится место, вы сможете заявиться снова.",
            )
        except Exception as e:
            logger.warning("kick message failed uid=%s: %s", victim, e)
    if changed:
        await storage.save_tournaments(tournaments)


def _days_since_started(started_at: str | None) -> int:
    if not started_at:
        return 0
    try:
        s = started_at.replace("Z", "+00:00")
        started = datetime.fromisoformat(s)
        if started.tzinfo is not None:
            started = started.astimezone().replace(tzinfo=None)
    except Exception:
        return 0
    return max(0, (datetime.now() - started).days)


def _pending_user_matches(matches: List[dict], uid: str) -> List[dict]:
    uid = str(uid)
    out: List[dict] = []
    for m in matches:
        if m.get("status") != "pending" or m.get("is_bye"):
            continue
        if not m.get("player1_id") or not m.get("player2_id"):
            continue
        if str(m.get("player1_id")) == uid or str(m.get("player2_id")) == uid:
            out.append(m)
    out.sort(key=lambda x: int(x.get("match_number", 0)))
    return out


def _opponent_index_for_match(all_matches: List[dict], user_id: str, match: dict) -> int:
    um = _pending_user_matches(all_matches, user_id)
    try:
        return um.index(match) + 1
    except ValueError:
        return 1


def _staggered_reminder_fire(opp_idx: int, d: int) -> bool:
    if opp_idx <= 1:
        return d >= 5 and (d - 5) % 5 == 0
    if opp_idx == 2:
        return d >= 14 and (d - 14) % 5 == 0
    return d >= 21 and (d - 21) % 5 == 0


async def process_round_robin_reminders(bot: Bot | None) -> None:
    """Круговая: уведомление после 8 дней без игры; затем циклы каждые 5 дней с разными стартами по номеру соперника."""
    if not bot:
        return
    tournaments = await storage.load_tournaments()
    users = await storage.load_users()
    any_changed = False
    for tid, td in tournaments.items():
        if td.get("type") != "Круговая" or td.get("status") != "started":
            continue
        started_at = td.get("started_at")
        if not started_at:
            continue
        d = _days_since_started(started_at)
        tour_name = td.get("name", "Турнир")
        view = view_tournament_deeplink(tid)
        matches: List[dict] = td.get("matches", []) or []
        t_changed = False
        for m in matches:
            if m.get("status") != "pending" or m.get("is_bye"):
                continue
            p1, p2 = m.get("player1_id"), m.get("player2_id")
            if not p1 or not p2:
                continue
            eight: Dict[str, Any] = m.setdefault("rr_eight_day_notice", {})
            rs: Dict[str, Any] = m.setdefault("rr_reminder_state", {})
            pairs = [
                (str(p1), str(p2), m.get("player2_name", "Соперник")),
                (str(p2), str(p1), m.get("player1_name", "Соперник")),
            ]
            for uid, opp_id, opp_name in pairs:
                udata = users.get(str(uid), {})
                pname = (udata.get("first_name", "") + " " + udata.get("last_name", "")).strip() or "Участник"
                opp_user = users.get(str(opp_id), {})
                opp_phone = opp_user.get("phone") or "не указан"
                opp_username = opp_user.get("username") or ""
                tg_line = f"@{opp_username}" if opp_username else "не указан"

                if d >= 8 and not eight.get(uid):
                    msg = (
                        f"Здравствуйте, {pname}!\n\n"
                        f"В турнире «{tour_name}» (<a href=\"{view}\">карточка</a>) "
                        f"у вас завершились 8 дней на игру с соперником <b>{opp_name}</b>.\n\n"
                        "Если вы уже сыграли, укажите счёт в боте: <b>Меню → Турниры → "
                        "Внести счёт по турниру</b>.\n\n"
                        "Если ещё не сыграли — вам даётся ещё <b>3 дня</b> на завершение игры.\n\n"
                        "Если не сможете сыграть и в ближайшие 3 дня, напишите на почту "
                        "<a href=\"mailto:info@tennis-play.com\">info@tennis-play.com</a> причину "
                        "и дату, на которую договорились сыграть.\n\n"
                        f"Контакты соперника: <b>{opp_name}</b>\n"
                        f"Тел.: {opp_phone}\n"
                        f"Ник в Telegram: {tg_line}"
                    )
                    try:
                        await bot.send_message(int(uid), msg, parse_mode="HTML", disable_web_page_preview=True)
                        eight[uid] = True
                        t_changed = True
                    except Exception as e:
                        logger.warning("8d notice failed uid=%s: %s", uid, e)

                opp_idx = _opponent_index_for_match(matches, uid, m)
                if not _staggered_reminder_fire(opp_idx, d):
                    continue
                last = int(rs.get(uid, -1))
                if last >= d:
                    continue
                short = (
                    f"Напоминание по турниру «{tour_name}».\n"
                    f"Сыграйте с <b>{opp_name}</b> и внесите счёт в боте "
                    f"(Меню → Турниры → Внести счёт по турниру).\n"
                    f"Соперник: тел. {opp_phone}, Telegram: {tg_line}"
                )
                try:
                    await bot.send_message(int(uid), short, parse_mode="HTML", disable_web_page_preview=True)
                    rs[uid] = d
                    t_changed = True
                except Exception as e:
                    logger.warning("rr reminder failed uid=%s: %s", uid, e)
        if t_changed:
            tournaments[tid] = td
            any_changed = True
    if any_changed:
        await storage.save_tournaments(tournaments)


async def run_tournament_scheduled_jobs(bot: Bot) -> None:
    """Вызывать из фонового цикла (оплата + напоминания)."""
    try:
        all_t = await storage.load_tournaments()
        await maybe_begin_payment_collection_batch(bot, all_t)
    except Exception as e:
        logger.error("sweep maybe_begin_payment_collection: %s", e, exc_info=True)
    try:
        await process_payment_windows(bot)
    except Exception as e:
        logger.error("process_payment_windows: %s", e, exc_info=True)
    try:
        await process_round_robin_reminders(bot)
    except Exception as e:
        logger.error("process_round_robin_reminders: %s", e, exc_info=True)
