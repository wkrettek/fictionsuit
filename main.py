import discord

from fictionsuit.commands.debug import Debug
from fictionsuit.commands.research import Research
from fictionsuit.api_wrap.discord import DiscordBotClient
from fictionsuit.core.basic_command_system import BasicCommandSystem
from fictionsuit.commands.chat import Chat


def main():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    command_groups = [Debug(), Research(), Chat()]

    system = BasicCommandSystem(
        command_groups, respond_on_unrecognized=True, stats_ui=False
    )

    system.add_meta_group()

    client = DiscordBotClient(system, intents=intents)

    client.run()


if __name__ == "__main__":
    main()
