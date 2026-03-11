import json

from redis.asyncio import Redis

from .models import UserData


class RedisStorage:
    """Class for managing user data storage using Redis."""

    NAME = "users"

    def __init__(self, redis: Redis) -> None:
        """
        Initializes the RedisStorage instance.

        :param redis: The Redis instance to be used for data storage.
        """
        self.redis = redis

    async def _get(self, name: str, key: str | int) -> bytes | None:
        """
        Retrieves data from Redis.

        :param name: The name of the Redis hash.
        :param key: The key to be retrieved.
        :return: The retrieved data or None if not found.
        """
        async with self.redis.client() as client:
            return await client.hget(name, key)

    async def _set(self, name: str, key: str | int, value: any) -> None:
        """
        Sets data in Redis.

        :param name: The name of the Redis hash.
        :param key: The key to be set.
        :param value: The value to be set.
        """
        async with self.redis.client() as client:
            await client.hset(name, key, value)

    async def set_message_mapping(
        self, message_id: int, user_id: int, ttl: int = 2592000
    ) -> None:
        """
        Creates a mapping between group message ID and user ID.

        :param message_id: The ID of the message in the group chat.
        :param user_id: The ID of the user who sent the original message.
        :param ttl: Time to live in seconds (default: 30 days).
        """
        key = f"msg_map:{message_id}"
        async with self.redis.client() as client:
            await client.setex(key, ttl, str(user_id))

    async def get_user_id_by_message(self, message_id: int) -> int | None:
        """
        Retrieves user ID based on group message ID.

        :param message_id: The ID of the message in the group chat.
        :return: The user ID or None if not found.
        """
        key = f"msg_map:{message_id}"
        async with self.redis.client() as client:
            user_id = await client.get(key)
            return int(user_id) if user_id else None

    async def set_bidirectional_mapping(
        self,
        source_chat_id: int,
        source_msg_id: int,
        target_chat_id: int,
        target_msg_id: int,
        ttl: int = 2592000,
    ) -> None:
        """
        Creates bidirectional mapping between messages in different chats.

        :param source_chat_id: The chat ID where the original message is.
        :param source_msg_id: The message ID in the source chat.
        :param target_chat_id: The chat ID where the copied message is.
        :param target_msg_id: The message ID in the target chat.
        :param ttl: Time to live in seconds (default: 30 days).
        """
        key = f"bidir_map:{source_chat_id}:{source_msg_id}"
        value = f"{target_chat_id},{target_msg_id}"
        async with self.redis.client() as client:
            await client.setex(key, ttl, value)

    async def get_target_message(
        self, chat_id: int, message_id: int
    ) -> tuple[int, int] | None:
        """
        Retrieves target message location based on source message.

        :param chat_id: The chat ID of the source message.
        :param message_id: The message ID of the source message.
        :return: Tuple of (target_chat_id, target_msg_id) or None if not found.
        """
        key = f"bidir_map:{chat_id}:{message_id}"
        async with self.redis.client() as client:
            value = await client.get(key)
            if value:
                target_chat_id, target_msg_id = value.decode().split(",")
                return int(target_chat_id), int(target_msg_id)
            return None

    async def get_user(self, id_: int) -> UserData | None:
        """
        Retrieves user data based on user ID.

        :param id_: The ID of the user.
        :return: The user data or None if not found.
        """
        data = await self._get(self.NAME, id_)
        if data is not None:
            decoded_data = json.loads(data)
            return UserData(**decoded_data)
        return None

    async def update_user(self, id_: int, data: UserData) -> None:
        """
        Updates user data in Redis.

        :param id_: The ID of the user to be updated.
        :param data: The updated user data.
        """
        json_data = json.dumps(data.to_dict())
        await self._set(self.NAME, id_, json_data)

    async def get_all_users_ids(self) -> list[int]:
        """
        Retrieves all user IDs stored in the Redis hash.

        :return: A list of all user IDs.
        """
        async with self.redis.client() as client:
            user_ids = await client.hkeys(self.NAME)
            return [int(user_id) for user_id in user_ids]
