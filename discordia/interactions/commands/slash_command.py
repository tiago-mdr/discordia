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
    name: str = attrs.field(default="")
    description: str = attrs.field(default="...")
    type: hikari.OptionType | None = attrs.field(default=None)
    is_required: bool | None = attrs.field(default=None)
    choices: abc.Sequence[hikari.CommandChoice] | None = attrs.field(default=None)
    options: abc.Sequence[hikari.CommandOption] | None = attrs.field(default=None)
    channel_types: abc.Sequence[hikari.ChannelType | int] | None = attrs.field(default=None)
    autocomplete: bool = attrs.field(default=False)
    min_value: int | float | None = attrs.field(default=None)
    max_value: int | float | None = attrs.field(default=None)
    name_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(factory=dict[hikari.Locale | str, str])
    description_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(
        factory=dict[hikari.Locale | str, str]
    )
    min_length: int | None = attrs.field(default=None)
    max_length: int | None = attrs.field(default=None)


class SlashCommandExtractor:
    def __init__(self, callback: abc.Callable[..., object]) -> None:
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

        # Additional validation can be encapsulated in an option build method
        # and caught as SlashCommandDefinitionError if needed
        return hikari.CommandOption(
            type=option.type,
            name=option.name,
            description=option.description,
            is_required=option.is_required,
            choices=option.choices,
            options=option.options,
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
            return signatures.extract_args(annotation)

        return (annotation,)

    def _parse_annotated(self) -> hikari.CommandOption | None:
        parameter_type, *metadata = signatures.extract_args(self.current_parameter.annotation)

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
        types = signatures.extract_args(annotation)
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
        option_map: dict[str, hikari.CommandOption] = {}
        signature = signatures.SignatureManager.get_signature(self.callback, cache=True)

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
    callback: abc.Callable[..., abc.Awaitable[typing.Any]] = attrs.field()
    data: dict[str, object] = attrs.field()


@attrs.define()
class SlashCommandResponder:
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
    name: str = attrs.field()
    description: str = attrs.field(default="...")
    name_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(factory=dict[hikari.Locale | str, str])
    description_localizations: abc.Mapping[hikari.Locale | str, str] = attrs.field(
        factory=dict[hikari.Locale | str, str]
    )
    _responder: SlashCommandResponder | None = attrs.field(default=None, init=False)

    def get_responder(self) -> SlashCommandResponder:
        if self._responder:
            return self._responder
        msg = f'Subcommand "{self.name}" does not have a registered responder callback.'
        raise ValueError(msg)

    def responder(self, func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> typing.Self:
        self._responder = SlashCommandResponder(func)
        return self

    def validate(self, validator: di.DependencyManager) -> None:
        self.get_responder().validate(validator)

    def autocomplete(self, name: str) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], typing.Self]:
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
        responder = self.get_responder()
        return SlashCommandParsed(responder.callback, responder.parse_options(subcommand_options, resolved))

    def parse_subcommand_autocomplete(
        self, autocomplete: abc.Sequence[hikari.AutocompleteInteractionOption] | None = None
    ) -> SlashCommandParsed:
        responder = self.get_responder()
        if responder.autocomplete:
            return responder.parse_autocomplete(autocomplete)

        msg = f'Subcommand "{self.name}" does not have an autocomplete handler registered.'
        raise ValueError(msg)

    def build(self) -> hikari.CommandOption:
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
        if subcommand.name in self.subcommands:
            msg = f'Subcommand "{subcommand.name}" already exists in command group "{self.name}".'
            raise ValueError(msg)
        self.subcommands[subcommand.name] = subcommand

    def get_subcommand(self, subcommand_name: str) -> SubCommand:
        subcommand = self.subcommands.get(subcommand_name)
        if subcommand:
            return subcommand

        msg = f'Subcommand "{subcommand_name}" was not found in command group "{self.name}".'
        raise ValueError(msg)

    def validate(self, validator: di.DependencyManager) -> None:
        for subcommand in self.subcommands.values():
            subcommand.validate(validator)

    def parse_interaction_group(
        self,
        subcommand_interaction: hikari.CommandInteractionOption,
        resolved: hikari.ResolvedOptionData | None = None,
    ) -> SlashCommandParsed:
        subcommand = self.subcommands.get(subcommand_interaction.name)
        if subcommand is None:
            msg = f'Subcommand "{subcommand_interaction.name}" was not found in command group "{self.name}".'
            raise ValueError(msg)

        return subcommand.parse_subcommand_interaction(subcommand_interaction.options, resolved)

    def parse_autocomplete_group(
        self, subcommand_autocomplete: hikari.AutocompleteInteractionOption
    ) -> SlashCommandParsed:
        subcommand = self.subcommands.get(subcommand_autocomplete.name)
        if subcommand is None:
            msg = f'Subcommand "{subcommand_autocomplete.name}" was not found in command group "{self.name}".'
            raise ValueError(msg)

        return subcommand.parse_subcommand_autocomplete(subcommand_autocomplete.options)

    def build(self) -> hikari.CommandOption:
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
        self._responder = SlashCommandResponder(func)
        return self

    def autocomplete(self, name: str) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], typing.Self]:
        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> typing.Self:
            responder = self.get_responder()
            responder.autocomplete[name] = func
            return self

        return wrapper

    def get_responder(self) -> SlashCommandResponder:
        if self._responder:
            return self._responder
        msg = f'Slash command "{self.name}" does not have a registered responder callback.'
        raise ValueError(msg)

    def validate(self, validator: di.DependencyManager) -> None:
        if self._responder:
            self._responder.validate(validator)
        else:
            for subcommand in self._subcommands.values():
                subcommand.validate(validator)

            for subcommand_group in self._subcommands_group.values():
                subcommand_group.validate(validator)

    def add_subcommand(self, subcommand: SubCommand) -> None:
        if subcommand.name in self._subcommands:
            msg = f'Subcommand "{subcommand.name}" already exists in slash command "{self.name}".'
            raise ValueError(msg)
        self._subcommands[subcommand.name] = subcommand

    def get_subcommand(self, subcommand_name: str) -> SubCommand:
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
        if subcommand_group.name in self._subcommands_group:
            msg = f'Subcommand group "{subcommand_group.name}" already exists in slash command "{self.name}".'
            raise ValueError(msg)
        self._subcommands_group[subcommand_group.name] = subcommand_group

    def get_subcommand_group(self, subcommand_group_name: str) -> SubCommandGroup:
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
        if interaction.options:
            option = interaction.options[0]

            subcommand = self._unwrap_subcommand(option)
            if subcommand:
                return subcommand.parse_subcommand_interaction(option.options, interaction.resolved)

            subcommand_group = self._unwrap_subcommand_group(option)
            if subcommand_group:
                # Subcommand group guarantees that a nested subcommand option exists
                assert option.options is not None  # noqa: S101
                return subcommand_group.parse_interaction_group(option.options[0], interaction.resolved)

        responder = self.get_responder()
        return SlashCommandParsed(
            responder.callback,
            responder.parse_options(options=interaction.options, resolved=interaction.resolved),
        )

    def parse_autocomplete_interaction(self, autocomplete: hikari.AutocompleteInteraction) -> SlashCommandParsed:
        if autocomplete.options:
            option = autocomplete.options[0]

            subcommand = self._unwrap_subcommand(option)
            if subcommand:
                return subcommand.parse_subcommand_autocomplete(option.options)

            subcommand_group = self._unwrap_subcommand_group(option)
            if subcommand_group:
                # Subcommand group guarantees that a nested subcommand option exists
                assert option.options is not None  # noqa: S101
                return subcommand_group.parse_autocomplete_group(option.options[0])

        responder = self.get_responder()
        if responder.autocomplete:
            return responder.parse_autocomplete(autocomplete.options)

        msg = f'Slash command "{self.name}" does not have an autocomplete handler registered.'
        raise ValueError(msg)

    def build(self) -> hikari.impl.SlashCommandBuilder:
        options: list[hikari.CommandOption] = []
        if self._responder:
            options.extend(self._responder.option_map.values())
        else:
            for subcommand in self._subcommands.values():
                options.append(subcommand.build())

            for subcommand_group in self._subcommands_group.values():
                options.append(subcommand_group.build())

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
