"""Dependency Injection (DI) example in Discordia.

Discordia features a first-class native DI system supporting:
1. Lifespan Scopes:
   - "singleton": the same instance is shared across the entire application runtime.
   - "scoped": instantiated once per interaction request.
   - "transient": a brand new instance is generated every time it is injected.
2. Generator functions with `yield` for automatic setup and teardown (ideal for DB sessions/pools).
3. Automatic injection of core objects (Bot...).
"""

from collections.abc import Generator
from typing import Annotated

import hikari

from discordia import Bot, inject

gateway_bot = hikari.GatewayBot("YOUR_TOKEN")
bot = Bot(gateway_bot)


# Defining Services and Resources #


# Example A: Simple configuration service registered as a Singleton
class AppConfig:
    def __init__(self) -> None:
        self.app_name = "My Discord Bot"
        self.version = "1.0.0"


# Example B: Session resource using a Generator (Setup -> Yield -> Teardown)
class DatabaseSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id


# Everything before `yield` runs before the command callback is executed.
# Everything after `yield` runs after the command finishes (cleanup/teardown).
def get_db_session() -> Generator[DatabaseSession, None, None]:
    print("[DI] Setup: opening database session...")
    session = DatabaseSession("session_token_998877")
    try:
        yield session
    finally:
        print("[DI] Teardown: closing database session and releasing resources!")


# Registering Dependencies in the Bot #

# Register config as a singleton
bot.di.add_dependency(AppConfig, scope="singleton")

# Register generator function in the 'scoped' scope (per-interaction lifecycle)
# dependencies are "scoped" by default
bot.di.add_dependency(get_db_session)


# Using Injected Dependencies in Commands #


# Simply annotate parameters with their corresponding types!
# Discordia inspects the signature and automatically resolves and injects them.
@bot.interactions.slash_command(description="Demonstrates dependency injection with a generator session")
async def query(interaction: hikari.CommandInteraction, config: AppConfig, db: DatabaseSession) -> None:
    msg = f"**Application:** {config.app_name} (v{config.version})\n**Active DB Session:** `{db.session_id}`"
    await interaction.create_initial_response(hikari.ResponseType.MESSAGE_CREATE, msg)


# You can also inject the dependency directly using "inject" + Annotated.
# This way, you don't need to register anything in the bot.
@bot.events.listen()
async def on_started(event: hikari.StartedEvent, config: Annotated[AppConfig, inject(AppConfig)]) -> None:
    print(f"{config.app_name} started in version {config.version}")


if __name__ == "__main__":
    bot.validate_setup()
    gateway_bot.run()
