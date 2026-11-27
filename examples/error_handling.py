"""Centralized Error Handling example in Discordia.

Demonstrates how to catch, log, and gracefully handle exceptions raised
during command routing and execution using `@bot.catch_error()`.
"""

import hikari

from discordia import Bot
from discordia.errors import CommandInteractionRoutingError

gateway_bot = hikari.GatewayBot("YOUR_TOKEN")
bot = Bot(gateway_bot)


# Commands that may raise exceptions
@bot.interactions.slash_command(description="Command demonstrating error handling")
async def divide(interaction: hikari.CommandInteraction, dividend: int, divisor: int) -> None:
    # A ZeroDivisionError may occur here
    result = dividend / divisor
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE, f"Result: `{dividend} / {divisor}` = **{result}**"
    )


# Global Error Handler #


# When a slash command fails, the router wraps the exception in CommandInteractionRoutingError
# and preserves the original exception in `error.__cause__`.
@bot.catch_error(CommandInteractionRoutingError)
async def handle_command_error(error: CommandInteractionRoutingError) -> None:
    original_cause = error.__cause__
    interaction = error.interaction_event.interaction

    if isinstance(original_cause, ZeroDivisionError):
        user_message = f"Warning: {original_cause}"
    else:
        user_message = f"An unexpected error occurred while executing the command: {original_cause}"

    # Respond to the user with an ephemeral message
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE, user_message, flags=hikari.MessageFlag.EPHEMERAL
    )


if __name__ == "__main__":
    bot.validate_setup()
    gateway_bot.run()
