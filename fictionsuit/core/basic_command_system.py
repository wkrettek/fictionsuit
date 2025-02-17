from typing import Sequence

from ..api_wrap.openai import ChatInstance

from .. import config
from ..commands.command_group import (
    CommandFailure,
    CommandGroup,
    CommandNotFound,
    CommandNotHandled,
    CommandReply,
    PartialReply,
    command_split,
)
from ..commands.scripting import Scripting
from ..utils import make_stats_str
from .system import System
from .user_message import UserMessage


class BasicCommandSystem(System):
    def __init__(
        self,
        command_groups: Sequence[CommandGroup],
        stats_ui: bool = True,
        respond_on_unrecognized: bool = False,
        enable_scripting: bool = False,
        prefix: str = config.COMMAND_PREFIX
    ):
        self.command_groups = command_groups
        self.stats_ui = stats_ui
        self.respond_on_unrecognized = respond_on_unrecognized
        self.prefix = prefix

        all_commands = [
            command for group in command_groups for command in group.get_all_commands()
        ]

        # TODO: this doesn't actually work; figure out why
        if len(all_commands) != len(set(all_commands)):
            # TODO: Print out more useful information, like where the name collision actually is.
            print(
                f'{"!"*20}\n\nWARNING: MULTIPLE COMMANDS WITH OVERLAPPING COMMAND NAMES\n\n{"!"*20}'
            )

        self.slow_commands = None

        if enable_scripting:
            self.command_groups += [Scripting(self, self.command_groups)]

        for group in self.command_groups:
            group.command_prefix = prefix
            group.inspect_other_groups(self.command_groups)

    async def enqueue_message(
        self, message: UserMessage, return_failures: bool = False
    ):
        content = message.content

        try:
            for group in self.command_groups:
                content = await group.intercept_content(content)
        except Exception as e:
            await message.reply(f"Error in content interception: {e}")
            content = message.content

        if not message.has_prefix(self.prefix):
            return  # Not handling non-prefixed messages, for now

        (cmd, args) = command_split(content, self.prefix)

        if cmd is None:
            return  # Nothing but a prefix. Nothing to do.

        if self.slow_commands is None:
            self.slow_commands = []
            for group in self.command_groups:
                self.slow_commands += group.get_slow_commands()

        cmd_is_slow = cmd in self.slow_commands

        if cmd_is_slow:
            await message.react("⏳")

        accumulator = None

        for group in self.command_groups:
            if accumulator is not None:
                result = await group.handle(message, cmd, args, accumulator)
            else:
                result = await group.handle(message, cmd, args)
            if type(result) is not CommandNotFound:
                if type(result) is CommandFailure:
                    if cmd_is_slow:
                        await message.undo_react("⏳")
                    await message.react("❌")
                    await message.reply(f'Command "{cmd}" failed.\n{result}')
                    if return_failures:
                        return result
                if type(result) is CommandReply:
                    if cmd_is_slow:
                        await message.undo_react("⏳")
                    await message.reply(result)
                    return
                if type(result) is PartialReply:
                    accumulator = result
                    continue
                if type(result) is not CommandNotHandled:
                    if cmd_is_slow:
                        await message.undo_react("⏳")
                    await message.react("✅")
                    return

        if accumulator is not None:
            if cmd_is_slow:
                await message.undo_react("⏳")
            await message.reply(accumulator)
            return

        await message.undo_react("⏳")

        if self.respond_on_unrecognized:
            await self.direct_chat(message)

    async def direct_chat(self, message: UserMessage):
        if hasattr(message, "discord_message"):
            await message.discord_message.channel.typing()
        chat = ChatInstance()
        chat.system(config.SYSTEM_MSG)
        chat.user(message.content)
        content = chat.continue_()
        content = (
            make_stats_str(content, chat.history, "chat") if self.stats_ui else content
        )
        await message.undo_react("⏳")
        await message.reply(content)

    # Retrieve history of the chat and return list of UserMessages
    async def retrieve_history(channel_id):
        messages = []
