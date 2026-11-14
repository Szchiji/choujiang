"""简单多语言支持"""

MESSAGES = {
    "zh": {
        "welcome": "🎯 欢迎使用 <b>LuckyDraw Cloud</b>！\n\n发送 /create 开始创建抽奖。",
        "help": "<b>📖 命令列表</b>\n/create /checkin /invite /my /me /buy /templates /leaderboard",
        "quota_ok": "配额充足",
        "quota_fail": "配额不足",
    },
    "en": {
        "welcome": "🎯 Welcome to <b>LuckyDraw Cloud</b>!\n\nSend /create to start.",
        "help": "<b>📖 Commands</b>\n/create /checkin /invite /my /me /buy /templates /leaderboard",
        "quota_ok": "Quota available",
        "quota_fail": "Insufficient quota",
    },
}


def t(lang: str, key: str) -> str:
    return MESSAGES.get(lang, MESSAGES["zh"]).get(key, key)
