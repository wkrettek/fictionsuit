from .. import config
from ..core.fictionscript.scope import Scope
from ..api_wrap.openai import ChatInstance
from .scripting import Scripting
from ..core.user_message import UserMessage
from .command_group import CommandFailure, CommandGroup, auto_reply, command_split, slow_command


class Chat(CommandGroup):
    def __init__(self):
        self._chat_cmds = _Chat(self)

    def inspect_other_groups(self, groups: list[CommandGroup]):
        self.scripting_group = None
        for group in groups:
            if type(group) is Scripting:
                self.scripting_group = group
        if self.scripting_group is None:
            self._scope = Scope()

    async def intercept_content(self, content: str) -> str:
        """Applies syntactic sugar, converting `<{role} @ {chat instance}> {message}` to `chat {role} {chat instance}: {message}`
        If the role is omitted, it will default to "user".
        
        TODO: also find a nicer syntax for `chat continue {name of chat}`. Maybe `<{name of chat}++>`?"""
        if not content.startswith(self.command_prefix):
            return content
        content = content[len(self.command_prefix):].strip()
        if not content.startswith('<'):
            return f'{self.command_prefix}{content}'
        split = [x.strip() for x in content[1:].split('>', maxsplit=1)]
        if len(split) < 2:
            return f'{self.command_prefix}{content}'
        role_and_chat = split[0]
        message = split[1]
        role_chat_split = [x.strip() for x in role_and_chat.split('@', maxsplit=1)]
        if len(role_chat_split) < 2:
            role = 'user'
            chat = role_chat_split[0]
        else:
            role = role_chat_split[0]
            chat = role_chat_split[1]
        return f'{self.command_prefix}chat {role} {chat}: {message}'

    def _get_scope(self) -> Scope:
        return self.scripting_group.vars if self.scripting_group is not None else self._scope

    @slow_command
    @auto_reply
    async def cmd_chat(self, message: UserMessage, args: str):
        """This one has subcommands. Not sure how to automate the help messages for that just yet..."""
        (inner_cmd, inner_args) = command_split(args, "")
        if inner_cmd is None:
            return
        return await self._chat_cmds.handle(message, inner_cmd, inner_args)
    
    
class _Chat(CommandGroup):
    def __init__(self, parent_group: Chat):
        self.parent = parent_group

    async def cmd_new(self, message: UserMessage, args: str) -> ChatInstance:
        """Create a new openai chat instance with default settings.
        Usage:
        `chat new` returns a ChatInstance
        `chat new {name of instance}` shorthand for `var {name of instance} = chat new`"""
        if args == '':
            return ChatInstance()
        else:
            scope = self.parent._get_scope()
            scope[args] = ChatInstance()
    
    async def cmd_temp(self, message: UserMessage, args: str):
        """Set a ChatInstance's temperature"""
        split = [x.strip() for x in args.split(maxsplit=1)]
        if len(split) == 1:
            return CommandFailure("Not enough arguments. TODO: better help message here")
        scope = self.parent._get_scope()
        if split[1] not in scope:
            return CommandFailure("No such ChatInstance in scope.")
        try:
            scope[split[1]].temperature = float(split[0])
        except ValueError:
            return CommandFailure("Chat temperature must be a float.")
    
    async def cmd_limit(self, message: UserMessage, args: str):
        """Set a ChatInstance's max_tokens"""
        split = [x.strip() for x in args.split(maxsplit=1)]
        if len(split) == 1:
            return CommandFailure("Not enough arguments. TODO: better help message here")
        scope = self.parent._get_scope()
        if split[1] not in scope:
            return CommandFailure("No such ChatInstance in scope.")
        try:
            scope[split[1]].max_tokens = int(split[0])
        except ValueError:
            return CommandFailure("Chat limit must be an int.")
    
    async def cmd_top_p(self, message: UserMessage, args: str):
        """Set a ChatInstance's top_p"""
        split = [x.strip() for x in args.split(maxsplit=1)]
        if len(split) == 1:
            return CommandFailure("Not enough arguments. TODO: better help message here")
        scope = self.parent._get_scope()
        if split[1] not in scope:
            return CommandFailure("No such ChatInstance in scope.")
        try:
            scope[split[1]].top_p = float(split[0])
        except ValueError:
            return CommandFailure("Chat top_p must be a float.")
        
    async def cmd_user(self, message: UserMessage, args: str):
        """Append a user message to the chat history."""
        split = [x.strip() for x in args.split(':', maxsplit=1)]
        if len(split) < 2:
            return CommandFailure("No message found -- did you forget the colon (:)?")
        if split[1] == '':
            return CommandFailure("Sorry, OpenAI's API doesn't like blank messages.")
        chat_name = split[0]
        content = split[1]
        scope = self.parent._get_scope()
        if chat_name not in scope:
            return CommandFailure("No such ChatInstance in scope.")
        return await scope[chat_name].user(content)
        
    async def cmd_assistant(self, message: UserMessage, args: str):
        """Append a assistant message to the chat history."""
        split = [x.strip() for x in args.split(':', maxsplit=1)]
        if len(split) < 2:
            return CommandFailure("No message found -- did you forget the colon (:)?")
        if split[1] == '':
            return CommandFailure("Sorry, OpenAI's API doesn't like blank messages.")
        chat_name = split[0]
        content = split[1]
        scope = self.parent._get_scope()
        if chat_name not in scope:
            return CommandFailure("No such ChatInstance in scope.")
        return await scope[chat_name].assistant(content)
        
    async def cmd_system(self, message: UserMessage, args: str):
        """Append a system message to the chat history."""
        split = [x.strip() for x in args.split(':', maxsplit=1)]
        if len(split) < 2:
            return CommandFailure("No message found -- did you forget the colon (:)?")
        if split[1] == '':
            return CommandFailure("Sorry, OpenAI's API doesn't like blank messages.")
        chat_name = split[0]
        content = split[1]
        scope = self.parent._get_scope()
        if chat_name not in scope:
            return CommandFailure("No such ChatInstance in scope.")
        return await scope[chat_name].system(content)
        

    async def cmd_continue(self, message: UserMessage, args: str):
        """Continue a chat. TODO: improve docs"""
        n = 1
        if args.startswith('x'):
            split = [x.strip() for x in args.split(maxsplit=1)]
            try:
                n = int(split[0][1:])
                if len(split) < 2: # if "xN" is all that's provided, we have to assume that's the name of the chat instance
                    n = 1
                    args = split[0]
                else:
                    args = split[1]
            except ValueError:
                pass
        scope = self.parent._get_scope()
        if args not in scope:
            return CommandFailure("No such ChatInstance in scope.")
        chat = scope[args]
        if len(chat.history) == 0:
            return CommandFailure("Sorry, OpenAI's API doesn't support completions with no messages.")
        return await scope[args].continue_(n)
    
    async def cmd_dump(self, message: UserMessage, args: str):
        """Dump out the full text of a chat."""
        scope = self.parent._get_scope()
        if args not in scope:
            return CommandFailure("No such ChatInstance in scope.")
        formatted_messages = [f'**__{m["role"]}__**:\n{m["content"]}\n' for m in scope[args].history]
        return '\n'.join(formatted_messages)