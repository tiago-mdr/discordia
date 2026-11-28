"""Core Bot class."""

from __future__ import annotations

import hikari

from discordia import modules, router
from discordia.di import DependencyManager


class Bot(modules.Module):
    """Main application class for Discordia bots."""

    def __init__(self, gateway_bot: hikari.GatewayBot, divider: str | None = None) -> None:
        """Initialize the bot application.

        Args:
            gateway_bot: The underlying Hikari GatewayBot instance.
            divider: Optional delimiter string used to namespace custom_ids.
        """
        super().__init__()
        self._gateway_bot = gateway_bot
        self._di = DependencyManager()
        self._routing = router.Routing(self._registers, self._di, self._gateway_bot.event_manager, divider)

        self._di.add_dependency(self)

    def _validate_events(self) -> None:
        for event in self.registers.events:
            event.validate(self._di)

    def _validate_commands(self) -> None:
        for slash_command in self.registers.slash_commands:
            slash_command.validate(self._di)

        for user_menu in self.registers.user_menus:
            user_menu.validate(self._di)

        for message_menu in self.registers.message_menus:
            message_menu.validate(self._di)

    def _validate_components(self) -> None:
        for button in self.registers.buttons:
            button.validate(self._di)

        for select_menu in self.registers.select_menus:
            select_menu.validate(self._di)

        for modal in self.registers.modals:
            modal.validate(self._di)

    def _validate_handlers(self) -> None:
        for error_handler in self.registers.errors:
            error_handler.validate(self._di)

    def validate_setup(self) -> None:
        """Validate dependencies for all registered callbacks.

        Raises:
            DependencyError: If any registered callback has unsatisfiable dependencies.
        """
        self._validate_events()
        self._validate_commands()
        self._validate_components()
        self._validate_handlers()

    async def sync_commands(self, guild: int | hikari.UndefinedType = hikari.UNDEFINED) -> None:
        """Synchronize application commands with Discord.

        Args:
            guild: Target guild ID to sync commands to. UNDEFINED for global commands.
        """
        rest = self._gateway_bot.rest
        app = await rest.fetch_application()
        commands: list[hikari.api.CommandBuilder] = []

        commands.extend(slash_command.build() for slash_command in self.registers.slash_commands)
        commands.extend(user_menu.build() for user_menu in self.registers.user_menus)
        commands.extend(message_menu.build() for message_menu in self.registers.message_menus)

        await rest.set_application_commands(app, commands, guild)

    @property
    def gateway(self) -> hikari.GatewayBot:
        """The Hikari GatewayBot instance."""
        return self._gateway_bot

    @property
    def di(self) -> DependencyManager:
        """The DependencyManager associated with this bot."""
        return self._di

    @property
    def routing(self) -> router.Routing:
        """The Routing subsystem."""
        return self._routing
