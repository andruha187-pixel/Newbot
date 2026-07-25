# Polymarket Strategy Research v3

Исследовательский бот для наблюдения за публичной активностью кошелька Polymarket.

## Что собирается

- все доступные сделки BUY и SELL;
- события Data API: TRADE, REDEEM, MERGE, SPLIT и другие;
- время сделки внутри пятиминутного рынка;
- задержка обнаружения сделки через Data API;
- публичные стаканы UP и DOWN;
- цены BTCUSDT и ETHUSDT через Binance WebSocket;
- изменение базового актива за 1, 5, 15 и 30 секунд;
- остаток позиции после BUY/SELL;
- PnL при победе UP и DOWN;
- реализованный PnL, когда победитель доступен;
- JSON, CSV и копия SQLite в ZIP.

## Важное ограничение

Бот видит публично исполненные сделки и публичную on-chain/Data API активность. Он не может увидеть
неисполненные лимитные заявки другого пользователя, потому что пользовательские ордера требуют
аутентификации владельца аккаунта.

## Render

Используй **Background Worker**, а не Web Service.

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
python bot.py
```

Переменные окружения:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TARGET_WALLET` — необязательно
- `TELEGRAM_POLLING_ENABLED=true`

Для команд Telegram используй отдельный токен. Один Telegram-бот не может одновременно работать
через `getUpdates` в двух сервисах — это вызывает ошибку 409 Conflict.

## Команды Telegram

- `/status`
- `/analyze`
- `/report`
- `/export`

## Замечание о прибыли

Точный PnL рассчитывается только по наблюдаемым BUY/SELL и доступному результату рынка.
Комиссии, скрытые вне наблюдаемого периода операции и неполная история API могут влиять на итог.
