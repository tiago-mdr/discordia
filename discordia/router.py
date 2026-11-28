"""Event and interaction routing subsystem connecting Hikari events to Discordia responders."""

from __future__ import annotations

import typing

import hikari

from discordia import errors

if typing.TYPE_CHECKING:
    from hikari.api import EventManager

    from discordia.di import DependencyManager
    from discordia.interactions.components.modal import Modal
    from discordia.modules import registry_store


# this is a temporary implementation
# as the way interactions are executed is updated, this will also change significantly
class Routing:
    """Dispatches incoming Hikari events and Discord interactions to registered handlers."""

    def __init__(
        self,
        registers: registry_store.RegistryStore,
        executor: DependencyManager,
        event_manager: EventManager,
        divider: str | None = None,
    ) -> None:
        """Initialize the routing system and subscribe internal routers to the EventManager.

        Args:
            registers: The central RegistryStore of the application.
            executor: The DependencyManager used to execute callbacks with DI.
            event_manager: The Hikari EventManager to subscribe to.
            divider: Optional namespace delimiter string for custom_ids.
        """
        self._registers = registers
        self._executor = executor
        self._event_manager = event_manager
        self._divider = divider
        self._set_routers()

    async def route_slash_command(self, interaction: hikari.CommandInteraction) -> None:
        """Route an application slash command interaction to its responder callback.

        Args:
            interaction: The incoming CommandInteraction payload.

        Raises:
            InteractionNotFoundError: If no matching slash command is registered.
        """
        slash_command = self._registers.slash_commands.get(interaction.command_name)
        if slash_command:
            responder = slash_command.parse_interaction(interaction)
            await self._executor.execute(responder.callback, interaction, **responder.data)
            return

        msg = f'Slash command "{interaction.command_name}" was not found in registered commands.'
        raise errors.InteractionNotFoundError(msg)

    async def route_message_menu(self, interaction: hikari.CommandInteraction) -> None:
        """Route a message context menu interaction to its responder callback.

        Args:
            interaction: The incoming CommandInteraction payload.

        Raises:
            InteractionNotFoundError: If no matching message menu is registered.
        """
        message_menu = self._registers.message_menus.get(interaction.command_name)
        if message_menu:
            message = message_menu.extract_message(interaction)
            await self._executor.execute(message_menu.callback, interaction, message)
            return

        msg = f'Message menu command "{interaction.command_name}" was not found in registered message menus.'
        raise errors.InteractionNotFoundError(msg)

    async def route_user_menu(self, interaction: hikari.CommandInteraction) -> None:
        """Route a user context menu interaction to its responder callback.

        Args:
            interaction: The incoming CommandInteraction payload.

        Raises:
            InteractionNotFoundError: If no matching user menu is registered.
        """
        user_menu = self._registers.user_menus.get(interaction.command_name)
        if user_menu:
            user = user_menu.parse_user_menu(interaction)
            await self._executor.execute(user_menu.callback, interaction, user)
            return

        msg = f'User menu command "{interaction.command_name}" was not found in registered user menus.'
        raise errors.InteractionNotFoundError(msg)

    async def route_command_interaction(self, interaction_event: hikari.CommandInteractionCreateEvent) -> None:
        """Dispatch incoming command interaction events by command type.

        Args:
            interaction_event: The CommandInteractionCreateEvent received from Hikari.

        Raises:
            CommandInteractionRoutingError: If an unhandled exception occurs during command routing.
        """
        interaction = interaction_event.interaction

        try:
            match interaction.command_type:
                case hikari.CommandType.SLASH:
                    await self.route_slash_command(interaction)
                case hikari.CommandType.USER:
                    await self.route_user_menu(interaction)
                case hikari.CommandType.MESSAGE:
                    await self.route_message_menu(interaction)
                case _:
                    pass
        except Exception as e:
            raise errors.CommandInteractionRoutingError(interaction_event) from e

    async def route_autocomplete_interaction(
        self, autocomplete_event: hikari.AutocompleteInteractionCreateEvent
    ) -> None:
        """Dispatch incoming autocomplete interactions to registered command handlers.

        Args:
            autocomplete_event: The AutocompleteInteractionCreateEvent received from Hikari.

        Raises:
            InteractionNotFoundError: If no matching command is found for autocomplete.
            AutoCompleteRoutinError: If an error occurs during autocomplete execution.
        """
        interaction = autocomplete_event.interaction
        slash_command = self._registers.slash_commands.get(interaction.command_name)

        try:
            if slash_command:
                responder = slash_command.parse_autocomplete_interaction(interaction)
                await self._executor.execute(responder.callback, interaction, **responder.data)
                return
            msg = f'Slash command "{interaction.command_name}" for autocomplete was not found in registered commands.'
            raise errors.InteractionNotFoundError(msg)
        except Exception as e:
            raise errors.AutoCompleteRoutinError(autocomplete_event) from e

    async def route_button_interaction(self, interaction: hikari.ComponentInteraction) -> None:
        """Route an interactive button component click to its registered callback.

        Args:
            interaction: The incoming ComponentInteraction payload.

        Raises:
            InteractionNotFoundError: If no registered button matches the custom_id.
        """
        custom_id_namespaces = interaction.custom_id.split(self._divider)

        for namespace in reversed(custom_id_namespaces):
            button = self._registers.buttons.get(namespace)
            if button:
                await self._executor.execute(button.callback, interaction)
                return

        msg = f'Button with custom_id "{interaction.custom_id}" was not found in registered buttons.'
        raise errors.InteractionNotFoundError(msg)

    async def route_select_menu_interaction(self, interaction: hikari.ComponentInteraction) -> None:
        """Route an interactive select menu submission to its registered callback.

        Args:
            interaction: The incoming ComponentInteraction payload.

        Raises:
            InteractionNotFoundError: If no registered select menu matches the custom_id.
        """
        custom_id_namespaces = interaction.custom_id.split(self._divider)

        for namespace in reversed(custom_id_namespaces):
            select_menu = self._registers.select_menus.get(namespace)
            if select_menu:
                values = select_menu.parse_select_menu(interaction)
                await self._executor.execute(select_menu.callback, interaction, **values)
                return

        msg = f'Select menu with custom_id "{interaction.custom_id}" was not found in registered select menus.'
        raise errors.InteractionNotFoundError(msg)

    async def route_component_interaction(
        self, component_interaction_event: hikari.ComponentInteractionCreateEvent
    ) -> None:
        """Dispatch incoming component interaction events by component type.

        Args:
            component_interaction_event: The ComponentInteractionCreateEvent received from Hikari.

        Raises:
            ComponentInteractionRoutingError: If an unhandled exception occurs during component routing.
        """
        interaction = component_interaction_event.interaction

        try:
            match interaction.component_type:
                case hikari.ComponentType.BUTTON:
                    await self.route_button_interaction(interaction)
                case (
                    hikari.ComponentType.TEXT_SELECT_MENU
                    | hikari.ComponentType.ROLE_SELECT_MENU
                    | hikari.ComponentType.USER_SELECT_MENU
                    | hikari.ComponentType.CHANNEL_SELECT_MENU
                    | hikari.ComponentType.MENTIONABLE_SELECT_MENU
                ):
                    await self.route_select_menu_interaction(interaction)
                case _:
                    pass
        except Exception as e:
            raise errors.ComponentInteractionRoutingError(component_interaction_event) from e

    async def route_modal_interaction(self, modal_interaction_event: hikari.ModalInteractionCreateEvent) -> None:
        """Dispatch incoming modal submission interactions to registered modal handlers.

        Args:
            modal_interaction_event: The ModalInteractionCreateEvent received from Hikari.

        Raises:
            InteractionNotFoundError: If no registered modal matches the custom_id.
            ModalRoutingError: If an unhandled error occurs during modal routing.
        """
        interaction = modal_interaction_event.interaction
        custom_id_namespaces = interaction.custom_id.split(self._divider)

        modal: Modal | None = None
        for namespace in reversed(custom_id_namespaces):
            modal = self._registers.modals.get(namespace) or modal

        try:
            if modal:
                await self._executor.execute(modal.callback, interaction)
                return

            msg = f'Modal with custom_id "{interaction.custom_id}" was not found in registered modals.'
            raise errors.InteractionNotFoundError(msg)
        except Exception as e:
            raise errors.ModalRoutingError(modal_interaction_event) from e

    async def route_event(self, event: hikari.Event) -> None:
        """Dispatch general gateway events to all registered event responders.

        Args:
            event: The incoming Hikari Event instance.
        """
        for event_type in event.dispatches():
            event_responder = self._registers.events.get(event_type)

            if event_responder:
                for callback in event_responder.callbacks:
                    await self._executor.execute(callback, event)

    async def route_error(self, error_event: hikari.ExceptionEvent[typing.Any]) -> None:
        """Dispatch an unhandled exception event to a registered error handler.

        Args:
            error_event: The ExceptionEvent trigged by Hikari containing the exception.
        """
        error = error_event.exception
        error_handler = self._registers.errors.get(type(error))

        if error_handler:
            await self._executor.execute(error_handler.callback, error)
        else:
            raise error

    def _set_routers(self) -> None:
        self._event_manager.subscribe(hikari.CommandInteractionCreateEvent, self.route_command_interaction)
        self._event_manager.subscribe(hikari.AutocompleteInteractionCreateEvent, self.route_autocomplete_interaction)
        self._event_manager.subscribe(hikari.ComponentInteractionCreateEvent, self.route_component_interaction)
        self._event_manager.subscribe(hikari.ModalInteractionCreateEvent, self.route_modal_interaction)
        self._event_manager.subscribe(hikari.Event, self.route_event)
        self._event_manager.subscribe(hikari.ExceptionEvent, self.route_error)
