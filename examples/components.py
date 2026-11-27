import hikari

from discordia import Bot

gateway_bot = hikari.GatewayBot("YOUR_TOKEN")
# Configure custom_id namespace divider (defaults to ":")
bot = Bot(gateway_bot, divider=":")


# Command sending an interactive component panel
@bot.interactions.slash_command(description="Sends an interactive component panel")
async def panel(interaction: hikari.CommandInteraction) -> None:
    # Create action row with buttons
    row_buttons = hikari.impl.MessageActionRowBuilder()
    row_buttons.add_interactive_button(hikari.ButtonStyle.PRIMARY, "my_hello_button", label="Say Hello")
    # Example using namespaces: "ticket:close"
    # Discordia's router splits by ":" and matches the namespace/action
    row_buttons.add_interactive_button(hikari.ButtonStyle.DANGER, "ticket:close", label="Close Ticket")

    # Create action row with a text select menu
    row_select = hikari.impl.MessageActionRowBuilder()
    text_select = row_select.add_text_menu("color_menu", placeholder="Choose your favorite color...")
    text_select.add_option("Blue", "blue", description="Color of the sky and ocean")
    text_select.add_option("Green", "green", description="Color of nature")
    text_select.add_option("Red", "red", description="Color of passion and energy")

    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        "Here is your interactive component panel:",
        components=[row_buttons, row_select],
    )


# Button Handlers


# @bot.interactions.button matches the exact custom_id or namespace
@bot.interactions.button("my_hello_button")
async def on_hello_click(interaction: hikari.ComponentInteraction) -> None:
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        f"Hello, {interaction.user.mention}! You clicked the simple button.",
        flags=hikari.MessageFlag.EPHEMERAL,
    )


# When the button custom_id is "ticket:close" and divider is ":",
# Discordia routes to the registered "close" or "ticket:close" component handler.
@bot.interactions.button("close")
async def on_ticket_close(interaction: hikari.ComponentInteraction) -> None:
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        f"Ticket closed by {interaction.user.mention}! Received custom_id: `{interaction.custom_id}`",
        flags=hikari.MessageFlag.EPHEMERAL,
    )


# Select Menu Handler

# Discordia inspects the function signature.
# By annotating `chosen_colors: list[str]`, the selected values are extracted
# and injected directly into your callback arguments.


# You will type the list according to the type of the selection menu.
# For instance, if it is a selection menu for users, you should use "list[User]".
@bot.interactions.select_menu("color_menu")
async def on_color_selected(interaction: hikari.ComponentInteraction, chosen_colors: list[str]) -> None:
    color = chosen_colors[0] if chosen_colors else "none"
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        f"You selected the color: **{color.upper()}**!",
        flags=hikari.MessageFlag.EPHEMERAL,
    )


if __name__ == "__main__":
    bot.validate_setup()
    gateway_bot.run()
