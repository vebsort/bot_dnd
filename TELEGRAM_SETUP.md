# Запуск бота в Telegram и VK

## 1. Установить зависимости

```powershell
pip install -r requirements.txt
```

## 2. Получить данные для Telegram

1. Откройте Telegram и напишите `@BotFather`.
2. Выполните `/newbot`.
3. Задайте имя и username бота.
4. Скопируйте токен вида `1234567890:AA...`.

Для работы в группах добавьте бота в группу. В группе команды лучше писать со слэшем, например `/1d20`, `/помощь`, `/создать`, или с упоминанием `@username_бота`.

## 3. Данные, которые нужно ввести в файл

Скопируйте `config.example.json` в `config.json`:

```powershell
Copy-Item config.example.json config.json
```

Откройте `config.json` и вставьте свои значения:

```json
{
  "BOT_PLATFORM": "telegram",
  "TELEGRAM_BOT_TOKEN": "токен от BotFather",
  "TELEGRAM_BOT_USERNAME": "username_бота_без_@",
  "VK_TOKEN": "токен сообщества VK",
  "VK_GROUP_ID": "179538565"
}
```

`config.json` добавлен в `.gitignore`, чтобы токены случайно не попали в git.

Для запуска только Telegram достаточно заполнить:

```json
{
  "BOT_PLATFORM": "telegram",
  "TELEGRAM_BOT_TOKEN": "токен от BotFather",
  "TELEGRAM_BOT_USERNAME": "username_бота_без_@"
}
```

Для VK + Telegram:

```json
{
  "BOT_PLATFORM": "both",
  "TELEGRAM_BOT_TOKEN": "токен от BotFather",
  "TELEGRAM_BOT_USERNAME": "username_бота_без_@",
  "VK_TOKEN": "токен сообщества VK",
  "VK_GROUP_ID": "179538565"
}
```

После этого запуск:

```powershell
python dnd_bot.py
```

## 4. Альтернатива: переменные окружения

Обязательные для Telegram:

```powershell
$env:TELEGRAM_BOT_TOKEN="токен от BotFather"
$env:TELEGRAM_BOT_USERNAME="username_бота_без_@"
```

Обязательные для VK:

```powershell
$env:VK_TOKEN="токен сообщества VK"
$env:VK_GROUP_ID="id сообщества VK"
```

Выбор платформы:

```powershell
# только Telegram
$env:BOT_PLATFORM="telegram"

# только VK
$env:BOT_PLATFORM="vk"

# одновременно Telegram и VK
$env:BOT_PLATFORM="both"
```

## 5. Запуск через переменные окружения

Telegram:

```powershell
$env:BOT_PLATFORM="telegram"
$env:TELEGRAM_BOT_TOKEN="токен от BotFather"
$env:TELEGRAM_BOT_USERNAME="username_бота_без_@"
python dnd_bot.py
```

VK + Telegram одновременно:

```powershell
$env:BOT_PLATFORM="both"
$env:VK_TOKEN="токен сообщества VK"
$env:VK_GROUP_ID="179538565"
$env:TELEGRAM_BOT_TOKEN="токен от BotFather"
$env:TELEGRAM_BOT_USERNAME="username_бота_без_@"
python dnd_bot.py
```

## 6. Проверка

В личке Telegram напишите:

```text
начать
```

или:

```text
помощь
```

Если бот запущен в группе, используйте слэш:

```text
/помощь
/1d20
```
