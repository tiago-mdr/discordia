"""Main application file integrating multiple modules.

Demonstrates using `bot.merge(module)` to merge isolated feature trees
into a single central bot application.
"""

import hikari
from commands import mod

from discordia import Bot

gateway_bot = hikari.GatewayBot("YOUR_TOKEN")
bot = Bot(gateway_bot)

# Merge the external module into the bot's root registry tree.
# All commands, buttons, and listeners in `mod` are now routed by `bot`.
bot.merge(mod)


@bot.events.listen()
async def on_started(event: hikari.StartedEvent) -> None:
    # Synchronizes all commands (including those merged from submodules)
    await bot.sync_commands()
    print("Modules loaded and commands synchronized successfully!")


if __name__ == "__main__":
    bot.validate_setup()
    gateway_bot.run()
