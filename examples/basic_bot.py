"""Basic bot initialization example in Discordia.

Demonstrates how to instantiate the bot, register a simple slash command,
listen to Hikari events, and run the application with validation.
"""

import hikari

from discordia import Bot

# Create Hikari's gateway client using your bot token.
gateway_bot = hikari.GatewayBot("YOUR_TOKEN")

# Initialize Discordia wrapping the gateway.
# The Bot provides dependency injection (DI), command registration, and interaction routing.
bot = Bot(gateway_bot)


# Register a basic Slash Command.
# By default, the command name in Discord will be the function name ('greet').
@bot.interactions.slash_command(description="Greets the user who executed the command")
async def greet(interaction: hikari.CommandInteraction) -> None:
    msg = f"Hello {interaction.user.mention}! You ran a command in Discordia!"
    await interaction.create_initial_response(hikari.ResponseType.MESSAGE_CREATE, msg)


# Listen to Discord/Hikari events.
# The event type is automatically inferred from the annotated parameter type (hikari.StartedEvent).
@bot.events.listen()
async def on_started(event: hikari.StartedEvent) -> None:
    # Synchronize application commands with Discord on startup
    await bot.sync_commands()

    me = gateway_bot.get_me()
    if me is not None:
        print(f"Bot connected successfully as {me.display_name} ({me.id})!")


# Run the bot using gateway_bot
if __name__ == "__main__":
    # You can verify that all functions are correctly typed before
    # starting the bot with `bot.validate_setup()`.

    # This prevents "dependency not found" errors from occurring in production.
    bot.validate_setup()
    gateway_bot.run()
