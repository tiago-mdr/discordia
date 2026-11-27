from typing import Annotated

import hikari

from discordia import Bot, Option

gateway_bot = hikari.GatewayBot("YOUR_TOKEN")
bot = Bot(gateway_bot)


# Simple command with automatic type inference.
# Discordia inspects `text: str` and creates a Discord STRING option automatically.
@bot.interactions.slash_command(description="Repeats the text provided by the user")
async def imitate(interaction: hikari.CommandInteraction, text: str) -> None:
    msg = f"You typed: {text}"
    await interaction.create_initial_response(hikari.ResponseType.MESSAGE_CREATE, msg)


# Command with custom option metadata using Annotated[Type, Option(...)].
# Option allows configuring custom name, description, min/max constraints, autocomplete, etc.
@bot.interactions.slash_command(name="autocomplete", description="Demonstrates dynamic autocomplete options")
async def autocomplete_test(
    interaction: hikari.CommandInteraction,
    chosen_value: Annotated[
        str,
        Option(
            name="number",
            description="Pick a number from the interactive list",
            autocomplete=True,
        ),
    ],
) -> None:
    msg = f"You chose: {chosen_value}"
    await interaction.create_initial_response(hikari.ResponseType.MESSAGE_CREATE, msg)


# Autocomplete handler bound to the command above.
# Use `@command.autocomplete("parameter_name")`.
# Discordia injects the AutocompleteInteraction and the current value typed by the user.
@autocomplete_test.autocomplete("chosen_value")
async def autocomplete_value(interaction: hikari.AutocompleteInteraction, chosen_value: str) -> None:
    # Example dataset: numbers from 0 to 49
    all_numbers = [str(i) for i in range(50)]
    choices: list[hikari.impl.AutocompleteChoiceBuilder] = []

    # Discord permits up to 25 choices per autocomplete response
    for number in all_numbers:
        if len(choices) >= 25:
            break
        # Filter choices based on user input
        if not chosen_value or chosen_value in number:
            choices.append(hikari.impl.AutocompleteChoiceBuilder(name=f"Option {number}", value=number))

    await interaction.create_response(choices)


if __name__ == "__main__":
    bot.validate_setup()
    gateway_bot.run()
