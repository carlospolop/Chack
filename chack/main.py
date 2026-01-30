import asyncio
import logging
import os

from .config import load_config
from .discord_adapter import run_discord_bot
from .env_utils import export_env
from .telegram_adapter import TelegramBot


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("discord").setLevel(logging.WARNING)

def main() -> None:
    config_path = os.environ.get("CHACK_CONFIG", "./config/chack.yaml")
    config = load_config(config_path)
    setup_logging(config.logging.level)
    export_env(config, config_path)

    # Check which bots are enabled
    telegram_enabled = config.telegram.enabled
    discord_enabled = config.discord.enabled

    if not telegram_enabled and not discord_enabled:
        raise RuntimeError("No channels are enabled. Configure telegram.enabled=true or discord.enabled=true.")

    # If both are enabled, we need to run them concurrently
    if telegram_enabled and discord_enabled:
        async def run_both():
            telegram_task = asyncio.create_task(asyncio.to_thread(run_telegram))
            discord_task = asyncio.create_task(asyncio.to_thread(run_discord))
            await asyncio.gather(telegram_task, discord_task)
        
        def run_telegram():
            bot = TelegramBot(config)
            bot.run()
        
        def run_discord():
            run_discord_bot(config)
        
        asyncio.run(run_both())
    
    elif telegram_enabled:
        bot = TelegramBot(config)
        bot.run()
    
    elif discord_enabled:
        run_discord_bot(config)


if __name__ == "__main__":
    main()
