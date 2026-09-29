import json
import os

SUBS_FILE = "subscriptions.json"


def load_subs():
    """Загружает подписки и дайджесты. Мигрирует старый формат."""
    if not os.path.exists(SUBS_FILE):
        return {"alerts": {}, "digests": []}
    try:
        with open(SUBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"alerts": {}, "digests": []}

    # Миграция со старого формата {"chat_id": [...]}
    if isinstance(data, dict) and "alerts" not in data:
        if all(k.isdigit() for k in data.keys()):
            return {"alerts": data, "digests": []}

    data.setdefault("alerts", {})
    data.setdefault("digests", [])
    return data


def save_subs(subs):
    try:
        with open(SUBS_FILE, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"Не удалось сохранить подписки: {e}")