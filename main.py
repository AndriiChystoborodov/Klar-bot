import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN
from handlers.callbacks import handle_callback
from handlers.commands import (
    handle_addaccount,
    handle_accounts,
    handle_banned,
    handle_budget,
    handle_help,
    handle_report,
    handle_setbudget,
    handle_setdefault,
    handle_start,
    handle_stats,
    handle_unban,
)
from handlers.message import handle_message
from services.database import init_db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("addaccount", handle_addaccount))
    app.add_handler(CommandHandler("accounts", handle_accounts))
    app.add_handler(CommandHandler("setdefault", handle_setdefault))
    app.add_handler(CommandHandler("report", handle_report))
    app.add_handler(CommandHandler("budget", handle_budget))
    app.add_handler(CommandHandler("setbudget", handle_setbudget))
    app.add_handler(CommandHandler("stats", handle_stats))
    app.add_handler(CommandHandler("banned", handle_banned))
    app.add_handler(CommandHandler("unban", handle_unban))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    logger.info("Klar bot starting (polling mode)...")
    app.run_polling(poll_interval=2)


if __name__ == "__main__":
    main()
