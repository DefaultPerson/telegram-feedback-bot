import asyncio

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.utils.markdown import hcode, hbold

from bot.manager import Manager
from bot.types.album import Album
from bot.utils.redis import RedisStorage
from bot.utils.redis.models import UserData

router = Router()
router.message.filter(F.chat.type == "private", StateFilter(None))


@router.edited_message(F.chat.type == "private")
async def handle_edited_message(message: Message, redis: RedisStorage) -> None:
    """
    Handle edited messages in private chats and sync them to the group.

    :param message: The edited message.
    :param redis: RedisStorage object.
    :return: None
    """
    from aiogram.exceptions import TelegramAPIError

    # Get target message location in the group
    target = await redis.get_target_message(message.chat.id, message.message_id)
    if not target:
        return  # No mapping found, ignore

    target_chat_id, target_msg_id = target

    try:
        # Try to edit the message in the target chat
        if message.text:
            await message.bot.edit_message_text(
                chat_id=target_chat_id,
                message_id=target_msg_id,
                text=message.text,
                entities=message.entities,
            )
        elif message.caption:
            await message.bot.edit_message_caption(
                chat_id=target_chat_id,
                message_id=target_msg_id,
                caption=message.caption,
                caption_entities=message.caption_entities,
            )
    except TelegramAPIError:
        # Ignore errors (message too old, deleted, or media type changed)
        pass


@router.message(F.media_group_id)
@router.message(F.media_group_id.is_(None))
async def handle_incoming_message(
    message: Message,
    manager: Manager,
    redis: RedisStorage,
    user_data: UserData,
    album: Album | None = None,
) -> None:
    """
    Handles incoming messages and forwards them to the group chat.
    If the user is banned, the messages are ignored.

    :param message: The incoming message.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :param user_data: UserData object.
    :param album: Album object or None.
    :return: None
    """
    # Check if the user is banned
    if user_data.is_banned:
        return

    # Generate user profile URL
    url = (
        f"https://t.me/{user_data.username[1:]}"
        if user_data.username and user_data.username != "-"
        else f"tg://user?id={user_data.id}"
    )

    # Send user context message to group
    context_text = (
        f"📩 {hbold('Новое сообщение от пользователя:')}\n\n"
        f'👤 {hbold("Имя:")} <a href="{url}">{user_data.full_name}</a>\n'
        f"🆔 {hbold('ID:')} {hcode(user_data.id)}\n"
        f"📱 {hbold('Username:')} {user_data.username if user_data.username != '-' else 'Не указан'}"
    )

    context_msg = await message.bot.send_message(
        chat_id=manager.config.bot.GROUP_ID,
        text=context_text,
        disable_web_page_preview=True,
    )

    # Copy message(s) to group and save bidirectional mapping
    if not album:
        sent_message = await message.copy_to(
            chat_id=manager.config.bot.GROUP_ID,
        )
        await redis.set_message_mapping(sent_message.message_id, user_data.id)
        # Save bidirectional mapping for edit synchronization
        await redis.set_bidirectional_mapping(
            source_chat_id=message.chat.id,
            source_msg_id=message.message_id,
            target_chat_id=manager.config.bot.GROUP_ID,
            target_msg_id=sent_message.message_id,
        )
        await redis.set_bidirectional_mapping(
            source_chat_id=manager.config.bot.GROUP_ID,
            source_msg_id=sent_message.message_id,
            target_chat_id=message.chat.id,
            target_msg_id=message.message_id,
        )
    else:
        messages = await album.copy_to(
            chat_id=manager.config.bot.GROUP_ID,
        )
        for idx, msg in enumerate(messages):
            await redis.set_message_mapping(msg.message_id, user_data.id)
            # Save bidirectional mapping for each message in album
            await redis.set_bidirectional_mapping(
                source_chat_id=message.chat.id,
                source_msg_id=album.messages[idx].message_id,
                target_chat_id=manager.config.bot.GROUP_ID,
                target_msg_id=msg.message_id,
            )
            await redis.set_bidirectional_mapping(
                source_chat_id=manager.config.bot.GROUP_ID,
                source_msg_id=msg.message_id,
                target_chat_id=message.chat.id,
                target_msg_id=album.messages[idx].message_id,
            )

    # Also save mapping for context message
    await redis.set_message_mapping(context_msg.message_id, user_data.id)

    # Send a confirmation message to the user
    text = manager.text_message.get("message_sent")
    msg = await message.reply(text)
    # Wait for 5 seconds before deleting the reply
    await asyncio.sleep(5)
    await msg.delete()
