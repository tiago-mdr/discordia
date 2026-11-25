"""Independent module containing commands and components.

Instances of `Module` function as isolated feature bundles.
They maintain their own registers for commands, events,
buttons, select menus, and error responders.
"""

import hikari

from discordia import Module

# Create the module instance
mod = Module()


@mod.interactions.slash_command(description="Test command defined inside an independent module")
async def ping(interaction: hikari.CommandInteraction) -> None:
    row = hikari.impl.MessageActionRowBuilder()
    row.add_interactive_button(
        hikari.ButtonStyle.PRIMARY,
        "module_button",
        label="Module Button"
    )

    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        "Pong! This command was defined inside a separate module.",
        component=row
    )


@mod.interactions.button("module_button")
async def on_module_button_click(interaction: hikari.ComponentInteraction) -> None:
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        "You clicked the button managed by the module!",
        flags=hikari.MessageFlag.EPHEMERAL
    )
