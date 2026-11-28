"""Definition and buld of slash commands, subcommands, and groups."""

from __future__ import annotations

import typing
from collections import abc

import attrs
import hikari
from hikari.undefined import UNDEFINED

from discordia import di, errors, signatures

if typing.TYPE_CHECKING:
    import inspect


@attrs.define()
class Option:
    """Configuration metadata for a slash command option."""

    name: str = attrs.field(default="")
    """Name of the option. Defaults to the parameter name."""

    description: str = attrs.field(default="...")
    """Description of the option in Discord UI."""

    type: hikari.OptionType | None = attrs.field(default=None)
    """Option type in Discord."""

    is_required: bool | None = attrs.field(default=None)
    """Whether the option is required."""

    choices: abc.Sequence[hikari.CommandChoice] | None = attrs.field(default=None)
    """Preset choices for the option value."""

    channel_types: abc.Sequence[hikari.ChannelType | int] | None = attrs.field(default=None)
    """Restricts channel options to specific channel types."""

    autocomplete: bool = attrs.field(default=False)
    """Whether this option triggers an autocomplete interaction."""

    min_value: int | float | None = attrs.field(default=None)
    """Minimum numeric value allowed."""

    max_value: int | float | None = attrs.field(default=None)
    """Maximum numeric value allowed."""

    name_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(factory=dict[hikari.Locale | str, str])
    """Localized names for the option across Discord client locales."""

    description_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(
        factory=dict[hikari.Locale | str, str]
    )
    """Localized descriptions across Discord client locales."""

    min_length: int | None = attrs.field(default=None)
    """Minimum character length for string options."""

    max_length: int | None = attrs.field(default=None)
    """Maximum character length for string options."""


class SlashCommandExtractor:
    """Inspects a callback signature to extract and construct cmmand option specifications."""

    def __init__(self, callback: abc.Callable[..., object]) -> None:
        """Initialize the extractor for a callback.

        Args:
            callback: The slash command handler callback to inspect.
        """
        self.callback = callback
        self.current_parameter: inspect.Parameter

    def _build_command_option(
        self,
        inferred_type: hikari.OptionType,
        unwrapped_annotations: tuple[object, ...],
        option: Option,
    ) -> hikari.CommandOption:
        if not option.name:
            option.name = self.current_parameter.name

        if option.type:
            if inferred_type != option.type:
                msg = (
                    f'Option "{option.name}" was inferred as type '
                    f'"{inferred_type}", but was explicitly declared as '
                    f'"{option.type}".\n\n'
                    f"Review the type annotation or option declaration to ensure consistent typing."
                )
                raise errors.SlashCommandDefinitionError(msg, self.callback, self.current_parameter)
        else:
            option.type = inferred_type

        if option.is_required is None:
            option.is_required = bool(
                self.current_parameter.default == self.current_parameter.empty
                or type(None) not in unwrapped_annotations
            )
        elif option.is_required == (
            self.current_parameter.default != self.current_parameter.empty or type(None) in unwrapped_annotations
        ):
            msg = (
                f'Option "{option.name}" has a requirement setting (is_required={option.is_required}) '
                "that is incompatible with its declared type annotation.\n\n"
                "Required options must not have a union with None and must not have a default value, "
                "while optional options must allow None or provide a default value."
            )
            raise errors.SlashCommandDefinitionError(msg, self.callback, self.current_parameter)

        return hikari.CommandOption(
            type=option.type,
            name=option.name,
            description=option.description,
            is_required=option.is_required,
            choices=option.choices,
            options=None,  # the sub-options are not created here.
            channel_types=option.channel_types,
            autocomplete=option.autocomplete,
            min_value=option.min_value,
            max_value=option.max_value,
            name_localizations=option.name_localizations,
            description_localizations=option.description_localizations,
            min_length=option.min_length,
            max_length=option.max_length,
        )

    def _infer_type(self, types: tuple[object, ...]) -> hikari.OptionType | None:
        option_type: hikari.OptionType | None = None

        if str in types:
            option_type = hikari.OptionType.STRING
        elif int in types:
            option_type = hikari.OptionType.INTEGER
        elif float in types:
            option_type = hikari.OptionType.FLOAT
        elif bool in types:
            option_type = hikari.OptionType.BOOLEAN
        elif hikari.InteractionChannel in types:
            option_type = hikari.OptionType.CHANNEL
        elif hikari.Attachment in types:
            option_type = hikari.OptionType.ATTACHMENT
        elif hikari.User in types and hikari.Role in types:
            option_type = hikari.OptionType.MENTIONABLE
        elif hikari.User in types:
            option_type = hikari.OptionType.USER
        elif hikari.Role in types:
            option_type = hikari.OptionType.ROLE

        return option_type

    def _unwrap_annotations(self, annotation: object) -> tuple[object, ...]:
        if signatures.is_union(annotation):
            return typing.get_args(annotation)

        return (annotation,)

    def _parse_annotated(self) -> hikari.CommandOption | None:
        parameter_type, *metadata = typing.get_args(self.current_parameter.annotation)

        for meta in metadata:
            if not isinstance(meta, Option):
                continue

            parameter_type = self._unwrap_annotations(parameter_type)
            inferred_type = self._infer_type(parameter_type)
            if not inferred_type:
                msg = (
                    f'Parameter "{self.current_parameter.name}" is marked as a command option, '
                    f'but has an unsupported or unknown type annotation: "{self.current_parameter.annotation}".\n\n'
                    "Please use a supported type annotation (such as str, int, float, bool, hikari.User, "
                    "hikari.Role, hikari.InteractionChannel, hikari.Attachment, or unions thereof)."
                )
                raise errors.SlashCommandDefinitionError(msg, self.callback, self.current_parameter)

            return self._build_command_option(inferred_type, parameter_type, meta)
        return None

    def _parse_union(self, annotation: object) -> hikari.CommandOption | None:
        types = typing.get_args(annotation)
        inferred_type = self._infer_type(types)

        if inferred_type:
            return self._build_command_option(inferred_type, types, Option())

        return None

    def _parse_parameter(self) -> hikari.CommandOption | None:
        annotation = self.current_parameter.annotation
        if signatures.is_annotated(annotation):
            return self._parse_annotated()

        if signatures.is_union(annotation):
            return self._parse_union(annotation)

        annotation = (annotation,)
        inferred_type = self._infer_type(annotation)
        if inferred_type:
            return self._build_command_option(inferred_type, annotation, Option())

        return None

    def extract(self) -> dict[str, hikari.CommandOption]:
        """Extract command option mappings from the callback parameters.

        Returns:
            A mapping from parameter name to configured CommandOption instances.
        """
        option_map: dict[str, hikari.CommandOption] = {}
        signature = signatures.SignatureManager.get_signature(self.callback)

        for parameter in signature.parameters.values():
            if parameter.annotation is parameter.empty:
                continue

            self.current_parameter = parameter
            option = self._parse_parameter()

            if option:
                option_map[parameter.name] = option
                continue

        return option_map


@attrs.define()
class SlashCommandParsed:
    """Represents the parsed execution target and arguments for a slash command."""

    callback: abc.Callable[..., abc.Awaitable[typing.Any]] = attrs.field()
    """Asynchronous callback function to invoke."""

    data: dict[str, object] = attrs.field()
    """Dictionary of parsed option names and extracted values."""


@attrs.define()
class SlashCommandResponder:
    """Manages the response flow for slash commands and their autocompletes."""

    callback: abc.Callable[..., abc.Awaitable[typing.Any]] = attrs.field()
    option_map: dict[str, hikari.CommandOption] = attrs.field(init=False)
    autocomplete: dict[str, abc.Callable[..., abc.Awaitable[typing.Any]]] = attrs.field(
        factory=dict[str, abc.Callable[..., abc.Awaitable[typing.Any]]], init=False
    )

    def __attrs_post_init__(self) -> None:
        self.option_map = SlashCommandExtractor(self.callback).extract()

    def _extract_option(
        self, option: hikari.CommandInteractionOption, resolved: hikari.ResolvedOptionData | None
    ) -> object:
        if option.type in (
            hikari.OptionType.STRING,
            hikari.OptionType.INTEGER,
            hikari.OptionType.FLOAT,
            hikari.OptionType.BOOLEAN,
        ):
            return option.value

        if not isinstance(option.value, hikari.Snowflake):
            return None

        if not resolved:
            return None

        match option.type:
            case hikari.OptionType.ROLE:
                return resolved.roles[option.value]
            case hikari.OptionType.USER:
                return resolved.users[option.value]
            case hikari.OptionType.CHANNEL:
                return resolved.channels[option.value]
            case hikari.OptionType.ATTACHMENT:
                return resolved.attachments[option.value]
            case hikari.OptionType.MENTIONABLE:
                return resolved.roles.get(option.value) or resolved.users.get(option.value)
            case _:
                return None

    def validate(self, validator: di.DependencyManager) -> None:
        """Validate the possibility of executing the callback using the DI system.

        Args:
            validator: The DependencyManager used to validate dependencies.
        """
        lazy_types = {
            str,
            bool,
            int,
            float,
            hikari.CommandInteraction,
            hikari.InteractionChannel,
            hikari.User,
            hikari.Attachment,
            hikari.Role,
        }
        validator.validate(self.callback, lazy_types)

    def parse_options(
        self,
        options: abc.Sequence[hikari.CommandInteractionOption] | None = None,
        resolved: hikari.ResolvedOptionData | None = None,
    ) -> dict[str, object]:
        """Parse incoming interaction options into a parameter value mapping.

        Args:
            options: Received interaction option sequence.
            resolved: Resolved Discord entity data.

        Returns:
            Dictionary mapping parameter names to their extracted values.

        Raises:
            TypeError: If an option receives a mismatched type or a required option is omitted.
        """
        data: dict[str, object] = {}
        if options is None:
            options = []

        for parameter_name, parameter_option in self.option_map.items():
            for option in options:
                if option.name != parameter_option.name:
                    continue

                if option.type != parameter_option.type:
                    msg = (
                        f'Option "{parameter_option.name}" expects value of type '
                        f"{parameter_option.type}, but received {option.type}."
                    )
                    raise TypeError(msg)

                extracted_option = self._extract_option(option, resolved)
                if extracted_option is None:
                    continue

                data[parameter_name] = extracted_option
                break
            else:
                if parameter_option.is_required:
                    msg = (
                        f'Option "{parameter_option.name}" is required, but no '
                        "valid value was provided in the interaction."
                    )
                    raise TypeError(msg)

        return data

    def parse_autocomplete(
        self, autocomplete_options: abc.Sequence[hikari.AutocompleteInteractionOption] | None = None
    ) -> SlashCommandParsed:
        """Identify the focused option and retrieve its autocomplete callback.

        Args:
            autocomplete_options: Sequence of autocomplete options from the interaction.

        Returns:
            A SlashCommandParsed pointing to the autocomplete callback and parsed values.

        Raises:
            ValueError: If no options are provided or no focused option is found.
        """
        result: dict[str, object] = {}
        name: str | None = None

        if not autocomplete_options:
            msg = "No autocomplete options provided in interaction."
            raise ValueError(msg)

        for parameter_name, option in self.option_map.items():
            for autocomplete_option in autocomplete_options:
                if autocomplete_option.name != option.name:
                    continue

                if autocomplete_option.is_focused:
                    name = parameter_name
                result[parameter_name] = autocomplete_option.value

        if not name:
            msg = "No autocomplete option is currently focused."
            raise ValueError(msg)

        return SlashCommandParsed(self.autocomplete[name], result)


@attrs.define()
class SubCommand:
    """Represents a subcommand in a Discord slash command hierarchy."""

    name: str = attrs.field()
    description: str = attrs.field(default="...")
    name_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(factory=dict[hikari.Locale | str, str])
    description_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(
        factory=dict[hikari.Locale | str, str]
    )
    _responder: SlashCommandResponder | None = attrs.field(default=None, init=False)

    def get_responder(self) -> SlashCommandResponder:
        """Get the configured SlashCommandResponder.

        Returns:
            The SlashCommandResponder for this subcommand.

        Raises:
            ValueError: If no responder callback has been attached.
        """
        if self._responder:
            return self._responder
        msg = f'Subcommand "{self.name}" does not have a registered responder callback.'
        raise ValueError(msg)

    def responder(self, func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> typing.Self:
        """Set the handler callback for this subcommand.

        Args:
            func: Callable to handle this subcommand.

        Returns:
            Self instance for method chaining.
        """
        self._responder = SlashCommandResponder(func)
        return self

    def validate(self, validator: di.DependencyManager) -> None:
        """Validate dependencies for this subcommand.

        Args:
            validator: The DependencyManager used to validate dependencies.
        """
        self.get_responder().validate(validator)

    def autocomplete(self, name: str) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], typing.Self]:
        """Register an autocomplete handler for a specific option of this subcommand.

        Args:
            name: Parameter name of the option to handle autocomplete for.

        Returns:
            A decorator function returning self.
        """

        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> typing.Self:
            responder = self.get_responder()
            responder.autocomplete[name] = func
            return self

        return wrapper

    def parse_subcommand_interaction(
        self,
        subcommand_options: abc.Sequence[hikari.CommandInteractionOption] | None = None,
        resolved: hikari.ResolvedOptionData | None = None,
    ) -> SlashCommandParsed:
        """Parse interaction options for this subcommand into a SlashCommandParsed container.

        Args:
            subcommand_options: Nested option sequence for this subcommand.
            resolved: Resolved Discord entity data.

        Returns:
            A SlashCommandParsed instance.

        Raises:
            ValueError: If no responder callback has been attached.
        """
        responder = self.get_responder()
        return SlashCommandParsed(responder.callback, responder.parse_options(subcommand_options, resolved))

    def parse_subcommand_autocomplete(
        self, autocomplete: abc.Sequence[hikari.AutocompleteInteractionOption] | None = None
    ) -> SlashCommandParsed:
        """Parse autocomplete interaction for this subcommand.

        Args:
            autocomplete: Nested autocomplete options.

        Returns:
            A SlashCommandParsed instance pointing to the autocomplete callback.

        Raises:
            ValueError: If no autocomplete or callback handler is registered.
        """
        responder = self.get_responder()
        if responder.autocomplete:
            return responder.parse_autocomplete(autocomplete)

        msg = f'Subcommand "{self.name}" does not have an autocomplete handler registered.'
        raise ValueError(msg)

    def build(self) -> hikari.CommandOption:
        """Build a Discord command option representation for this subcommand.

        Returns:
            A CommandOption of type SUB_COMMAND.
        """
        responder = self._responder
        options = list(responder.option_map.values()) if responder else []
        return hikari.CommandOption(
            type=hikari.OptionType.SUB_COMMAND,
            name=self.name,
            description=self.description,
            options=options,
            name_localizations=self.name_localizations,
            description_localizations=self.description_localizations,
        )


@attrs.define()
class SubCommandGroup:
    """Represents a subcommand group containing nested subcommands."""

    name: str = attrs.field()
    description: str = attrs.field(default="...")
    name_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(factory=dict[hikari.Locale | str, str])
    description_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(
        factory=dict[hikari.Locale | str, str]
    )
    subcommands: dict[str, SubCommand] = attrs.field(factory=dict[str, SubCommand])

    def subcommand(
        self,
        name: str = "",
        description: str = "...",
        name_localizations: abc.Mapping[hikari.Locale | str, str] | None = None,
        description_localizations: abc.Mapping[hikari.Locale | str, str] | None = None,
    ) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], SubCommand]:
        """Declare a nested subcommand within this group.

        Args:
            name: Subcommand name. Defaults to the decorated function name if empty.
            description: Subcommand description.
            name_localizations: Localized names across locales.
            description_localizations: Localized descriptions across locales.

        Returns:
            A decorator returning the created SubCommand instance.
        """

        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> SubCommand:
            subcommand_name = name or func.__name__
            subcommand = SubCommand(
                subcommand_name,
                description=description,
                name_localizations=name_localizations if name_localizations is not None else {},
                description_localizations=description_localizations if description_localizations is not None else {},
            )
            subcommand.responder(func)
            self.add_subcommand(subcommand)
            return subcommand

        return wrapper

    def add_subcommand(self, subcommand: SubCommand) -> None:
        """Add a SubCommand instance to this group.

        Args:
            subcommand: The SubCommand to add.

        Raises:
            ValueError: If a subcommand with the same name already exists in this group.
        """
        if subcommand.name in self.subcommands:
            msg = f'Subcommand "{subcommand.name}" already exists in command group "{self.name}".'
            raise ValueError(msg)
        self.subcommands[subcommand.name] = subcommand

    def get_subcommand(self, subcommand_name: str) -> SubCommand:
        """Retrieve a nested subcommand by name.

        Args:
            subcommand_name: The name of the subcommand.

        Returns:
            The matching SubCommand instance.

        Raises:
            ValueError: If the subcommand is not found in this group.
        """
        subcommand = self.subcommands.get(subcommand_name)
        if subcommand:
            return subcommand

        msg = f'Subcommand "{subcommand_name}" was not found in command group "{self.name}".'
        raise ValueError(msg)

    def validate(self, validator: di.DependencyManager) -> None:
        """Validate dependencies for all subcommands within this group.

        Args:
            validator: The DependencyManager used to validate dependencies.
        """
        for subcommand in self.subcommands.values():
            subcommand.validate(validator)

    def parse_interaction_group(
        self,
        subcommand_interaction: hikari.CommandInteractionOption,
        resolved: hikari.ResolvedOptionData | None = None,
    ) -> SlashCommandParsed:
        """Parse an interaction directed at a subcommand within this group.

        Args:
            subcommand_interaction: The interaction option corresponding to this group.
            resolved: Resolved Discord entity data.

        Returns:
            A SlashCommandParsed instance for the targeted subcommand.

        Raises:
            ValueError: If the nested subcommand name is not registered.
        """
        subcommand = self.subcommands.get(subcommand_interaction.name)
        if subcommand is None:
            msg = f'Subcommand "{subcommand_interaction.name}" was not found in command group "{self.name}".'
            raise ValueError(msg)

        return subcommand.parse_subcommand_interaction(subcommand_interaction.options, resolved)

    def parse_autocomplete_group(
        self, subcommand_autocomplete: hikari.AutocompleteInteractionOption
    ) -> SlashCommandParsed:
        """Parse an autocomplete interaction targeting a subcommand within this group.

        Args:
            subcommand_autocomplete: The autocomplete option for this group.

        Returns:
            A SlashCommandParsed pointing to the targeted subcommand's autocomplete callback.

        Raises:
            ValueError: If the nested subcommand is not found.
        """
        subcommand = self.subcommands.get(subcommand_autocomplete.name)
        if subcommand is None:
            msg = f'Subcommand "{subcommand_autocomplete.name}" was not found in command group "{self.name}".'
            raise ValueError(msg)

        return subcommand.parse_subcommand_autocomplete(subcommand_autocomplete.options)

    def build(self) -> hikari.CommandOption:
        """Build a Discord command option representation for this subcommand.

        Returns:
            A CommandOption of type SUB_COMMAND_GROUP with nested subcommands.
        """
        options = [subcommand.build() for subcommand in self.subcommands.values()]
        return hikari.CommandOption(
            type=hikari.OptionType.SUB_COMMAND_GROUP,
            name=self.name,
            description=self.description,
            options=options,
            name_localizations=self.name_localizations,
            description_localizations=self.description_localizations,
        )


@attrs.define()
class SlashCommand:
    """Represents a top-level Discord application slash command."""

    name: str = attrs.field()
    description: str = attrs.field(default="...")
    default_member_permissions: hikari.UndefinedType | hikari.Permissions = attrs.field(default=UNDEFINED)
    is_nsfw: hikari.UndefinedOr[bool] = attrs.field(default=UNDEFINED)
    name_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(factory=dict[hikari.Locale | str, str])
    integration_types: hikari.UndefinedOr[abc.Sequence[hikari.ApplicationIntegrationType]] = attrs.field(
        default=UNDEFINED
    )
    context_types: hikari.UndefinedOr[abc.Sequence[hikari.ApplicationContextType]] = attrs.field(default=UNDEFINED)
    description_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(
        factory=dict[hikari.Locale | str, str]
    )

    _subcommands: dict[str, SubCommand] = attrs.field(factory=dict[str, SubCommand], init=False)
    _subcommands_group: dict[str, SubCommandGroup] = attrs.field(factory=dict[str, SubCommandGroup], init=False)
    _responder: SlashCommandResponder | None = attrs.field(default=None, init=False)

    def responder(self, func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> typing.Self:
        """Set the top-level handler callback for this slash command.

        Args:
            func: Callable handling command executions.

        Returns:
            Self instance for method chaining.
        """
        self._responder = SlashCommandResponder(func)
        return self

    def autocomplete(self, name: str) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], typing.Self]:
        """Register an autocomplete handler for a top-level option.

        Args:
            name: Parameter name of the option to handle autocomplete for.

        Returns:
            A decorator function returning self.
        """

        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> typing.Self:
            responder = self.get_responder()
            responder.autocomplete[name] = func
            return self

        return wrapper

    def get_responder(self) -> SlashCommandResponder:
        """Get the configured SlashCommandResponder.

        Returns:
            The SlashCommandResponder for this command.

        Raises:
            ValueError: If no responder callback has been attached.
        """
        if self._responder:
            return self._responder
        msg = f'Slash command "{self.name}" does not have a registered responder callback.'
        raise ValueError(msg)

    def validate(self, validator: di.DependencyManager) -> None:
        """Validate dependencies for this command and all subcommands/groups.

        Args:
            validator: The DependencyManager used to validate dependencies.
        """
        if self._responder:
            self._responder.validate(validator)

        for subcommand in self._subcommands.values():
            subcommand.validate(validator)

        for subcommand_group in self._subcommands_group.values():
            subcommand_group.validate(validator)

    def add_subcommand(self, subcommand: SubCommand) -> None:
        """Add a SubCommand to this slash command.

        Args:
            subcommand: The SubCommand to register.

        Raises:
            ValueError: If a subcommand with the same name already exists.
        """
        if subcommand.name in self._subcommands:
            msg = f'Subcommand "{subcommand.name}" already exists in slash command "{self.name}".'
            raise ValueError(msg)
        self._subcommands[subcommand.name] = subcommand

    def get_subcommand(self, subcommand_name: str) -> SubCommand:
        """Retrieve a direct subcommand by name.

        Args:
            subcommand_name: The name of the subcommand.

        Returns:
            The matching SubCommand instance.

        Raises:
            KeyError: If the subcommand is not found.
        """
        subcommand = self._subcommands.get(subcommand_name)
        if subcommand:
            return subcommand

        msg = f'Subcommand "{subcommand_name}" was not found in slash command "{self.name}".'
        raise KeyError(msg)

    def subcommand(
        self,
        name: str,
        description: str = "...",
        name_localizations: abc.Mapping[hikari.Locale | str, str] | None = None,
        description_localizations: abc.Mapping[hikari.Locale | str, str] | None = None,
    ) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], SubCommand]:
        """Declare a direct subcommand under this slash command.

        Args:
            name: Subcommand name.
            description: Subcommand description.
            name_localizations: Localized names across locales.
            description_localizations: Localized descriptions across locales.

        Returns:
            A decorator returning the created SubCommand instance.
        """

        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> SubCommand:
            subcommand = SubCommand(
                name,
                description=description,
                name_localizations=name_localizations if name_localizations is not None else {},
                description_localizations=description_localizations if description_localizations is not None else {},
            )
            subcommand.responder(func)
            self.add_subcommand(subcommand)
            return subcommand

        return wrapper

    def add_subcommand_group(self, subcommand_group: SubCommandGroup) -> None:
        """Add a SubCommandGroup to this slash command.

        Args:
            subcommand_group: The SubCommandGroup to add.

        Raises:
            ValueError: If a subcommand group with the same name already exists.
        """
        if subcommand_group.name in self._subcommands_group:
            msg = f'Subcommand group "{subcommand_group.name}" already exists in slash command "{self.name}".'
            raise ValueError(msg)
        self._subcommands_group[subcommand_group.name] = subcommand_group

    def subcommand_group(
        self,
        name: str,
        description: str = "...",
        name_localizations: abc.Mapping[hikari.Locale | str, str] | None = None,
        description_localizations: abc.Mapping[hikari.Locale | str, str] | None = None,
    ) -> SubCommandGroup:
        """Declare a subcommand group under this slash command.

        Args:
            name: Group name.
            description: Group description.
            name_localizations: Localized names across locales.
            description_localizations: Localized descriptions across locales.

        Returns:
            The configured SubCommandGroup instance.
        """
        group = SubCommandGroup(
            name,
            description=description,
            name_localizations=name_localizations if name_localizations is not None else {},
            description_localizations=description_localizations if description_localizations is not None else {},
        )
        self.add_subcommand_group(group)
        return group

    def get_subcommand_group(self, subcommand_group_name: str) -> SubCommandGroup:
        """Retrieve a subcommand group by name.

        Args:
            subcommand_group_name: Name of the subcommand group.

        Returns:
            The matching SubCommandGroup instance.

        Raises:
            KeyError: If the subcommand group is not found.
        """
        subcommand_group = self._subcommands_group.get(subcommand_group_name)
        if subcommand_group:
            return subcommand_group

        msg = f'Subcommand group "{subcommand_group_name}" was not found in slash command "{self.name}".'
        raise KeyError(msg)

    def _unwrap_subcommand(self, interaction_option: hikari.CommandInteractionOption) -> SubCommand | None:
        if interaction_option.type == hikari.OptionType.SUB_COMMAND:
            return self.get_subcommand(interaction_option.name)
        return None

    def _unwrap_subcommand_group(self, interaction_option: hikari.CommandInteractionOption) -> SubCommandGroup | None:
        if interaction_option.type == hikari.OptionType.SUB_COMMAND_GROUP:
            subcommand_group = self.get_subcommand_group(interaction_option.name)
            if not interaction_option.options or interaction_option.options[0].type != hikari.OptionType.SUB_COMMAND:
                msg = f'Subcommand group "{subcommand_group.name}" must be accompanied by a nested subcommand.'
                raise ValueError(msg)
            return subcommand_group

        return None

    def parse_interaction(self, interaction: hikari.CommandInteraction) -> SlashCommandParsed:
        """Parse an incoming command interaction into target callback and arguments.

        Args:
            interaction: The incoming CommandInteraction payload.

        Returns:
            A SlashCommandParsed instance.
        """
        if interaction.options:
            option = interaction.options[0]

            subcommand = self._unwrap_subcommand(option)
            if subcommand:
                return subcommand.parse_subcommand_interaction(option.options, interaction.resolved)

            subcommand_group = self._unwrap_subcommand_group(option)
            if subcommand_group:
                assert option.options is not None
                return subcommand_group.parse_interaction_group(option.options[0], interaction.resolved)

        responder = self.get_responder()
        return SlashCommandParsed(
            responder.callback,
            responder.parse_options(options=interaction.options, resolved=interaction.resolved),
        )

    def parse_autocomplete_interaction(self, autocomplete: hikari.AutocompleteInteraction) -> SlashCommandParsed:
        """Parse an incoming autocomplete interaction to its designated callback.

        Args:
            autocomplete: The incoming AutocompleteInteraction payload.

        Returns:
            A SlashCommandParsed instance.

        Raises:
            ValueError: If no autocomplete handler is registered.
        """
        if autocomplete.options:
            option = autocomplete.options[0]

            subcommand = self._unwrap_subcommand(option)
            if subcommand:
                return subcommand.parse_subcommand_autocomplete(option.options)

            subcommand_group = self._unwrap_subcommand_group(option)
            if subcommand_group:
                assert option.options is not None
                return subcommand_group.parse_autocomplete_group(option.options[0])

        responder = self.get_responder()
        if responder.autocomplete:
            return responder.parse_autocomplete(autocomplete.options)

        msg = f'Slash command "{self.name}" does not have an autocomplete handler registered.'
        raise ValueError(msg)

    def build(self) -> hikari.impl.SlashCommandBuilder:
        """Build the slash command for registration on Discord.

        Returns:
            A configured SlashCommandBuilder instance ready for command sync.
        """
        options: list[hikari.CommandOption] = []

        if self._subcommands or self._subcommands_group:
            options.extend(subcommand.build() for subcommand in self._subcommands.values())
            options.extend(subcommand_group.build() for subcommand_group in self._subcommands_group.values())
        elif self._responder:
            options.extend(self._responder.option_map.values())

        return hikari.impl.SlashCommandBuilder(
            name=self.name,
            description=self.description,
            default_member_permissions=self.default_member_permissions,
            is_nsfw=self.is_nsfw,
            name_localizations=self.name_localizations,
            integration_types=self.integration_types,
            context_types=self.context_types,
            options=options,
            description_localizations=self.description_localizations,
        )
