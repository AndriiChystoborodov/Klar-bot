Issue #1 — Duplicate header row written to Google Sheets
Problem: Every time an expense was logged, the bot wrote a header row (Timestamp | Purchase Date | Item | Amount | Category) as a data row, creating duplicates at the top of the Expenses sheet.
Root cause: The append_row() call included the headers list in the write function, which was called on every expense submission.

Solution: Removed the header row from the write function. Headers are set up once manually in the sheet. The bot only writes data rows.

Lesson: Google Sheets headers should be set up once manually. The bot should never write them programmatically unless initializing a brand new sheet.

Issue #2 — Wrong column order (Account before Category)
Problem: The original sheet template had columns Timestamp | Purchase Date | Item | Amount | Category. When Account column was manually added between Amount and Category, the bot continued writing data in the old order — putting Account data into Category column and vice versa.

Root cause: The append_row() list in the code did not match the updated column order in the sheet.

Solution: Updated the append_row() call to match the new column order:
pythonsheet.append_row([timestamp, date, description, amount, account, category],
                 value_input_option='USER_ENTERED')

Lesson: Column order in code must always match the sheet exactly. When adding columns manually, always update the write function.

Issue #3 — Dates stored as text with apostrophe prefix
Problem: Dates written by the bot appeared with an apostrophe prefix ('30.04.2026) in Google Sheets, causing them to be stored as text rather than date values. This broke all SUMIFS formulas that compared dates.

Root cause: gspread's default value_input_option='RAW' stores strings as-is without date parsing. Google Sheets interpreted the date string as text and added the apostrophe to force text format.

Solution: Changed all append_row() and append_rows() calls to use value_input_option='USER_ENTERED', which tells Google Sheets to parse the value as if the user typed it — converting date strings to actual date values.
pythonsheet.append_row([...], value_input_option='USER_ENTERED')

Lesson: Always use USER_ENTERED when writing dates or numbers to Google Sheets via gspread. RAW is only for strings that should stay as strings.

Issue #4 — Voice transcription failing (OpenRouter 500 error)

Problem: Voice messages triggered a 500 Internal Server Error from OpenRouter when attempting to use Whisper transcription.

Root cause: OpenRouter's audio transcription endpoint is unstable and returned an HTML error page instead of JSON. The SDK then failed to parse the HTML as JSON, causing the cryptic error: No number after minus sign in JSON at position 1.

Solution: Switched from OpenRouter to Groq for voice transcription. Groq hosts Whisper natively, is free, and has a stable API:
pythonfrom groq import AsyncGroq

client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

result = await client.audio.transcriptions.create(
    model="whisper-large-v3",
    file=audio
)
Lesson: OpenRouter is good for text LLMs but unreliable for audio. Use provider-native APIs for specialized tasks like transcription.

Issue #5 — Date format inconsistency between bot and sheet formulas
Problem: SUMIFS formulas in Monthly/Weekly/Daily Overview sheets returned 0 or #N/A for new bot-written rows, even though the data was visually correct in the Expenses sheet.
Root cause: The bot wrote dates in DD.MM.YYYY format, but some rows were written in MM/DD/YYYY (American format) due to locale differences. The SUMIFS formulas expected a consistent format and couldn't match mixed formats.

Solution: Standardized date output in the bot to always use DD.MM.YYYY:
pythondate = datetime.strptime(expense["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
Added a parse_date() utility function that handles multiple formats when reading:
pythondef parse_date(date_str):
    for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y"]:
        try:
            return datetime.strptime(str(date_str), fmt).date()
        except:
            continue
    return None

Lesson: Always normalize dates to one format before writing. Never rely on locale-dependent formatting.

Issue #6 — KeyError: 'description' crashing the bot
Problem: Bot crashed with KeyError: 'description' when Claude's JSON response omitted the description field for some expense inputs.

Root cause: Claude occasionally returns partial JSON — if the input is ambiguous (e.g. just a number like "45"), it may not include all fields. The code used expense['description'] which throws KeyError if the key is missing.

Solution: Replaced all dictionary key access with .get() and default values:
pythondescription = expense.get('description', '')
amount = expense.get('amount', 0)
category = expense.get('category', 'Other')
date = expense.get('date', datetime.now().strftime('%Y-%m-%d'))
Also updated the Claude system prompt to always include all fields even if empty.

Lesson: Never trust LLM JSON output to always include all fields. Always use .get() with defaults.

Issue #7 — #REF! errors in Income formulas across Overview sheets
Problem: Income and Gross Savings columns showed #N/A and #REF! errors across Monthly, Weekly, Fortnightly, and Daily Overview sheets.
Root cause: When the Account column was added to the Income sheet, it shifted column positions. Existing SUMIFS formulas that referenced specific columns by letter became invalid — the column they pointed to no longer existed at that position.
Solution: Updated all SUMIFS formulas across all Overview sheets to reference the correct column (Income!$E$1:$E1048 for Income Amount). Used Find & Replace to fix #REF! references across all sheets.
Lesson: When adding columns to a referenced sheet, always check and update all dependent formulas in other sheets.
