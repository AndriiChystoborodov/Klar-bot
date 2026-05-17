import json
from datetime import datetime

from openai import OpenAI

from config import OPENROUTER_API_KEY, CATEGORIES
from services.security import check_api_limit

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

# OpenRouter model names for Claude
_HAIKU = "anthropic/claude-haiku-4-5"
_SONNET = "anthropic/claude-sonnet-4-5"

_PARSE_SYSTEM = f"""You are a personal finance assistant.
Analyze the user message and return ONLY valid JSON. No explanation, no markdown.

Today's date: {datetime.now().strftime("%Y-%m-%d")}

If the message contains one or more EXPENSES (money spent):
{{"intent": "expense", "expenses": [{{"amount": 4.50, "category": "Food & Drink", "description": "coffee", "date": "2026-04-30"}}]}}

If the message contains INCOME (money received, salary, payment, freelance, etc.):
{{"intent": "income", "incomes": [{{"amount": 2000.00, "source": "Workplace 1", "description": "April salary", "date": "2026-04-30"}}]}}

If the message is clearly a question, request for analysis, greeting, or contains words like "how much", "did I", "show me", "what", "why", "help":
{{"intent": "question"}}

Rules:
- CORRECTION → question: "sorry", "mistake", "actually", "it was", "should be", "wrong", "fix", "change", "update", "edit", "wait", "нет", "ошибка", "виправ" — these override everything else
- QUESTION clues: "how much", "did I", "show me", "what", "why", "help", "?"
- EXPENSE clues: a number + description/place/item with NO correction words ("63 to bern", "lunch 15", "paid 50 for taxi", "migros 23.40")
- If message has a number AND correction words → question
- If message has a number and no correction/question words → expense
- amounts must be positive numbers
- date defaults to today if not mentioned, format YYYY-MM-DD
- for expenses: category must be one of: {", ".join(CATEGORIES)}
- for income: source is who paid (e.g. employer name, "Freelance", "Client"), description is invoice/note
- support any language (English, German, Russian, Ukrainian)
- keywords hinting income: received, salary, payment, got paid, earned, invoice, freelance, зарплата, получил, дохід
- NEVER return anything except valid JSON
"""

_QA_SYSTEM = f"""You are Klar, a friendly personal finance assistant.
Today's date: {datetime.now().strftime("%Y-%m-%d")}
You have access to the user's expense history provided in the message.

Always return ONLY valid JSON, one of:

If answering any question, greeting, or conversation:
{{"action": "answer", "text": "your answer here"}}

If the user wants to correct/edit an expense:
{{"action": "edit", "match_date": "2026-05-08", "match_amount": 53.0, "match_description": "transport", "field": "Amount", "new_value": 60.0, "confirmation_text": "Change amount of 'transport' from 53.00 to 60.00 CHF?"}}

Rules:
- Be conversational and friendly — greetings, small talk, and general questions are all welcome
- If the user says "hello" or chats casually, respond warmly and briefly mention what you can help with
- For financial questions: be specific and use real numbers from the data
- For edits: identify the transaction using match_date (YYYY-MM-DD), match_amount, match_description from the data
- field can be: "Purchase Date", "Item", "Amount", "Category"
- new_value is the new value (string for date/text, number for amount)
- Match the user's language (English, German, Russian, Ukrainian, etc.)
- NEVER return anything except valid JSON
"""


def _guard() -> None:
    if not check_api_limit():
        raise RuntimeError("API rate limit reached. Please try again in a moment.")


def _chat(model: str, system: str, user: str, max_tokens: int) -> str:
    import logging
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    logging.getLogger(__name__).info(f"Claude raw response: {repr(raw)}")
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").strip()
        raw = raw.removesuffix("```").strip()
    return raw


def classify_and_parse(text: str) -> dict:
    _guard()
    raw = _chat(_HAIKU, _PARSE_SYSTEM, text, max_tokens=500)
    return json.loads(raw)


def parse_bank_csv(raw_csv: str) -> list:
    """Use Haiku to extract transactions from any bank CSV format.
    Returns a list of {date, amount, description, category}."""
    _guard()
    system = (
        f"You are a bank statement parser. Extract ALL transactions from the raw CSV text.\n"
        f"Return ONLY valid JSON array. Today: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"Format:\n"
        f'[{{"date": "2026-05-01", "amount": 45.50, "description": "Migros", "category": "Groceries"}}]\n\n'
        f"Rules:\n"
        f"- Only include EXPENSES (money going out, debits). Skip credits/income.\n"
        f"- amount must be positive\n"
        f"- date format: YYYY-MM-DD\n"
        f"- category must be one of: {', '.join(CATEGORIES)}\n"
        f"- description: merchant name or transaction note\n"
        f"- If date missing, use today\n"
        f"- NEVER return anything except a valid JSON array"
    )
    raw = _chat(_HAIKU, system, raw_csv, max_tokens=2000)
    result = json.loads(raw)
    return result if isinstance(result, list) else []


def parse_budget_input(text: str) -> dict:
    """Use Haiku to extract amount + category from natural language budget input.
    Returns {"amount": float|None, "category": str|None}."""
    _guard()
    system = (
        f"Extract budget information from the user message. Return ONLY valid JSON.\n\n"
        f"Categories: {', '.join(CATEGORIES)}\n\n"
        f"If the message contains an amount for a specific category (even with typos):\n"
        f'{{\"amount\": 500, \"category\": \"Transport\"}}\n\n'
        f"If only a total monthly budget:\n"
        f'{{\"amount\": 2000, \"category\": null}}\n\n'
        f"If no valid amount:\n"
        f'{{\"amount\": null, \"category\": null}}\n\n'
        f"Rules:\n"
        f"- Fix typos to match the closest category (e.g. 'Transprot' → 'Transport')\n"
        f"- amount must be a positive number\n"
        f"- category must be exactly one of the listed categories, or null\n"
        f"- NEVER return anything except valid JSON"
    )
    raw = _chat(_HAIKU, system, text, max_tokens=80)
    return json.loads(raw)


def answer_with_data(question: str, rows: list) -> dict:
    """Full conversational Q&A with complete sheet data. Returns {action, text} or {action, edit fields}."""
    _guard()
    # Limit to last 500 rows to stay within token budget
    if len(rows) > 500:
        rows = rows[-500:]
    raw = _chat(
        _SONNET,
        _QA_SYSTEM,
        f"My expenses:\n{json.dumps(rows)}\n\nQuestion: {question}",
        max_tokens=600,
    )
    return json.loads(raw)


def generate_monthly_report(summary: dict) -> str:
    _guard()
    return _chat(
        _SONNET,
        (
            "You are a personal finance advisor. "
            "Analyze the spending summary and provide:\n"
            "1. Top 2-3 spending patterns\n"
            "2. Exactly 3 concrete saving tips with specific CHF amounts\n"
            "3. One positive observation\n"
            "Be friendly, specific, and actionable. Max 200 words."
        ),
        json.dumps(summary),
        max_tokens=600,
    )
