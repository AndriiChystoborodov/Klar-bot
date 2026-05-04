import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")

CATEGORIES = [
    "Food & Drink",
    "Groceries",
    "Transport",
    "Travel",
    "Shopping",
    "Entertainment",
    "Subscriptions",
    "Health & Wellbeing",
    "Bills",
    "Business",
    "Gifts",
    "Other",
]

EXPENSES_TAB = "Expenses"
INCOME_TAB = "Income"
