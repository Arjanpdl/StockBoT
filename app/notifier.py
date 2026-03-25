import requests

class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()

    def send(self, message: str):
        r = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data={"chat_id": self.chat_id, "text": message},
            timeout=30,
        )
        if not r.ok:
            raise RuntimeError(f"Telegram send failed: {r.status_code} {r.text}")
