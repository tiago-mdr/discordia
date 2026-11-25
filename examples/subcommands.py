"""Subcommands and Subcommand Groups example in Discordia.

In Discord, commands can be structured into up to three hierarchical levels:
1. Root command (/math add)
2. Subcommand group (/admin user ban)

This example shows how to declare both patterns cleanly and declaratively.
"""

import hikari

from discordia import Bot

gateway_bot = hikari.GatewayBot("YOUR_TOKEN")
bot = Bot(gateway_bot)


# Direct Subcommands (/math add and /math subtract) #

# Create the root command. The decorated function acts as a container for subcommands.
@bot.interactions.slash_command(name="math", description="Mathematical calculation commands")
async def math_command() -> None:
    pass


# Register /math add
@math_command.subcommand(name="add", description="Adds two integers together")
async def math_add(interaction: hikari.CommandInteraction, a: int, b: int) -> None:
    result = a + b
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        f"Operation: `{a} + {b}` = **{result}**"
    )


# Register /math subtract
@math_command.subcommand(name="subtract", description="Subtracts two integers")
async def math_subtract(interaction: hikari.CommandInteraction, a: int, b: int) -> None:
    result = a - b
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        f"Operation: `{a} - {b}` = **{result}**"
    )


# Subcommand Groups (/admin user kick and /admin user ban) #

# Root administrative command
@bot.interactions.slash_command(name="admin", description="Server administration commands")
async def admin_command() -> None:
    pass


# Create the /admin user ... subcommand group
user_group = admin_command.subcommand_group(
    name="user",
    description="User moderation operations"
)


# Add /admin user kick to the group
@user_group.subcommand(name="kick", description="Kicks a member from the guild")
async def user_kick(
    interaction: hikari.CommandInteraction,
    member: hikari.User,
    reason: str = "No reason provided"
) -> None:
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        f"Member {member.mention} kicked for: *{reason}*"
    )


# Add /admin user ban to the group
@user_group.subcommand(name="ban", description="Bans a member from the guild")
async def user_ban(
    interaction: hikari.CommandInteraction,
    member: hikari.User,
    reason: str = "No reason provided"
) -> None:
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        f"Member {member.mention} banned for: *{reason}*"
    )


if __name__ == "__main__":
    bot.validate_setup()
    gateway_bot.run()
