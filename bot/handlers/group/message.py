import asyncio
from typing import Optional

from aiogram import Router, F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import MagicData
from aiogram.types import Message

from bot.manager import Manager
from bot.types.album import Album
from bot.utils.redis import RedisStorage

router = Router()
router.message.filter(
    MagicData(F.event_chat.id == F.config.bot.GROUP_ID),  # type: ignore
    F.chat.type.in_(["group", "supergroup"]),
)


@router.edited_message(F.chat.type.in_(["group", "supergroup"]))
async def handle_group_edited_message(message: Message, redis: RedisStorage) -> None:
    """
    Handle edited messages in group chat and sync them to private chats.

    :param message: The edited message.
    :param redis: RedisStorage object.
    :return: None
    """
    from aiogram.exceptions import TelegramAPIError

    # Get target message location in the user's private chat
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
                entities=message.entities
            )
        elif message.caption:
            await message.bot.edit_message_caption(
                chat_id=target_chat_id,
                message_id=target_msg_id,
                caption=message.caption,
                caption_entities=message.caption_entities
            )
    except TelegramAPIError:
        # Ignore errors (message too old, deleted, or media type changed)
        pass


@router.message(F.media_group_id, F.from_user[F.is_bot.is_(False)])
@router.message(F.media_group_id.is_(None), F.from_user[F.is_bot.is_(False)])
async def handler(message: Message, manager: Manager, redis: RedisStorage, album: Optional[Album] = None) -> None:
    """
    Handles admin replies and sends them to the respective user.
    Only processes messages that are replies to forwarded user messages.
    If silent mode is enabled for the user, the messages are ignored.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :param album: Album object or None.
    :return: None
    """
    # Only process replies to messages
    if not message.reply_to_message:
        return

    # Get user ID from message mapping
    user_id = await redis.get_user_id_by_message(message.reply_to_message.message_id)
    if not user_id:
        return  # No mapping found, ignore

    # Get user data
    user_data = await redis.get_user(user_id)
    if not user_data:
        return  # User not found

    if user_data.message_silent_mode:
        # If silent mode is enabled, ignore all messages.
        return

    text = manager.text_message.get("message_sent_to_user")

    try:
        if not album:
            sent_msg = await message.copy_to(chat_id=user_data.id)
            # Save bidirectional mapping for admin replies
            await redis.set_bidirectional_mapping(
                source_chat_id=message.chat.id,
                source_msg_id=message.message_id,
                target_chat_id=user_data.id,
                target_msg_id=sent_msg.message_id
            )
            await redis.set_bidirectional_mapping(
                source_chat_id=user_data.id,
                source_msg_id=sent_msg.message_id,
                target_chat_id=message.chat.id,
                target_msg_id=message.message_id
            )
        else:
            sent_messages = await album.copy_to(chat_id=user_data.id)
            # Save bidirectional mapping for each message in album
            for idx, sent_msg in enumerate(sent_messages):
                await redis.set_bidirectional_mapping(
                    source_chat_id=message.chat.id,
                    source_msg_id=album.messages[idx].message_id,
                    target_chat_id=user_data.id,
                    target_msg_id=sent_msg.message_id
                )
                await redis.set_bidirectional_mapping(
                    source_chat_id=user_data.id,
                    source_msg_id=sent_msg.message_id,
                    target_chat_id=message.chat.id,
                    target_msg_id=album.messages[idx].message_id
                )

    except TelegramAPIError as ex:
        if "blocked" in ex.message:
            text = manager.text_message.get("blocked_by_user")

    except (Exception,):
        text = manager.text_message.get("message_not_sent")

    # Reply with the status message
    msg = await message.reply(text)
    # Wait for 5 seconds before deleting the reply
    await asyncio.sleep(5)
    # Delete the status message
    await msg.delete()
