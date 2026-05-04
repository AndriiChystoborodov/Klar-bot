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

If the message is a question about finances:
{{"intent": "question"}}

If unclear or unrelated:
{{"intent": "unclear"}}

Rules:
- amounts must be positive numbers
- date defaults to today if not mentioned, format YYYY-MM-DD
- for expenses: category must be one of: {", ".join(CATEGORIES)}
- for income: source is who paid (e.g. employer name, "Freelance", "Client"), description is invoice/note
- support any language (English, German, Russian, Ukrainian)
- keywords hinting income: received, salary, payment, got paid, earned, invoice, freelance, зарплата, получил, дохід
- NEVER return anything except valid JSON
"""

_QA_SYSTEM = f"""You are a personal finance assistant for Klar.
Today's date: {datetime.now().strftime("%Y-%m-%d")}
You have access to the user's complete expense history provided in the message.

Always return ONLY valid JSON, one of:

If answering a question:
{{"action": "answer", "text": "your answer here"}}

If the user wants to correct/edit an expense:
{{"action": "edit", "row_index": 45, "field": "amount", "new_value": 4.50, "confirmation_text": "Change amount of 'coffee' from 5.00 to 4.50 CHF?"}}

Rules:
- Be specific — use real numbers from the data
- For edits: row_index is 0-based index in the provided rows array
- field can be: "Purchase Date", "Item", "Amount", "Category"
- new_value is the new value (string for date/text, number for amount)
- Support any language in responses (match the user's language)
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
