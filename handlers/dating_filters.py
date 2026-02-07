from typing import Union
from aiogram import types
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from models.states import SearchPartnerStates
from utils.translations import get_user_language_async, t

async def show_age_range_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
        user_id = str(message.from_user.id)
    else:
        message_obj = message
        user_id = str(message.chat.id)
    
    language = await get_user_language_async(user_id)
    builder = InlineKeyboardBuilder()
    
    age_ranges = [
        ("18-25", t("dating_filters.age_18_25", language)),
        ("26-35", t("dating_filters.age_26_35", language)), 
        ("36-45", t("dating_filters.age_36_45", language)),
        ("46-55", t("dating_filters.age_46_55", language)),
        ("56+", t("dating_filters.age_56_plus", language)),
        ("any", t("dating_filters.age_any", language))
    ]
    
    for value, label in age_ranges:
        builder.add(InlineKeyboardButton(
            text=label,
            callback_data=f"partner_age_{value}"
        ))
    
    builder.adjust(2, 2)
    
    builder.row(InlineKeyboardButton(
        text=t("dating_filters.back_to_gender", language),
        callback_data="partner_back_to_gender"
    ))
    
    await message_obj.edit_text(
        t("dating_filters.select_age_range", language),
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_AGE_RANGE)

async def show_dating_goal_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    """Показывает выбор цели знакомства"""
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
        user_id = str(message.from_user.id)
    else:
        message_obj = message
        user_id = str(message.chat.id)
    
    language = await get_user_language_async(user_id)
    builder = InlineKeyboardBuilder()
    
    # Цели знакомств
    goals = [
        ("any", t("dating_filters.goal_any", language)),
        ("relationship", t("dating_filters.goal_relationship", language)),
        ("communication", t("dating_filters.goal_communication", language)),
        ("friendship", t("dating_filters.goal_friendship", language)),
        ("never_know", t("dating_filters.goal_never_know", language))
    ]
    
    for value, label in goals:
        builder.add(InlineKeyboardButton(
            text=label,
            callback_data=f"partner_dating_goal_{value}"
        ))
    
    builder.adjust(1, 2)
    
    builder.row(InlineKeyboardButton(
        text=t("dating_filters.back_to_age", language),
        callback_data="partner_back_to_age"
    ))
    
    await message_obj.edit_text(
        t("dating_filters.select_dating_goal", language),
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_DATING_GOAL)

async def show_distance_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    """Показывает выбор расстояния для знакомств"""
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
        user_id = str(message.from_user.id)
    else:
        message_obj = message
        user_id = str(message.chat.id)
    
    language = await get_user_language_async(user_id)
    builder = InlineKeyboardBuilder()
    
    # Диапазоны расстояния
    distances = [
        ("5", t("dating_filters.distance_5", language)),
        ("10", t("dating_filters.distance_10", language)),
        ("20", t("dating_filters.distance_20", language)),
        ("50", t("dating_filters.distance_50", language)),
        ("100", t("dating_filters.distance_100", language)),
        ("any", t("dating_filters.distance_any", language))
    ]
    
    for value, label in distances:
        builder.add(InlineKeyboardButton(
            text=label,
            callback_data=f"partner_distance_{value}"
        ))
    
    builder.adjust(2, 2)
    
    builder.row(InlineKeyboardButton(
        text=t("dating_filters.back_to_goal", language),
        callback_data="partner_back_to_dating_goal"
    ))
    
    await message_obj.edit_text(
        t("dating_filters.select_distance", language),
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_DISTANCE)
