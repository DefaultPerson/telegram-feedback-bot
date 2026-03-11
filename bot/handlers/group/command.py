from aiogram import Router, F
from aiogram.filters import Command, MagicData
from aiogram.types import Message
from aiogram.utils.markdown import hcode, hbold

from bot.manager import Manager
from bot.utils.redis import RedisStorage

router_id = Router()
router_id.message.filter(
    F.chat.type.in_(["group", "supergroup"]),
)


@router_id.message(Command("id"))
async def id_handler(message: Message) -> None:
    """
    Sends chat ID in response to the /id command.

    :param message: Message object.
    :return: None
    """
    await message.reply(hcode(message.chat.id))


router = Router()
router.message.filter(
    F.chat.type.in_(["group", "supergroup"]),
    MagicData(F.event_chat.id == F.config.bot.GROUP_ID),  # type: ignore
)


@router.message(Command("silent"))
async def silent_handler(
    message: Message, manager: Manager, redis: RedisStorage
) -> None:
    """
    Toggles silent mode for a user in the group.
    Works only as a reply to a user's message.
    If silent mode is disabled, it will be enabled, and vice versa.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :return: None
    """
    # Check if command is a reply
    if not message.reply_to_message:
        await message.reply(
            "⚠️ Эта команда работает только в ответ на сообщение пользователя"
        )
        return

    # Get user ID from message mapping
    user_id = await redis.get_user_id_by_message(message.reply_to_message.message_id)
    if not user_id:
        await message.reply("⚠️ Не найден пользователь для этого сообщения")
        return

    # Get user data
    user_data = await redis.get_user(user_id)
    if not user_data:
        return

    # Toggle silent mode
    if user_data.message_silent_mode:
        user_data.message_silent_mode = False
        text = manager.text_message.get("silent_mode_disabled")
    else:
        user_data.message_silent_mode = True
        text = manager.text_message.get("silent_mode_enabled")

    await redis.update_user(user_data.id, user_data)
    await message.reply(text)


@router.message(Command("information"))
async def information_handler(
    message: Message, manager: Manager, redis: RedisStorage
) -> None:
    """
    Sends user information in response to the /information command.
    Works only as a reply to a user's message.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :return: None
    """
    # Check if command is a reply
    if not message.reply_to_message:
        await message.reply(
            "⚠️ Эта команда работает только в ответ на сообщение пользователя"
        )
        return

    # Get user ID from message mapping
    user_id = await redis.get_user_id_by_message(message.reply_to_message.message_id)
    if not user_id:
        await message.reply("⚠️ Не найден пользователь для этого сообщения")
        return

    # Get user data
    user_data = await redis.get_user(user_id)
    if not user_data:
        return

    format_data = user_data.to_dict()
    format_data["full_name"] = hbold(format_data["full_name"])
    text = manager.text_message.get("user_information")
    # Reply with formatted user information
    await message.reply(text.format_map(format_data))


@router.message(Command(commands=["ban"]))
async def ban_handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    """
    Toggles the ban status for a user in the group.
    Works only as a reply to a user's message.
    If the user is banned, they will be unbanned, and vice versa.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :return: None
    """
    # Check if command is a reply
    if not message.reply_to_message:
        await message.reply(
            "⚠️ Эта команда работает только в ответ на сообщение пользователя"
        )
        return

    # Get user ID from message mapping
    user_id = await redis.get_user_id_by_message(message.reply_to_message.message_id)
    if not user_id:
        await message.reply("⚠️ Не найден пользователь для этого сообщения")
        return

    # Get user data
    user_data = await redis.get_user(user_id)
    if not user_data:
        return

    # Toggle ban status
    if user_data.is_banned:
        user_data.is_banned = False
        text = manager.text_message.get("user_unblocked")
    else:
        user_data.is_banned = True
        text = manager.text_message.get("user_blocked")

    await redis.update_user(user_data.id, user_data)
    # Reply with the specified text
    await message.reply(text)
