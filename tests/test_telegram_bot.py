"""
Teste 0: Verificar se o Bot do Telegram está funcionando.
Se você receber uma mensagem no Telegram, está tudo certo!
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def test_telegram():
    """Envia uma mensagem de teste via Telegram Bot API."""
    import aiohttp

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": "🟢 BabyGuard — Teste de conexão!\n\nSe você está lendo isso, o bot está funcionando perfeitamente!",
        "parse_mode": "HTML",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            if data["ok"]:
                print("✅ Mensagem enviada com sucesso!")
                print(f"   Message ID: {data['result']['message_id']}")
            else:
                print(f"❌ Erro: {data['description']}")


if __name__ == "__main__":
    asyncio.run(test_telegram())