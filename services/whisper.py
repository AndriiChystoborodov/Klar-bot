import os
import tempfile

from groq import Groq
from telegram import Voice

from config import GROQ_API_KEY

_client = Groq(api_key=GROQ_API_KEY)


async def transcribe(voice: Voice) -> str:
    file = await voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as audio:
            result = _client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio,
            )
        return result.text
    finally:
        os.unlink(tmp_path)
