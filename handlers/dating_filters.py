from typing import Union
from aiogram import types
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from models.states import SearchPartnerStates

async def show_age_range_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    """Показывает выбор возрастного диапазона для знакомств"""
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    builder = InlineKeyboardBuilder()
    
    # Возрастные диапазоны
    age_ranges = [
        ("18-25", "18-25 лет"),
        ("26-35", "26-35 лет"), 
        ("36-45", "36-45 лет"),
        ("46-55", "46-55 лет"),
        ("56+", "56+ лет"),
        ("any", "Любой возраст")
    ]
    
    for value, label in age_ranges:
        builder.add(InlineKeyboardButton(
            text=label,
            callback_data=f"partner_age_{value}"
        ))
    
    builder.adjust(2, 2)
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к полу",
        callback_data="partner_back_to_gender"
    ))
    
    await message_obj.edit_text(
        "🎂 Выберите возрастной диапазон партнера:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_AGE_RANGE)

async def show_dating_goal_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    """Показывает выбор цели знакомства"""
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    builder = InlineKeyboardBuilder()
    
    # Цели знакомств
    goals = [
        ("any", "Любая цель"),
        ("relationship", "Отношения"),
        ("communication", "Общение"),
        ("friendship", "Дружба"),
        ("never_know", "Никогда не знаешь, что будет")
    ]
    
    for value, label in goals:
        builder.add(InlineKeyboardButton(
            text=label,
            callback_data=f"partner_dating_goal_{value}"
        ))
    
    builder.adjust(1, 2)
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к возрасту",
        callback_data="partner_back_to_age"
    ))
    
    await message_obj.edit_text(
        "💕 Выберите цель знакомства партнера:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_DATING_GOAL)

async def show_distance_selection(message: Union[types.Message, types.CallbackQuery], state: FSMContext):
    """Показывает выбор расстояния для знакомств"""
    if isinstance(message, types.CallbackQuery):
        message_obj = message.message
    else:
        message_obj = message
    
    builder = InlineKeyboardBuilder()
    
    # Диапазоны расстояния
    distances = [
        ("5", "5 км"),
        ("10", "10 км"),
        ("20", "20 км"),
        ("50", "50 км"),
        ("100", "100 км"),
        ("any", "Любое расстояние")
    ]
    
    for value, label in distances:
        builder.add(InlineKeyboardButton(
            text=label,
            callback_data=f"partner_distance_{value}"
        ))
    
    builder.adjust(2, 2)
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к цели",
        callback_data="partner_back_to_dating_goal"
    ))
    
    await message_obj.edit_text(
        "📍 Выберите максимальное расстояние для поиска:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SearchPartnerStates.SEARCH_DISTANCE)
