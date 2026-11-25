import hikari

from discordia import Bot

gateway_bot = hikari.GatewayBot("YOUR_TOKEN")
bot = Bot(gateway_bot)


# User Menu (User Context Menu)
# Discordia resolves the target user and injects it into `target: hikari.User`.
@bot.interactions.user_menu("View User Info")
async def view_user_info(
    interaction: hikari.CommandInteraction,
    target: hikari.User
) -> None:
    msg = (
        f"**User Details:**\n"
        f"- Username: {target.username}\n"
        f"- ID: `{target.id}`\n"
        f"- Mention: {target.mention}\n"
        f"- Is Bot: {'Yes' if target.is_bot else 'No'}"
    )
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        msg,
        flags=hikari.MessageFlag.EPHEMERAL
    )


# Message Menu (Message Context Menu)
# Discordia resolves the target message and injects it into `message: hikari.Message`
@bot.interactions.message_menu("Count Characters")
async def count_characters(
    interaction: hikari.CommandInteraction,
    message: hikari.Message
) -> None:
    content = message.content or "(message contains no text content)"
    length = len(content)

    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        f"The selected message contains **{length}** characters.",
        flags=hikari.MessageFlag.EPHEMERAL
    )


if __name__ == "__main__":
    bot.validate_setup()
    gateway_bot.run()
