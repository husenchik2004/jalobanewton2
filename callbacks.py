# handlers/callbacks.py
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from google_sheets import GoogleSheetsClient
from aiogram.fsm.context import FSMContext
router = Router()

# -------------------------
# 📞 Нажали "Перезвонили родителю"
# -------------------------
@router.callback_query(F.data.startswith("called:"))
async def mark_called(callback: types.CallbackQuery):
    cid = callback.data.split(":", 1)[1]
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    # простая защита от повторной обработки одного ID
    if not hasattr(callback.bot, "_called_ids"):
        callback.bot._called_ids = set()
    if cid in callback.bot._called_ids:
        try:
            await callback.answer("Уже обработано ✅", show_alert=False)
        except:
            pass
        return
    callback.bot._called_ids.add(cid)

    # Попытка обновить Google Sheets (не падаем, если ошибка)
    try:
        gs = GoogleSheetsClient(callback.bot.config["SERVICE_ACCOUNT_FILE"], callback.bot.config["GOOGLE_SHEET_ID"])
        gs.update_by_id(cid, {"Статус": "Принята", "Время обзвона": now})
    except Exception as e:
        # информируем пользователя, но не останавливаем дальнейшие действия
        try:
            await callback.answer("⚠️ Не удалось обновить таблицу", show_alert=True)
        except:
            pass
        # можно уведомить лидеров, если настроено
        if callback.bot.config.get("GROUP_LEADERS_ID"):
            try:
                await callback.bot.send_message(callback.bot.config["GROUP_LEADERS_ID"], f"Error updating sheet for {cid}: {e}")
            except:
                pass

    # Попытка отредактировать исходное сообщение (которое в группе жалоб)
    try:
        original = callback.message.caption or callback.message.text or ""
        new_text = original + f"\n☎️ Перезвонили в {now}"
        # пробуем edit_caption, если не работает — edit_text
        try:
            await callback.message.edit_caption(new_text, parse_mode="HTML")
        except:
            await callback.message.edit_text(new_text, parse_mode="HTML")
    except Exception:
        # игнорируем ошибки редактирования
        pass

    # Пересылаем текст в группу РЕШЕНИЯ (без inline-кнопки)
    group_solutions = callback.bot.config.get("GROUP_SOLUTIONS_ID")
    try:
        forward_text = f"📤 Жалоба ID {cid} передана в «РЕШЕНИЯ».\n\n{callback.message.caption or callback.message.text or ''}\n\n🕒 {now}"
        if group_solutions:
            # отправляем без кнопок (по твоему запросу)
            await callback.bot.send_message(group_solutions, forward_text, parse_mode="HTML")
    except Exception:
        # если не получилось — уведомим лидеров (опционально)
        if callback.bot.config.get("GROUP_LEADERS_ID"):
            try:
                await callback.bot.send_message(callback.bot.config["GROUP_LEADERS_ID"], f"Не удалось переслать жалобу {cid} в РЕШЕНИЯ.")
            except:
                pass

    try:
        await callback.answer("✅ Жалоба передана в «РЕШЕНИЯ».")
    except:
        pass


