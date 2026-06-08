import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.upload import VkUpload
import random
import re
import json
import os
import tempfile
import threading
import time
import requests
import dnd5e_data

import keyboards #импорт клавиатур
from dnd_character_generator import generate_character # Это ваш модуль для генерации персонажей
import character_sheet_image

# Настройки бота
def load_config():
    config_path = os.getenv('BOT_CONFIG', 'config.json')
    if not os.path.exists(config_path):
        return {}
    with open(config_path, 'r', encoding='utf-8') as config_file:
        return json.load(config_file)


CONFIG = load_config()


def get_setting(name, default=None):
    return os.getenv(name) or CONFIG.get(name) or default


GROUP_ID = get_setting('VK_GROUP_ID', '179538565')
TOKEN = get_setting('VK_TOKEN')
TELEGRAM_BOT_TOKEN = get_setting('TELEGRAM_BOT_TOKEN')
TELEGRAM_BOT_USERNAME = get_setting('TELEGRAM_BOT_USERNAME', '').lstrip('@').lower()
BOT_PLATFORM = get_setting('BOT_PLATFORM', 'vk').lower()

symbol = '/'

# Инициализация API выполняется при запуске нужного транспорта.
vk_session = None
longpoll = None
vk = None
vk_upload = None
current_platform = 'vk'
telegram_chat_id = None
telegram_message_id = None
telegram_last_reply_markup_by_chat = {}
transport_lock = threading.RLock()

# Состояния пользователей (для простой машины состояний)
user_states = {}
user_warnings = {}
# Последний бросок по user_id для переброса вдохновением (-вдох)
last_roll_by_user = {}


def get_photo_attachment(attachments):
    """Из вложений сообщения извлекает строку вложения фото для VK (photo{owner_id}_{id}_{access_key} или photo{owner_id}_{id}). Возвращает None, если фото нет."""
    if not attachments:
        return None
    for att in attachments:
        if att.get('type') == 'photo':
            ph = att.get('photo', {})
            if ph.get('url'):
                return f"url:{ph['url']}"
            oid = ph.get('owner_id')
            pid = ph.get('id')
            if oid is not None and pid is not None:
                acc = ph.get('access_key', '')
                if acc:
                    return f"photo{oid}_{pid}_{acc}"
                return f"photo{oid}_{pid}"
    return None


def get_photo_url_from_attachments(attachments):
    """Из вложений сообщения извлекает URL фото наибольшего размера (для сохранения и последующей вставки в лист)."""
    if not attachments:
        return None
    for att in attachments:
        if att.get('type') != 'photo':
            continue
        ph = att.get('photo', {})
        sizes = ph.get('sizes')
        if not sizes:
            for key in ('photo_2560', 'photo_1280', 'photo_807', 'photo_604', 'url'):
                u = ph.get(key)
                if u:
                    return u
            return None
        best = max(sizes, key=lambda s: (s.get('width', 0) or 0) * (s.get('height', 0) or 0))
        url = best.get('url')
        if url:
            return url
    return None


def download_character_photo(photo_attachment, image_url=None, vk_api_obj=None):
    """Скачивает фото во временный файл. Сначала пробует image_url (URL, сохранённый при загрузке), иначе — VK API photos.getById. Возвращает путь к файлу или None."""
    if photo_attachment and photo_attachment.startswith('url:'):
        image_url = image_url or photo_attachment[4:]
    if image_url:
        try:
            r = requests.get(image_url, timeout=10)
            r.raise_for_status()
            fd, path = tempfile.mkstemp(suffix='.jpg')
            os.write(fd, r.content)
            os.close(fd)
            return path
        except Exception:
            pass
    if not photo_attachment or not photo_attachment.startswith('photo'):
        return None
    parts = photo_attachment.replace('photo', '').split('_')
    if len(parts) < 2:
        return None
    try:
        owner_id, photo_id = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None
    api = vk_api_obj or vk
    try:
        resp = api.photos.getById(photos=f"{owner_id}_{photo_id}")
        if not resp or not isinstance(resp, list):
            return None
        photo = resp[0]
        url = None
        sizes = photo.get('sizes') or []
        if sizes:
            best = max(sizes, key=lambda s: s.get('width', 0) * s.get('height', 0))
            url = best.get('url')
        if not url:
            for key in ('photo_2560', 'photo_1280', 'photo_807', 'photo_604', 'url'):
                url = photo.get(key)
                if url:
                    break
        if not url:
            return None
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        fd, path = tempfile.mkstemp(suffix='.jpg')
        os.write(fd, r.content)
        os.close(fd)
        return path
    except Exception:
        return None


def character_image_for_send(character):
    """Attachment для send_message: локальный файл в Telegram, VK photo id в VK. Возвращает (attachment, temp_path)."""
    attachment = character.get('image') or None
    if not attachment:
        return None, None
    if current_platform == 'telegram':
        path = download_character_photo(attachment, image_url=character.get('image_url'))
        return path, path
    return attachment, None


#функция отправки сообщения (в зависимости от лички/беседы меняет параметры)
def send_message(message, keyboard=None, attachment=None, remove_keyboard=False, inline_keyboard=None, parse_mode=None):
    """Отправляет сообщение пользователю. attachment — строка вложения VK (например, photo123_456)."""
    if current_platform == 'telegram':
        send_telegram_message(
            message,
            keyboard=keyboard,
            attachment=attachment,
            remove_keyboard=remove_keyboard,
            inline_keyboard=inline_keyboard,
            parse_mode=parse_mode,
        )
        return

    if chat_id is not None:
        params = {
            'chat_id': message_id,
            'message': message,
            'random_id': random.randint(1, 10000)
        }
    else:
         params = {
            'user_id': message_id,
            'message': message,
            'random_id': random.randint(1, 10000)
         }
    vk_keyboard = inline_keyboard if inline_keyboard is not None else keyboard
    if vk_keyboard:
        params['keyboard'] = json.dumps(vk_keyboard)
    if attachment:
        params['attachment'] = attachment

    vk.messages.send(**params)


def telegram_api(method, **params):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is not set')
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    response = requests.post(url, json=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not payload.get('ok'):
        raise RuntimeError(payload)
    return payload['result']


def vk_keyboard_to_telegram_markup(keyboard):
    if not keyboard:
        return None
    rows = []
    for row in keyboard.get('buttons', []):
        labels = []
        for button in row:
            label = button.get('action', {}).get('label')
            if label:
                labels.append(label)
        if labels:
            rows.append(labels)
    if not rows:
        return None
    return {
        'keyboard': rows,
        'resize_keyboard': True,
        'one_time_keyboard': False,
        'is_persistent': True,
    }


def send_telegram_message(message, keyboard=None, attachment=None, remove_keyboard=False, inline_keyboard=None, parse_mode=None):
    global telegram_last_reply_markup_by_chat
    if inline_keyboard is not None:
        reply_markup = inline_keyboard
    elif remove_keyboard:
        reply_markup = {'remove_keyboard': True}
        telegram_last_reply_markup_by_chat.pop(telegram_chat_id, None)
    elif keyboard is not None:
        reply_markup = vk_keyboard_to_telegram_markup(keyboard)
        if reply_markup and telegram_chat_id is not None:
            telegram_last_reply_markup_by_chat[telegram_chat_id] = reply_markup
    else:
        reply_markup = telegram_last_reply_markup_by_chat.get(telegram_chat_id)

    params = {
        'chat_id': telegram_chat_id,
        'text': message,
    }
    if parse_mode:
        params['parse_mode'] = parse_mode
        params['disable_web_page_preview'] = True
    if reply_markup:
        params['reply_markup'] = reply_markup

    photo_path = attachment if attachment and os.path.exists(str(attachment)) else None
    if photo_path:
        with open(photo_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            data = {'chat_id': telegram_chat_id, 'caption': message}
            if parse_mode:
                data['parse_mode'] = parse_mode
            if reply_markup:
                data['reply_markup'] = json.dumps(reply_markup, ensure_ascii=False)
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            response = requests.post(url, data=data, files=files, timeout=60)
            response.raise_for_status()
        return

    return telegram_api('sendMessage', **params)


def get_telegram_file_url(file_id):
    file_info = telegram_api('getFile', file_id=file_id)
    file_path = file_info.get('file_path')
    if not file_path:
        return None
    return f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

#Вывод сообщения при выходе из других меню в главное
def main_menu_message():
    send_message("Главное меню: ", keyboards.main_keyboard)

#Выход из состояния
def exit_state(show_message = True):
    if user_id in user_states:
        del user_states[user_id]
    if show_message:
        main_menu_message()    

def error_exit_state(show_message = True):
    if user_id in user_states:
        del user_states[user_id]
    if show_message:
        send_message("Произошла ошибка при загрузке файла персонажей. Обратитесь к админу.")

#Создание клавиатуры для выбора персонажей (разное количество кнопок каждый раз)

def char_choice_keyboard_array_maker(): #создание массива кнопок для клавиатуры, зависимое от числа персонажей пользователя
    char_choice_keyboard_array = [] 

    characters = load_characters(user_id)

    keyboard_rows = ((len(characters) - 1) // 5) + 1

    len_to_go = len(characters)

    for y in range(keyboard_rows):
        char_choice_keyboard_array.append([])
        for i in range(len_to_go):
            if i < 5:
                char_choice_keyboard_array[y].append({
                    "action": {
                        "type": "text",
                        "payload": "{\"button\": \""f"{y+1}""\"}",
                        "label": f"{y*5 + i+1}"
                    },
                    "color": "primary"
            })
        len_to_go = len_to_go - 5
            
    char_choice_keyboard_array.append([])
    char_choice_keyboard_array[keyboard_rows].append({ #добавление кнопки назад на последнюю строку
                    "action": {
                        "type": "text",
                        "payload": "{\"button\": \"2\"}",
                        "label": "Назад"
                    },
                    "color": "secondary"
            })
    return char_choice_keyboard_array

def numbered_keyboard_array_maker(number, keyboard_columns = 5, additional_button_name = 'none', hasbackbutton = True): #создание массива кнопок для клавиатуры, зависимое от числа персонажей пользователя
    numbered_keyboard_array = [] 
    
    if number != 0:
        keyboard_rows = ((number - 1) // 5) + 1
        len_to_go = number
        for y in range(keyboard_rows):
            numbered_keyboard_array.append([])
            for i in range(keyboard_columns):
                if i < len_to_go:
                    numbered_keyboard_array[y].append({
                        "action": {
                            "type": "text",
                            "payload": "{\"button\": \""f"{y+1}""\"}",
                            "label": f"{y*5 + i+1}"
                        },
                        "color": "primary"
                })
            len_to_go = len_to_go - keyboard_columns
    else:
        keyboard_rows = 0

    if additional_button_name != 'none':
        numbered_keyboard_array.append([])
        numbered_keyboard_array[keyboard_rows].append({ #добавление кнопки на предпоследнюю строку
                        "action": {
                            "type": "text",
                            "payload": "{\"button\": \"2\"}",
                            "label": f"{additional_button_name}"
                        },
                        "color": "primary"
                })
    
    if hasbackbutton:
        numbered_keyboard_array.append([])
        numbered_keyboard_array[keyboard_rows].append({ #добавление кнопки назад на последнюю строку
                        "action": {
                            "type": "text",
                            "payload": "{\"button\": \"3\"}",
                            "label": "Назад"
                        },
                        "color": "secondary"
                })
    return numbered_keyboard_array

def array_to_text_color_array(array, color = "primary"):
    text_color_array = []
    for i in range(len(array)): # [["Название", "primary"],[]]
        text_color_array.append([array[i], color])

    return text_color_array 


def subrace_keyboard_array_maker(race, edition='2014'):
    # Редакция 2024: подрасы только у эльфа и гнома
    if edition == '2024':
        if race and race.lower() in dnd5e_data.race_to_subrace_2024:
            names = dnd5e_data.race_to_subrace_2024[race.lower()]
            text_color_array = [[n, 'primary'] for n in names]
            return keyboard_array_maker(text_color_array, 1, hasbackbutton=True)
        return keyboard_array_maker([], 1, hasbackbutton=True)
    if race == 'Дварф': #добавление условий со всеми расами
        text_color_array = [
            ['Горный дварф', 'primary'],
            ['Холмовой дварф', 'primary'],
        ]
    elif race == "Полурослик":
        text_color_array = [
            ['Крепкий полурослик', 'primary'],
            ['Легконогий полурослик', 'primary']
        ]
    # elif race == "Человек":
    #     text_color_array = [
    #         ['Сильф', 'primary'],
    #         ['Вальдор', 'primary']
    #     ]
    elif race == "Эльф":
        text_color_array = [
            ['Высший эльф', 'primary'],
            ['Лесной эльф', 'primary'],
            ['Дроу', 'primary']
        ]
    elif race == "Гном":
        text_color_array = [
            ['Лесной гном', 'primary'],
            ['Скальный гном', 'primary']
        ]
    # elif race == "Драконорожденный":
    #     text_color_array = [
    #         ['Американец', 'primary'],
    #         ['Кенийский житель', 'primary']
    #     ]
    # elif race == "Полуорк":
    #     text_color_array = [
    #         ['Американец', 'primary'],
    #         ['Кенийский житель', 'primary']
    #     ]
    # elif race == "Полуэльф":
    #     text_color_array = [
    #         ['Американец', 'primary'],
    #         ['Кенийский житель', 'primary']
    #     ]
    # elif race == "Тифлинг":
    #     text_color_array = [
    #         ['Американец', 'primary'],
    #         ['Кенийский житель', 'primary']
    #     ]
    return keyboard_array_maker(text_color_array, 1, hasbackbutton=True) #возвращение клавиатуры



def keyboard_array_maker(text_color_array, keyboard_columns = 5, hasbackbutton = False):
    keyboard_array = [] 

    len_to_go = len(text_color_array)

    keyboard_rows = ((len(text_color_array) - 1) // keyboard_columns) + 1

    for y in range(keyboard_rows):
        keyboard_array.append([])
        for i in range(len_to_go):
            if i < keyboard_columns:
                keyboard_array[y].append({
                    "action": {
                        "type": "text",
                        "payload": "{\"button\": \""f"{y+1}""\"}",
                        "label": f"{text_color_array[y*keyboard_columns + i][0]}"
                    },
                    "color": f"{text_color_array[y*keyboard_columns + i][1]}"
            })
        len_to_go = len_to_go - keyboard_columns

    if hasbackbutton:
        keyboard_array.append([])
        keyboard_array[keyboard_rows].append({ #добавление кнопки назад на последнюю строку
                        "action": {
                            "type": "text",
                            "payload": "{\"button\": \"2\"}",
                            "label": "Назад"
                        },
                        "color": "secondary"
                })
    return keyboard_array


def keyboard_maker(codeword_or_button_array, number=0, keyboard_columns = 5, additional_button_name='none', hasbackbutton = False, onetime= False): #возвращает готовую клавиатуру
    
    if codeword_or_button_array == 'chars_list':
        button_array = char_choice_keyboard_array_maker()
    elif codeword_or_button_array == 'subraces_list':
        edition = user_states[user_id].get('edition', '2014') if user_id in user_states else '2014'
        button_array = subrace_keyboard_array_maker(user_states[user_id]['character']['race'], edition)
    elif codeword_or_button_array == 'numbered_list': 
        button_array = numbered_keyboard_array_maker(number=number, additional_button_name=additional_button_name, hasbackbutton=hasbackbutton)
    else: 
        button_array = keyboard_array_maker(codeword_or_button_array, keyboard_columns, hasbackbutton)
    
    keyboard = {
            "one_time": onetime,
            "buttons": button_array
        }    
    return keyboard  

#Функции персонажа

def change_main_char(user_id, character_id):
    """меняет информацию об id основного персонажа у пользователя с заданным id"""
    filename = f'data/main_char_user_data.json'
    if not os.path.exists('data'):
        os.makedirs('data')
    
    try:
        main_char_user_data = {}
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                main_char_user_data = json.load(f)
        main_char_user_data[f'{user_id}'] = character_id
    except json.JSONDecodeError:
        print("Ошибка json")

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(main_char_user_data, f, ensure_ascii=False, indent=2)

def get_main_char_id(user_id): #-1 = error
    filename = f'data/main_char_user_data.json'
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                main_char_user_data = json.load(f)
            main_char_id = main_char_user_data[f'{user_id}']
        else:
            main_char_id = -1
    except json.JSONDecodeError:
        print("Ошибка json")
    except KeyError:
        main_char_id = -1
    return main_char_id

def get_user_edition(user_id):
    """Возвращает редакцию правил для пользователя: '2014' или '2024'. По умолчанию 2014."""
    filename = 'data/user_edition.json'
    if not os.path.exists('data'):
        os.makedirs('data')
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get(str(user_id), '2014')
    except (json.JSONDecodeError, TypeError):
        pass
    return '2014'

def set_user_edition(user_id, edition):
    """Сохраняет выбор редакции (2014 или 2024) для пользователя."""
    filename = 'data/user_edition.json'
    if not os.path.exists('data'):
        os.makedirs('data')
    data = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, TypeError):
            pass
    data[str(user_id)] = edition
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_character(user_id, character): #добавляет нового персонажа в json файл пользователя 
    """Сохраняет персонажа в файл"""
    filename = f'characters/{user_id}.json'
    if not os.path.exists('characters'):
        os.makedirs('characters')
    
    try:
        characters = []
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                characters = json.load(f)
    except json.JSONDecodeError:
        print("Ошибка json")
    character['id'] = len(characters) + 1

    characters.append(character)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(characters, f, ensure_ascii=False, indent=2)

def write_characters(user_id, characters, set_new_ids=False): #Перезаписывает json файл пользователя  
    if set_new_ids == True:
        for i in range(len(characters)): #id rewrite
            char = characters[i]
            char['id'] = i + 1
            characters[i] = char
            print(char)

    filename = f'characters/{user_id}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(characters, f, ensure_ascii=False, indent=2)    

def load_characters(user_id): #загрузить json 
    """Загружает персонажей пользователя"""
    try:
        filename = f'characters/{user_id}.json'
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
    except json.JSONDecodeError:
        print("Ошибка json")

    return []

def load_main_character(user_id):
    characters = load_characters(user_id)
    main_char = characters[get_main_char_id(user_id) - 1]
    return main_char

# --- Напарники (компаньоны) ---
COMPANIONS_FILENAME = lambda uid: f'companions/{uid}.json'
RESERVED_NICKNAMES = frozenset(dnd5e_data.code_word_list + [
    'напарник', 'нап', 'напар', 'помощь', 'пом', 'создать', 'я', 'лист', 'дом', 'привет', 'начать',
    'справка', 'справ', 'спр', 'снар', 'ос', 'до', 'ко', 'закл', 'деньги', 'мон', 'навыки',
    'мои', 'персонажи', 'создать персонажа', 'помощ',
    'уд', 'удалить', 'исп'  # раздельные команды напарника: нап уд кличка, кличка исп лов
])
COMPANION_STAT_SUFFIXES = ('ини', 'пз', 'макс', 'мпз', 'кб', 'атак', 'атк', 'уров', 'ур', 'уровень',
    'лов', 'сил', 'вын', 'инт', 'муд', 'хар', 'акр', 'атл', 'вни', 'выж', 'дре', 'зап',
    'ист', 'лрк', 'ловрук', 'маг', 'мед', 'обм', 'при', 'про', 'рас', 'рел', 'скр', 'убе')
# Ловкость рук: лрк и ловрук хранятся под ключом 'лр'
COMPANION_SKILL_STORAGE_KEY = lambda suf: 'лр' if suf in ('лрк', 'ловрук') else suf
# Испытания напарника: [кличка] исп <характеристика> (раздельные слова)
# Поддерживаем сокращения и полные слова; храним модификаторы в канонических ключах.
COMPANION_TRIAL_CODE_MAP = {
    'сил': 'сил', 'сила': 'сил',
    'лов': 'лов', 'лвк': 'лов', 'ловкость': 'лов',
    'вын': 'вын', 'выносливость': 'вын',
    'инт': 'инт', 'интеллект': 'инт',
    'муд': 'муд', 'мдр': 'муд', 'мудр': 'муд', 'мудрость': 'муд',
    'хар': 'хар', 'харизма': 'хар',
}
COMPANION_TRIAL_NAMES = {
    'лов': 'Испытание Ловкости',
    'сил': 'Испытание Силы',
    'вын': 'Испытание Выносливости',
    'инт': 'Испытание Интеллекта',
    'муд': 'Испытание Мудрости',
    'хар': 'Испытание Харизмы',
}
# Полные названия навыков/характеристик для напарника (как в get_mod)
COMPANION_SKILL_DISPLAY = {
    'сил': 'Сила', 'сила': 'Сила', 'лов': 'Ловкость', 'лвк': 'Ловкость', 'ловкость': 'Ловкость',
    'вын': 'Выносливость', 'выносливость': 'Выносливость', 'инт': 'Интеллект', 'интеллект': 'Интеллект',
    'муд': 'Мудрость', 'мдр': 'Мудрость', 'мудр': 'Мудрость', 'мудрость': 'Мудрость',
    'хар': 'Харизма', 'харизма': 'Харизма',
    'акр': 'Акробатика', 'акробатика': 'Акробатика', 'атл': 'Атлетика', 'атлетика': 'Атлетика',
    'вни': 'Внимание', 'внимание': 'Внимание', 'выж': 'Выживание', 'выживание': 'Выживание',
    'дре': 'Дрессировка', 'дрессировка': 'Дрессировка', 'зап': 'Запугивание', 'запугивание': 'Запугивание',
    'исп': 'Исполнение', 'исполнение': 'Исполнение', 'ист': 'История', 'история': 'История',
    'лрк': 'Ловкость рук', 'ловрук': 'Ловкость рук', 'ловкость рук': 'Ловкость рук', 'маг': 'Магия', 'магия': 'Магия',
    'мед': 'Медицина', 'медицина': 'Медицина', 'обм': 'Обман', 'обман': 'Обман',
    'при': 'Природа', 'природа': 'Природа', 'про': 'Проницательность', 'проницательность': 'Проницательность',
    'рас': 'Расследование', 'расследование': 'Расследование', 'рел': 'Религия', 'религия': 'Религия',
    'скр': 'Скрытность', 'скрытность': 'Скрытность', 'убе': 'Убеждение', 'убеждение': 'Убеждение',
}
# Полные названия проверок для бросков напарника (как в get_mod / roll)
COMPANION_CHECK_NAMES = {
    'сил': 'Проверка Силы', 'сила': 'Проверка Силы', 'лов': 'Проверка Ловкости', 'лвк': 'Проверка Ловкости', 'ловкость': 'Проверка Ловкости',
    'вын': 'Проверка Выносливости', 'выносливость': 'Проверка Выносливости', 'инт': 'Проверка Интеллекта', 'интеллект': 'Проверка Интеллекта',
    'муд': 'Проверка Мудрости', 'мдр': 'Проверка Мудрости', 'мудр': 'Проверка Мудрости', 'мудрость': 'Проверка Мудрости',
    'хар': 'Проверка Харизмы', 'харизма': 'Проверка Харизмы',
    'акр': 'Проверка Ловкости (Акробатика)', 'атл': 'Проверка Силы (Атлетика)', 'вни': 'Проверка Мудрости (Внимание)',
    'выж': 'Проверка Мудрости (Выживание)', 'дре': 'Проверка Мудрости (Дрессировка)', 'зап': 'Проверка Харизмы (Запугивание)',
    'исп': 'Проверка Харизмы (Исполнение)', 'ист': 'Проверка Истории (Интеллект)', 'лрк': 'Проверка Ловкости (Ловкость рук)', 'ловрук': 'Проверка Ловкости (Ловкость рук)',
    'маг': 'Проверка Интеллекта (Магия)', 'мед': 'Проверка Мудрости (Медицина)', 'обм': 'Проверка Харизмы (Обман)',
    'при': 'Проверка Интеллекта (Природа)', 'про': 'Проверка Мудрости (Проницательность)', 'рас': 'Проверка Интеллекта (Расследование)',
    'рел': 'Проверка Интеллекта (Религия)', 'скр': 'Проверка Ловкости (Скрытность)', 'убе': 'Проверка Харизмы (Убеждение)',
}

def format_companion_roll(comp_name, check_name, roll_val, mod):
    """Формат броска напарника как у основного персонажа: Имя, Проверка +N: d20 = total 🎲 [roll] + N"""
    total = roll_val + mod
    if mod >= 0:
        header = f"{check_name} +{mod}: \n"
        tail = f"] + {mod}"
    else:
        header = f"{check_name} {mod}: \n"
        tail = f"] - {abs(mod)}"
    return f"{comp_name},\n{header}d20 = {total} 🎲\n\n[{roll_val}{tail}"

def load_companions(user_id):
    """Загружает напарников пользователя: {[кличка]: {name, hp, max_hp, ac, initiative, attack_bonus, level, skills}}"""
    try:
        path = COMPANIONS_FILENAME(user_id)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {}

def save_companions(user_id, companions):
    path = COMPANIONS_FILENAME(user_id)
    dirname = os.path.dirname(path)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(companions, f, ensure_ascii=False, indent=2)

def companion_default(name):
    return {
        'name': name,
        'hp': 10,
        'max_hp': 10,
        'ac': 10,
        'initiative': 0,
        'attack_bonus': 0,
        'level': 1,
        'skills': {}
    }

def companion_card_text(companion):
    """Текст карточки напарника: ПЗ, КБ, Навыки, бонус атаки, уровень, инициатива."""
    c = companion
    init_str = f"+{c['initiative']}" if c['initiative'] >= 0 else str(c['initiative'])
    atk_str = f"+{c['attack_bonus']}" if c['attack_bonus'] >= 0 else str(c['attack_bonus'])
    skills_str = ", ".join(
        f"{COMPANION_SKILL_DISPLAY.get(k, k)} +{v}" if v >= 0 else f"{COMPANION_SKILL_DISPLAY.get(k, k)} {v}"
        for k, v in sorted(c.get('skills', {}).items())
    )
    if not skills_str:
        skills_str = "—"
    return (
        f"Напарник: {c['name']}\n"
        f"ПЗ: {c['hp']}/{c['max_hp']} | КБ: {c['ac']} | Инициатива: {init_str}\n"
        f"Бонус атаки: {atk_str} | Уровень: {c['level']}\n"
        f"Навыки: {skills_str}"
    )

def companions_list_text(companions):
    """Краткий список напарников: имя, [кличка], ПЗ, КБ."""
    if not companions:
        return (
            "У вас пока нет напарников.\n\n"
            "Как добавить напарника:\n"
            "• Напишите: нап <имя> [кличка]\n"
            "• Пример: нап Римус рим\n"
            "• Тогда карточка будет по команде /рим\n\n"
            "Команды: нап, напарник, напар — список или добавление."
        )
    lines = ["Напарники:"]
    for nick, c in companions.items():
        lines.append(f"  • {c['name']} ({nick}) — ПЗ {c['hp']}/{c['max_hp']}, КБ {c['ac']}\n    /{nick}")
    return "\n".join(lines)

def delete_character(user_id, character_id, set_new_ids = True): #удаляет персонажа по номеру в списке
    """Удаляет персонажа пользователя"""
    characters = load_characters(user_id)

    if character_id > len(characters) or character_id < 0:
        send_message("Персонажа с таким номером не существует.")
        return
    elif character_id < get_main_char_id(user_id):
        change_main_char(user_id, get_main_char_id(user_id)-1)



    characters.pop(character_id - 1) # удаление персонажа
    write_characters(user_id, characters, set_new_ids) # перезапись данных

def show_characters(characters): #показать список персонажей (добавляет текст "выберите персонажа" в конце в случае нахождения в состоянии)
    """Показывает список персонажей пользователя"""
    if not characters:
        send_message("У вас пока нет созданных персонажей.", keyboards.main_keyboard)
        if user_id in user_states: 
            exit_state(show_message=False)
    elif characters == ['error']:
        exit_state()
    else:
        message = ""
        main_id = get_main_char_id(user_id)
        if main_id == -1 or main_id > len(characters):
            message += "Не выбран основной персонаж. Автоматическое определение 1-го персонажа основным.\n\n"
            change_main_char(user_id, 1)
            main_id = 1 

        message += "Ваши персонажи:\n\n"
        for i, char in enumerate(characters, 1):
            if i == main_id:
                message += (
                f"{i}. {char['name']} (основной) \n{char['race']}-{char['class'].lower()} {char['level']} уровня\n"
                f"ПЗ: {char['max_hit_points']}, КБ: {char['armor_class']}\n\n"
                )
            else:
                message += (
                    f"{i}. {char['name']} \n{char['race']}-{char['class'].lower()} {char['level']} уровня\n"
                    f"ПЗ: {char['max_hit_points']}, КБ: {char['armor_class']}\n\n"
                )
        if user_states[user_id]['state'] == 'manage_character':
            message += "Выберите персонажа: "
        send_message(message, keyboard=keyboard_maker('chars_list'))



def stat_format(stat):
    stat_mod = dnd5e_data.calc_mod(stat)
    if stat > 9:
        stat_str = f"{stat}" + f" (+{stat_mod})"
    else:
        stat_str = f"{stat}" + f" ({stat_mod})"
    return stat_str

STAT_ABBR = ['СИЛ', 'ЛОВ', 'ВЫН', 'ИНТ', 'МДР', 'ХАР']
STAT_KEYS = ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma']
ABILITY_ABBR = {
    'Сила': 'СИЛ', 'Ловкость': 'ЛОВ', 'Выносливость': 'ВЫН',
    'Интеллект': 'ИНТ', 'Мудрость': 'МДР', 'Харизма': 'ХАР',
}

def stat_compact(stat):
    mod = dnd5e_data.calc_mod(stat)
    if mod >= 0:
        return f"{stat}(+{mod})"
    return f"{stat}({mod})"

def format_gp_total(money_dict):
    gp = money_sum(money_dict)
    if gp == int(gp):
        return f"{int(gp)} зм"
    return f"{gp} зм"

def skill_label(skill_name, show_commands=False):
    if not show_commands:
        return skill_name
    aliases = dnd5e_data.skill_command_aliases.get(skill_name)
    if aliases:
        return f"{skill_name} ({', '.join(aliases)})"
    return skill_name

def get_prof_string(character, profkey = 'prof_mult_dict', is_saving_throw = False, horizontal_format = False, show_all = False, show_commands = False):
    keys_list = list(character[profkey].keys())
    text = ''
    if show_all == True: # определяет, будет ли показываться все или только навыки с умением (или экспертизой)
        x = -1
    else:
        x = 0

    for i in keys_list:
        if character[profkey][i] > x:
            if is_saving_throw:
                mod = get_mod(f'{i.lower()}', character) + character['prof_saves_dict'][f'{i}'] * character['proficiency_bonus']
            else:
                mod = get_mod(f'{i.lower()}', character)
            label = skill_label(i, show_commands=show_commands and not is_saving_throw)
            if mod >= 0:
                text += f'{label} +{mod}, '
            else:
                text += f'{label} {mod}, '
        if horizontal_format == True:
            text = text[:-2] + "\n"
    if horizontal_format == False:
        text = text[:-2]
    return text

def show_all_skills(character, horizontal_format=True, show_all=True):
    message = get_prof_string(character, horizontal_format=True, show_all=True, show_commands=True)
    send_message(message)

def show_spell_slots(character, horizontal_format=True, show_all=True):
    try: 
        slots_arr = character['spell_slots']
    except KeyError:
        character['spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        character['current_spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        slots_arr = character['spell_slots']
    message='---Максимум ячеек заклинаний---\n\n'
    for i in range(9):
        message+=f"{i+1}-круг: {slots_arr[i+1]}\n"
    send_message(message)
    
def show_current_spell_slots(character):
    try: 
        curr_slots_arr = character['current_spell_slots']
    except KeyError:
        character['spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        character['current_spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        curr_slots_arr = character['current_spell_slots']
    max_slots_arr = character['spell_slots']
    message = '---Ячейки заклинаний---\n\n'
    message1=''
    message2=''
    for i in range(9):
        if max_slots_arr[i+1] !=0:
            message1+=f"{i+1}-круг: {curr_slots_arr[i+1]} ({max_slots_arr[i+1]})\n"
    if message1 == '':
        message2 = 'У вас нет ячеек заклинаний.'
    message += message1 + message2
    send_message(message)



    
def change_param(character, param, value, characters='none'):
    if characters == 'none':
        characters = load_characters(user_id)
    character[param] = value
    replace_char(character, characters)

def money_sum(money_dict):
    return round(money_dict['пм']*10 + money_dict['зм'] + money_dict['эм'] / 2 + money_dict['см'] /10 + money_dict['мм']/100, 2)

# Типы монет (нижний регистр для хранения); в 2024 при отображении — верхний (ЗМ, ПМ и т.д.)
COIN_TYPES = ['пм', 'зм', 'эм', 'см', 'мм']
WEIGHT_PATTERN = re.compile(r'(\d+)\s*(фунтов|фунт\.?|фунта|унций|унц\.?|унции|унц)\b', re.I)
COST_IN_PARENS = re.compile(r'\(\s*(\d+)\s*(пм|зм|эм|см|мм)\s*\)', re.I)
COST_PLAIN = re.compile(r'(\d+)\s*(пм|зм|эм|см|мм)\b', re.I)


def _format_coin(coin_type, edition='2014'):
    """Для редакции 2024 возвращает тип монеты в верхнем регистре (ЗМ, ПМ и т.д.)."""
    if edition == '2024':
        return coin_type.upper()
    return coin_type


def _format_item_cost(cost_dict, edition='2014'):
    """Форматирует стоимость предмета из словаря {тип: количество}."""
    if not cost_dict:
        return ''
    parts = []
    for ct in COIN_TYPES:
        if cost_dict.get(ct):
            parts.append(f"{cost_dict[ct]} {_format_coin(ct, edition)}")
    return ', '.join(parts)


def parse_equipment_bulk(text):
    """
    Парсит строку с перечислением предметов через запятую.
    Возвращает список dict: name, amount, cost (dict), weight_str.
    Пример: "5 Кинжал, рубин 5 фунтов (50 зм), ложка 1 фунт" -> [...]
    """
    results = []
    for segment in text.split(','):
        s = segment.strip()
        if not s:
            continue
        cost_list = []
        # Стоимость в скобках: (50 зм), (50 ЗМ)
        for m in COST_IN_PARENS.finditer(s):
            cost_list.append((int(m.group(1)), m.group(2).lower()))
        s = COST_IN_PARENS.sub('', s).strip()
        # Стоимость без скобок: 14 пм, 14зм
        for m in COST_PLAIN.finditer(s):
            cost_list.append((int(m.group(1)), m.group(2).lower()))
        s = COST_PLAIN.sub('', s).strip()
        # Вес: 5 фунтов, 1 фунт, 2 унц
        weight_str = ''
        weight_m = WEIGHT_PATTERN.search(s)
        if weight_m:
            weight_str = weight_m.group(0).strip()
            s = s.replace(weight_m.group(0), '', 1).strip()
        s = re.sub(r'\s+', ' ', s).strip()
        parts = s.split()
        amount = 1
        if parts and parts[-1].isdigit():
            amount = int(parts[-1])
            parts = parts[:-1]
        if parts and parts[0].isdigit():
            amount = int(parts[0])
            parts = parts[1:]
        name = ' '.join(parts).strip()
        if not name:
            continue
        cost_dict = {}
        for am, ct in cost_list:
            cost_dict[ct] = cost_dict.get(ct, 0) + am
        results.append({'name': name, 'amount': amount, 'cost': cost_dict, 'weight_str': weight_str})
    return results


def _item_cost_dict(item):
    """Возвращает стоимость предмета как dict (для сравнения). Вес не учитывается."""
    if item.get('cost'):
        return dict(item['cost'])
    if item.get('value') or item.get('valuetype'):
        return {item.get('valuetype', 'зм'): item.get('value', 0)}
    return {}


def delete_equipment_bulk(character, parsed_items):
    """
    Удаляет перечисленные предметы. Совпадение по названию и стоимости (вес не проверяется).
    Если стоимость не совпадает — предмет не удаляется.
    Возвращает (deleted_count, errors_list).
    """
    equipment_list = character['equipment']
    deleted_count = 0
    errors = []
    for it in parsed_items:
        name = it['name']
        amount = it['amount']
        cost = it.get('cost') or {}
        # Нормализуем: только ключи из COIN_TYPES, убираем нули
        cost = {k: v for k, v in cost.items() if k in COIN_TYPES and v}
        found = False
        for i in range(len(equipment_list) - 1, -1, -1):
            eq = equipment_list[i]
            if eq['name'].lower() != name.lower():
                continue
            eq_cost = _item_cost_dict(eq)
            eq_cost = {k: v for k, v in eq_cost.items() if k in COIN_TYPES and v}
            if eq_cost != cost:
                errors.append(f"{name}: не совпадает стоимость (не удалён)")
                found = True
                break
            # Совпадают название и стоимость — уменьшаем количество или удаляем
            cur_amount = eq.get('amount', 1)
            if amount > cur_amount:
                errors.append(f"{name}: нет столько (есть {cur_amount})")
                found = True
                break
            if amount >= cur_amount:
                equipment_list.pop(i)
                deleted_count += cur_amount
            else:
                eq['amount'] = cur_amount - amount
                deleted_count += amount
            found = True
            break
        if not found:
            errors.append(f"{name}: не найден")
    return deleted_count, errors


def delete_equipment_by_name_all(character, names):
    """
    Удаляет все предметы с указанными названиями (любая стоимость, весь стак).
    names — список строк. Возвращает (суммарное количество удалённых, список не найденных).
    """
    equipment_list = character['equipment']
    deleted_count = 0
    not_found = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        name_lower = name.lower()
        found_any = False
        for i in range(len(equipment_list) - 1, -1, -1):
            if equipment_list[i]['name'].lower() == name_lower:
                deleted_count += equipment_list[i].get('amount', 1)
                equipment_list.pop(i)
                found_any = True
        if not found_any:
            not_found.append(f"{name}: не найден")
    return deleted_count, not_found


def create_item(character, name, desc='', amount=1, value=0, valuetype='зм', weight=0, itemtype='none', damage='none', damagetype='none', delete=False, cost=None, weight_str=''):
    """cost — опциональный dict вида {'зм': 50, 'пм': 14}. weight_str — строка вида '5 фунтов' или '2 унц'."""
    equipment_list = character['equipment']
    if cost is None and (value or valuetype):
        cost = {valuetype: value} if value else {}
    if cost is None:
        cost = {}
    if delete == True:
        amount = amount * -1
    if len(equipment_list) > 0:
        for i in range(len(equipment_list)):
            if name.lower() == equipment_list[i]['name'].lower():
                if equipment_list[i]['amount'] + amount < 0:
                    send_message("У вас нет такого количества этих предметов. Введите число поменьше.")
                    return -1
                equipment_list[i]['amount'] += amount
                if equipment_list[i]['amount'] < 1:
                    delete_item(character, equipment_list[i]['id'])
                return 1
    if amount < 0:
        send_message("У вас нет такого предмета, невозможно удалить.")
        return -1
    item = {
        'id': len(equipment_list) + 1,
        'name': name,
        'desc': desc,
        'amount': amount,
        'value': value,
        'valuetype': valuetype,
        'weight': weight,
        'itemtype': itemtype,
        'damage': damage,
        'damagetype': damagetype,
    }
    if cost:
        item['cost'] = cost
    if weight_str:
        item['weight_str'] = weight_str
    equipment_list.append(item)
    return 1


def delete_item(character, item_id):
    equipment_list = character['equipment']
    for i in range(len(equipment_list)):
        if equipment_list[i]['id'] == item_id:
            equipment_list.remove(equipment_list[i])
            return
        
def delete_spell(character, spell_id):
    spell_list = character['known_spells']
    for i in range(len(spell_list)):
        if spell_list[i]['id'] == spell_id:
            spell_list.remove(spell_list[i])
            return

def create_spell(character, name, lvl, desc='', range=0, casttime='', duration=0, components='none', school='', damage='none', damagetype='none'):
    spell_list = character['known_spells']
    spell_list.append({
        'id': len(spell_list) + 1,
        'name': name,
        'lvl': lvl,
        'desc': desc,
        'range': range,
        'casttime': casttime,
        'duration': duration,
        'components': components,
        'damage': damage,
        'damagetype': damagetype,     
    })

def _item_line(item, item_count, edition='2014'):
    """Одна строка списка предмета: номер. название (кол-во) — стоимость, вес."""
    name = item['name']
    amount = item.get('amount', 1)
    cost_dict = item.get('cost')
    if not cost_dict and (item.get('value') or item.get('valuetype')):
        cost_dict = {item.get('valuetype', 'зм'): item.get('value', 0)}
    weight_str = item.get('weight_str', '')
    cost_s = _format_item_cost(cost_dict, edition) if cost_dict else ''
    line = f"{item_count}. {name}"
    if amount > 1:
        line += f" ({amount})"
    extra = []
    if cost_s:
        extra.append(cost_s)
    if weight_str:
        extra.append(weight_str)
    if extra:
        line += " - " + ", ".join(extra)
    return line + "\n"


def show_equipment(character, show_keyboard=True):
    equipment_list = character['equipment']
    money_dict = character['money']
    edition = character.get('edition', '2014')
    message = '---Экипировка---\n'
    message += f"Всего монет в золоте: {money_sum(money_dict)} зм\n\n"

    message += '---Предметы---\n'
    item_count = 0

    for i in range(len(equipment_list)):
        if equipment_list[i]['itemtype'] == 'оружие':
            item_count += 1
            message += _item_line(equipment_list[i], item_count, edition)
            equipment_list[i]['id'] = item_count
    if item_count > 0:
        message += "\n"

    for i in range(len(equipment_list)):
        if equipment_list[i]['itemtype'] == 'броня':
            item_count += 1
            message += _item_line(equipment_list[i], item_count, edition)
            equipment_list[i]['id'] = item_count
    if item_count > 0:
        message += "\n"

    for i in range(len(equipment_list)):
        if equipment_list[i]['itemtype'] == 'магия':
            item_count += 1
            message += _item_line(equipment_list[i], item_count, edition)
            equipment_list[i]['id'] = item_count
    if item_count > 0:
        message += "\n"

    for i in range(len(equipment_list)):
        if equipment_list[i]['itemtype'] == 'none':
            item_count += 1
            message += _item_line(equipment_list[i], item_count, edition)
            equipment_list[i]['id'] = item_count

    if show_keyboard == True:
        message += "\nВведите номер предмета:"
        send_message(message, keyboard_maker([["Монеты", "primary"],["Новый предмет", "primary"],["Удаление предметов", "secondary"]], keyboard_columns=2, hasbackbutton=True))
    else:
        send_message(message)

DND5E_CLUB_SPELLS_URL = "https://dnd5e.club/spells"


def _eng_name_to_spell_slug(eng):
    """Преобразует английское название заклинания в slug dnd5e.club (например, Tasha's → tasha-s)."""
    slug = eng.lower().strip()
    slug = re.sub(r"'s\b", "-s", slug)
    slug = slug.replace("'", "")
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')


def _extract_bracketed_eng_name(spellname):
    start = spellname.find('[')
    end = spellname.find(']')
    if start == -1 or end == -1 or end <= start:
        return None
    eng = spellname[start + 1:end].strip()
    return eng or None


def get_dnd5e_spell_link(spellname):
    """Если в названии заклинания есть [англ. название], возвращает ссылку dnd5e.club/spells/slug. Иначе None."""
    eng = _extract_bracketed_eng_name(spellname)
    if not eng:
        return None
    return f"{DND5E_CLUB_SPELLS_URL}/{_eng_name_to_spell_slug(eng)}"


def _is_eng_spell_query(query):
    """Запрос похож на английское название заклинания (латиница, пробелы, апостроф)."""
    q = query.strip()
    if not q:
        return False
    return bool(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9\s'\-]*", q))


def find_dnd5e_spell_link(query):
    """Ищет заклинание на dnd5e.club по запросу (рус/англ) через GraphQL API."""
    query = query.strip()
    if not query:
        return None
    try:
        resp = requests.post(
            'https://dnd5e.club/graphql',
            json={
                'query': 'query($text: String!) { findSpells(text: $text) { id title } }',
                'variables': {'text': query},
            },
            timeout=5,
        )
        resp.raise_for_status()
        spells = resp.json().get('data', {}).get('findSpells') or []
        if spells:
            return f"{DND5E_CLUB_SPELLS_URL}/{spells[0]['id']}"
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    # GraphQL findSpells ищет по русским названиям — для английских строим slug напрямую
    eng_query = _extract_bracketed_eng_name(query) or query
    if _is_eng_spell_query(eng_query):
        slug = _eng_name_to_spell_slug(eng_query)
        if slug:
            return f"{DND5E_CLUB_SPELLS_URL}/{slug}"
    return None


def resolve_spell_link(spellname):
    """Возвращает ссылку на заклинание на dnd5e.club (по [англ.] или поиску по русскому названию)."""
    link = get_dnd5e_spell_link(spellname)
    if link:
        return link
    if ' [' in spellname:
        search_name = spellname.split(' [')[0].strip()
    else:
        search_name = spellname.strip()
    if search_name and len(search_name) > 1 and search_name[0].isdigit() and search_name[1:2].isspace():
        search_name = search_name[2:].strip()
    return find_dnd5e_spell_link(search_name) or DND5E_CLUB_SPELLS_URL


def get_dndsort_spell_link(spellname):
    """Обратная совместимость: ссылка на заклинание на dnd5e.club."""
    return get_dnd5e_spell_link(spellname)


DND5E_CLUB_BASE_URL = "https://dnd5e.club"
_dnd5e_handbook_cache = None

DND5E_HANDBOOK_INDEX_QUERY = """
query {
  monsters { id title originalTitle alternativeTitles }
  items { id title originalTitle alternativeTitles }
  classes { id title originalTitle }
  feats { id title originalTitle alternativeTitles }
  features { id title originalTitle alternativeTitles }
  glossaryItems { id title originalTitle alternativeTitles }
  species { id title originalTitle }
  origins { id title originalTitle alternativeTitles }
  spells { id title originalTitle alternativeTitles }
}
"""

# graphql_key -> (url_path, русское название раздела)
DND5E_HANDBOOK_CATEGORIES = (
    ('spells', 'spells', 'Заклинание'),
    ('monsters', 'monsters', 'Чудовище'),
    ('items', 'items', 'Предмет'),
    ('classes', 'classes', 'Класс'),
    ('feats', 'feats', 'Черта'),
    ('features', 'feats', 'Особенность'),
    ('species', 'specie', 'Вид'),
    ('origins', 'feats', 'Предыстория'),
    ('glossaryItems', 'glossary', 'Глоссарий'),
)


def _normalize_search_text(text):
    if not text:
        return ''
    text = str(text).lower().replace('ё', 'е')
    text = re.sub(r'[^a-zа-я0-9\s\-]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _item_search_blob(item):
    parts = [
        item.get('title', ''),
        item.get('originalTitle', ''),
        item.get('id', '').replace('-', ' '),
    ]
    alts = item.get('alternativeTitles') or []
    if isinstance(alts, list):
        parts.extend(alts)
    return _normalize_search_text(' '.join(p for p in parts if p))


def _score_handbook_item(item, query_norm, query_tokens):
    blob = _item_search_blob(item)
    if not blob or not query_norm:
        return 0
    title_norm = _normalize_search_text(item.get('title', ''))
    orig_norm = _normalize_search_text(item.get('originalTitle', ''))
    id_norm = _normalize_search_text(item.get('id', '').replace('-', ' '))
    score = 0
    if query_norm in (title_norm, orig_norm, id_norm):
        score = 100
    elif title_norm.startswith(query_norm) or orig_norm.startswith(query_norm):
        score = max(score, 85)
    elif id_norm.replace(' ', '-') == query_norm.replace(' ', '-'):
        score = max(score, 80)
    elif query_norm in title_norm or query_norm in orig_norm or query_norm in blob:
        score = max(score, 70)
    if query_tokens and all(t in blob for t in query_tokens):
        score = max(score, 55)
    for token in query_tokens:
        if token in title_norm:
            score += 25
        elif token in orig_norm:
            score += 20
        elif token in id_norm:
            score += 15
        elif token in blob:
            score += 8
    return score


def get_dnd5e_handbook_index(force=False):
    """Возвращает кэш индекса справочника. Обновляется при первом поиске или по команде «обновить поиск»."""
    global _dnd5e_handbook_cache
    if not force and _dnd5e_handbook_cache is not None:
        return _dnd5e_handbook_cache
    try:
        resp = requests.post(
            f'{DND5E_CLUB_BASE_URL}/graphql',
            json={'query': DND5E_HANDBOOK_INDEX_QUERY},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get('data') or {}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return _dnd5e_handbook_cache or []
    index = []
    for graphql_key, url_path, type_label in DND5E_HANDBOOK_CATEGORIES:
        for item in data.get(graphql_key) or []:
            if not item.get('id'):
                continue
            index.append({
                'id': item['id'],
                'title': item.get('title') or item['id'],
                'originalTitle': item.get('originalTitle') or '',
                'alternativeTitles': item.get('alternativeTitles') or [],
                'url_path': url_path,
                'type_label': type_label,
            })
    _dnd5e_handbook_cache = index
    return index


def refresh_dnd5e_handbook_index():
    """Принудительно перезагружает индекс с dnd5e.club. Возвращает (index, had_cache, prev_count)."""
    had_cache = _dnd5e_handbook_cache is not None
    prev_count = len(_dnd5e_handbook_cache) if had_cache else 0
    return get_dnd5e_handbook_index(force=True), had_cache, prev_count


def send_dnd5e_handbook_refresh_message(index, had_cache, prev_count):
    if not index:
        send_message('Не удалось обновить индекс поиска. Попробуйте позже.')
    elif not had_cache:
        send_message(f'Индекс поиска загружен: {len(index)} записей.')
    else:
        send_message(f'Индекс поиска обновлён: {len(index)} записей (было {prev_count}).')


def dnd5e_handbook_item_url(item):
    return f"{DND5E_CLUB_BASE_URL}/{item['url_path']}/{item['id']}"


def _escape_telegram_html(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _vk_link_text(text):
    return str(text).replace('|', ' ').replace('[', '(').replace(']', ')')


def format_dnd5e_search_results_message(query, results):
    lines = [f'Поиск: «{query}»', '']
    for i, r in enumerate(results, 1):
        type_label = r['type_label']
        title = r['title']
        url = r['url']
        if current_platform == 'telegram':
            lines.append(
                f"{i}. [{_escape_telegram_html(type_label)}] "
                f"<a href=\"{url}\">{_escape_telegram_html(title)}</a>"
            )
        else:
            lines.append(f"{i}. [{type_label}] [{url}|{_vk_link_text(title)}]")
    return '\n'.join(lines)


def search_dnd5e_handbook(query, limit=5):
    query_norm = _normalize_search_text(query)
    if not query_norm:
        return []
    query_tokens = [t for t in query_norm.split() if t]
    scored = []
    for item in get_dnd5e_handbook_index():
        score = _score_handbook_item(item, query_norm, query_tokens)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: (-x[0], x[1]['title']))
    results = []
    for _, item in scored[:limit]:
        results.append({
            'title': item['title'],
            'type_label': item['type_label'],
            'url': dnd5e_handbook_item_url(item),
        })
    return results


def start_dnd5e_handbook_search(user_id, query):
    try:
        results = search_dnd5e_handbook(query, limit=5)
    except Exception as e:
        print('search_dnd5e_handbook error:', e)
        send_message('Не удалось выполнить поиск на dnd5e.club. Попробуйте позже.')
        return
    if not results:
        send_message(f'По запросу «{query}» ничего не найдено в справочнике dnd5e.club.')
        return
    message = format_dnd5e_search_results_message(query, results)
    if current_platform == 'telegram':
        send_message(message, parse_mode='HTML')
    else:
        send_message(message)


def show_all_spells(character, show_keyboard=True, ttg_msg=True):
    spell_list = character['known_spells']
    try: 
        curr_slots_arr = character['current_spell_slots']
    except KeyError:
        character['spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        character['current_spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        curr_slots_arr = character['current_spell_slots']
    max_slots_arr = character['spell_slots']
    
    message = ''
    message += f"---Заклинания---\n" \
    f"Характеристика: {get_spell_stat(character)}\n" \
    f"Бонус атаки: {get_mod(get_spell_stat(character).lower(),character) + character['proficiency_bonus']}\n" \
    f"CЛ испытаний: {8 + get_mod(get_spell_stat(character).lower(),character) + character['proficiency_bonus']}\n\n"

    item_count = 0
    spells_left = len(spell_list)
    
    message += '---Фокусы---\n'
    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 0:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if spells_left > 0:
        message += f"\n---1 круг--- {curr_slots_arr[1]} ({max_slots_arr[1]})\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 1:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count   
    if spells_left > 0:
        message += f"\n---2 круг--- {curr_slots_arr[2]} ({max_slots_arr[2]})\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 2:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if spells_left > 0:
            message += f"\n---3 круг--- {curr_slots_arr[3]} ({max_slots_arr[3]})\n"
    
    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 3:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if spells_left > 0:
            message += f"---4 круг--- {curr_slots_arr[4]} ({max_slots_arr[4]})\n"
    
    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 4:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if spells_left > 0:
            message += f"---5 круг--- {curr_slots_arr[5]} ({max_slots_arr[5]})\n"        

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 5:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if spells_left > 0:
            message += f"---6 круг--- {curr_slots_arr[6]} ({max_slots_arr[6]})\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 6:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
            
    if spells_left > 0:
            message += f"---7 круг--- {curr_slots_arr[7]} ({max_slots_arr[7]})\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 7:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
            
    if spells_left > 0:
            message += f"---8 круг--- {curr_slots_arr[8]} ({max_slots_arr[8]})\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 8:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
            
    if spells_left > 0:
            message += f"---9 круг--- {curr_slots_arr[9]} ({max_slots_arr[9]})\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 9:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if ttg_msg:
        message += "\nВведите номер заклинания, чтобы получить ссылку на dnd5e.club:" # ["Список (не доступно)", "primary"],
    if show_keyboard == True:
        change_param(character, 'known_spells', spell_list)
        send_message(message, keyboard_maker([["Добавить новые", "primary"],["Удаление заклинаний", "secondary"]], keyboard_columns=1, hasbackbutton=True))
    else:
        send_message(message)
    
def show_prepared_spells(character, show_keyboard=True):

            
    message += "\nВведите номер заклинания:" # ["Список (не доступно)", "primary"],
    send_message(message, keyboard_maker([["Добавить новые", "primary"],["Удаление заклинаний", "secondary"]], keyboard_columns=1, hasbackbutton=True))
    

def show_features(char, rewrite = True):
    feature_list = char['proficiencies']
    
    message = ''

    item_count = 0
    feature_left = len(feature_list)
    if feature_left == 0:
        message = 'У вас нет особенностей.'
        send_message(message)
        return -1
    
    
    message += '---Основные---\n'
    for i in range(len(feature_list)):
        if feature_list[i]['type'] == 'main':
            item_count += 1
            feature_left -= 1
            message += f"{item_count}. {feature_list[i]['name']}\n"
            feature_list[i]['id'] = item_count
    if feature_left > 0:
        message += f"\n---Классовые---\n"

    for i in range(len(feature_list)):
        if feature_list[i]['type'] == 'class':
            item_count += 1
            feature_left -= 1
            message += f"{item_count}. {feature_list[i]['name']}\n"
            feature_list[i]['id'] = item_count   
    if feature_left > 0:
        message += f"\n---Расовые---\n"

    for i in range(len(feature_list)):
        if feature_list[i]['type'] == 'race':
            item_count += 1
            feature_left -= 1
            message += f"{item_count}. {feature_list[i]['name']}\n"
            feature_list[i]['id'] = item_count   
    if feature_left > 0:
        message += f"\n---Происхождения---\n"

    for i in range(len(feature_list)):
        if feature_list[i]['type'] == 'background':
            item_count += 1
            feature_left -= 1
            message += f"{item_count}. {feature_list[i]['name']}\n"
            feature_list[i]['id'] = item_count

    if rewrite:
        change_param(char, 'proficiencies', feature_list)
    send_message(message)


def show_desc_feature(char, id):
    feature = ''
    for i in range(len(char['proficiencies'])):
        if char['proficiencies'][i]['id'] == id:
            feature = char['proficiencies'][i]
            break
    if feature == '':
        send_message("Выберите правельную особенность (если у вас они есть).")
        return

    message = ''
    message += f"---{feature['name']}---\n"
    message += f"{feature['desc']}"
    send_message(message)

def create_feature(char, name, desc, type):
    feature_list = char['proficiencies']
    feature_list.append({
        'id': len(feature_list) + 1,
        'name': name,
        'desc': desc,
        'type': type,   
    })
    replace_char(char, load_characters(user_id))

def delete_feature(char, id):
    feature_list = char['proficiencies']
    for i in range(len(feature_list)):
        if feature_list[i]['id'] == id:
            feature_list.remove(feature_list[i])
            replace_char(char, load_characters(user_id))
            return

def money_message(character):
    money_dict = character['money']

    message = f"Платина: {money_dict['пм']}\n" \
            f"Золото: {money_dict['зм']}\n" \
            f"Электрум: {money_dict['эм']}\n" \
            f"Серебро: {money_dict['см']}\n" \
            f"Медь: {money_dict['мм']}\n\n" \
            f"Всего в золоте: {money_sum(money_dict)} зм\n\n"
    
    return message



def replace_char(character, characters):
    """берет персонажа и заменяет его в списке персонжей, потом записывает все в файл пользователя"""
    if character['name'] == characters[character['id'] - 1]['name']:
        characters[character['id'] - 1] = character
        write_characters(user_id, characters)
    else:
        send_message('Ошибка. Обратитесь к админу')


# игровые функции

def get_mod(skill_name, character, get_name = False):
    #основные характеристики
    if skill_name in ['сил','сила']:
        mod = dnd5e_data.calc_mod(character['stats']['strength'])
        name = 'Проверка Силы'
    elif skill_name in ['лвк','лов','ловкость']:
        mod = dnd5e_data.calc_mod(character['stats']['dexterity'])
        name = 'Проверка Ловкости'
    elif skill_name in ['вын','выносливость']:
        mod = dnd5e_data.calc_mod(character['stats']['constitution'])
        name = 'Проверка Выносливости'
    elif skill_name in ['инт','интеллект']:
        mod = dnd5e_data.calc_mod(character['stats']['intelligence'])
        name = 'Проверка Интеллекта'
    elif skill_name in ['мдр','муд','мудр','мудрость']:
        mod = dnd5e_data.calc_mod(character['stats']['wisdom'])
        name = 'Проверка Мудрости'
    elif skill_name in ['хар','харизма']:
        mod = dnd5e_data.calc_mod(character['stats']['charisma'])
        name = 'Проверка Харизмы'
    
    #навыки
    elif skill_name in ['акр','акробатика']:
        mod = dnd5e_data.calc_mod(character['stats']['dexterity']) + character['prof_mult_dict']['Акробатика'] * character['proficiency_bonus']
        name = 'Проверка Ловкости (Акробатика)'
    elif skill_name in ['атл','атлетика']:
        mod = dnd5e_data.calc_mod(character['stats']['strength']) + character['prof_mult_dict']['Атлетика'] * character['proficiency_bonus']
        name = 'Проверка Силы (Атлетика)'
    elif skill_name in ['вни','внимание']:
        mod = dnd5e_data.calc_mod(character['stats']['wisdom']) + character['prof_mult_dict']['Внимание'] * character['proficiency_bonus']
        name = 'Проверка Мудрости (Внимание)'
    elif skill_name in ['выж','выживание']:
        mod = dnd5e_data.calc_mod(character['stats']['wisdom']) + character['prof_mult_dict']['Выживание'] * character['proficiency_bonus']
        name = 'Проверка Мудрости (Выживание)'
    elif skill_name in ['дре','дрессировка']:
        mod = dnd5e_data.calc_mod(character['stats']['wisdom']) + character['prof_mult_dict']['Дрессировка'] * character['proficiency_bonus']
        name = 'Проверка Мудрости (Дрессировка)'
    elif skill_name in ['зап','запугивание']:
        mod = dnd5e_data.calc_mod(character['stats']['charisma']) + character['prof_mult_dict']['Запугивание'] * character['proficiency_bonus']
        name = 'Проверка Харизмы (Запугивание)'
    elif skill_name in ['исп','исполнение']:
        mod = dnd5e_data.calc_mod(character['stats']['charisma']) + character['prof_mult_dict']['Исполнение'] * character['proficiency_bonus']
        name = 'Проверка Харизмы (Исполнение)'
    elif skill_name in ['ист','история']:
        mod = dnd5e_data.calc_mod(character['stats']['intelligence']) + character['prof_mult_dict']['История'] * character['proficiency_bonus']
        name = 'Проверка Истории (Интеллект)'
    elif skill_name in ['ловрук', 'лрк', 'ловкость рук']:
        mod = dnd5e_data.calc_mod(character['stats']['dexterity']) + character['prof_mult_dict']['Ловкость рук'] * character['proficiency_bonus']
        name = 'Проверка Ловкости (Ловкость рук)'
    elif skill_name in ['маг','магия']:
        mod = dnd5e_data.calc_mod(character['stats']['intelligence']) + character['prof_mult_dict']['Магия'] * character['proficiency_bonus']
        name = 'Проверка Интеллекта (Магия)'
    elif skill_name in ['мед','медицина']:
        mod = dnd5e_data.calc_mod(character['stats']['wisdom']) + character['prof_mult_dict']['Медицина'] * character['proficiency_bonus']
        name = 'Проверка Мудрости (Медицина)'
    elif skill_name in ['обм','обман']:
        mod = dnd5e_data.calc_mod(character['stats']['charisma']) + character['prof_mult_dict']['Обман'] * character['proficiency_bonus']
        name = 'Проверка Харизмы (Обман)'
    elif skill_name in ['при','природа']:
        mod = dnd5e_data.calc_mod(character['stats']['intelligence']) + character['prof_mult_dict']['Природа'] * character['proficiency_bonus']
        name = 'Проверка Интеллекта (Природа)'
    elif skill_name in ['про','проницательность']:
        mod = dnd5e_data.calc_mod(character['stats']['wisdom']) + character['prof_mult_dict']['Проницательность'] * character['proficiency_bonus']
        name = 'Проверка Мудрости (Проницательность)'
    elif skill_name in ['рас','рассл','расследование']:
        mod = dnd5e_data.calc_mod(character['stats']['intelligence']) + character['prof_mult_dict']['Расследование'] * character['proficiency_bonus']
        name = 'Проверка Интеллекта (Расследование)'
    elif skill_name in ['рел','религия']:
        mod = dnd5e_data.calc_mod(character['stats']['intelligence']) + character['prof_mult_dict']['Религия'] * character['proficiency_bonus']
        name = 'Проверка Интеллекта (Религия)'
    elif skill_name in ['скр','скрытность']:
        mod = dnd5e_data.calc_mod(character['stats']['dexterity']) + character['prof_mult_dict']['Скрытность'] * character['proficiency_bonus']
        name = 'Проверка Ловкости (Скрытность)'
    elif skill_name in ['убе','убеж','убеждение']:
        mod = dnd5e_data.calc_mod(character['stats']['charisma']) + character['prof_mult_dict']['Убеждение'] * character['proficiency_bonus']
        name = 'Проверка Харизмы (Убеждение)'
    
    #спасброски
    elif skill_name in ['исил','испсил','испытание силы']:
        mod = dnd5e_data.calc_mod(character['stats']['strength']) + character['prof_saves_dict']['Сила'] * character['proficiency_bonus']
        name = 'Испытание Силы'
    elif skill_name in ['илвк','илов','исплвк','исплов','испытание ловкости']:
        mod = dnd5e_data.calc_mod(character['stats']['dexterity']) + character['prof_saves_dict']['Ловкость'] * character['proficiency_bonus']
        name = 'Испытание Ловкости'
    elif skill_name in ['ивын','испвын','испытание выносливости']:
        mod = dnd5e_data.calc_mod(character['stats']['constitution']) + character['prof_saves_dict']['Выносливость'] * character['proficiency_bonus']
        name = 'Испытание Выносливости'
    elif skill_name in ['иинт','испинт','испытание интеллекта']:
        mod = dnd5e_data.calc_mod(character['stats']['intelligence']) + character['prof_saves_dict']['Интеллект'] * character['proficiency_bonus']
        name = 'Испытание Интеллекта'
    elif skill_name in ['имдр','имуд','испмдр','испмуд','испытание мудрости']:
        mod = dnd5e_data.calc_mod(character['stats']['wisdom']) + character['prof_saves_dict']['Мудрость'] * character['proficiency_bonus']
        name = 'Испытание Мудрости'
    elif skill_name in ['ихар','испхар','испытание харизмы']:
        mod = dnd5e_data.calc_mod(character['stats']['charisma']) + character['prof_saves_dict']['Харизма'] * character['proficiency_bonus']
        name = 'Испытание Харизмы'


    elif skill_name in ['ини','иниц','инициатива']:
        mod = character['initiative']
        name = 'Определение Инициативы!'
    elif skill_name in ['затака','атаказ','зтк','атака заклинанием',"заклатака"]:
        mod = get_mod(get_spell_stat(character).lower(),character) + character['proficiency_bonus']
        name = 'Атака заклинанием!'
    
    if get_name == False:
        return mod
    else: 
        return {'mod': mod, 'check_name': name}

def roll(character='none', amount = 1, die = 20, skill_name = 'none', custom_mod = 0, has_message=False, adv = '', user_id=None):
    if amount < 1:
        send_message("Введите правильное число костей.")
        return
    if amount > 500:
        send_message("Слишком большое число костей.")
        return 
    if die <1:
        send_message("Введите верную кость")
        return 
    if die > 10000:
        send_message("Слишком большое значение кости.")
        return 

    comment = ''
    if adv == 'пом':
        amount = 2
        comment = ' с помехой'
    elif adv == 'пре':
        amount = 2
        comment = ' с преимуществом'

    roll_result = 0
    if amount == 1:
        roll_message= f"d{die} = "
    else:
        roll_message= f"{amount}d{die} = "

    mod = 0
    roll_history_arr = []
    roll_history = f"\n\n["
    for i in range(amount):
        current_roll = random.randint(1, die)
        roll_result += current_roll
        roll_history_arr.append(current_roll)
        if has_message:
            # При бросках больше 1 (не пре/пом) — эмодзи рядом с 20 и 1; при одном кубике эмодзи только в тексте в конце
            if die == 20 and amount > 1 and adv not in ('пре', 'пом') and (current_roll == 20 or current_roll == 1):
                roll_history += f"{current_roll}🎯+" if current_roll == 20 else f"{current_roll}💀+"
            else:
                roll_history += f"{current_roll}+"
    
    if skill_name != 'none':
        mod_and_name = get_mod(skill_name, character, get_name=True)
        mod = mod_and_name['mod']
        roll_result += mod_and_name['mod'] + custom_mod
        if mod >= 0:
            roll_message = mod_and_name['check_name'] + f" +{mod}: \n" + roll_message
        else:
            roll_message = mod_and_name['check_name'] + f" {mod}: \n" + roll_message
    else:
        roll_result += mod + custom_mod

    if adv == 'пре' and character !='none':
        roll_result = max(roll_history_arr) + mod_and_name['mod'] + custom_mod
    if adv == 'пом' and character !='none':
        roll_result = min(roll_history_arr) + mod_and_name['mod'] + custom_mod
    elif adv == 'пре' and character =='none':
        roll_result = max(roll_history_arr) + custom_mod
    elif adv == 'пом' and character =='none':
        roll_result = min(roll_history_arr) + custom_mod

    roll_history = roll_history[:-1]
    
    if mod+custom_mod > 0:
        roll_message += f"{roll_result} 🎲" + comment + roll_history + f"] + {mod+custom_mod}"
    elif mod+custom_mod < 0:
        roll_message += f"{roll_result} 🎲" + comment + roll_history + f"] - {abs(mod+custom_mod)}"
    else:
        roll_message += f"{roll_result} 🎲" + comment + roll_history + f"]"
    
    # Критическое попадание/промах только для d20: при одном кубике или пре/пом — текст с эмодзи в конце (в списке эмодзи не дублируем)
    if die == 20 and roll_history_arr and (amount == 1 or adv in ('пре', 'пом')):
        if adv == 'пре':
            kept_roll = max(roll_history_arr)
        elif adv == 'пом':
            kept_roll = min(roll_history_arr)
        else:
            kept_roll = roll_history_arr[0]
        if kept_roll == 20:
            roll_message += " 🎯 Критическое попадание!"
        elif kept_roll == 1:
            roll_message += " 💀 Критический промах!"
    
    if character != 'none':
        roll_message = f"{character['name']},\n"+ roll_message
    if has_message and user_id is not None:
        last_roll_by_user[user_id] = {
            'character': character,
            'amount': amount,
            'die': die,
            'skill_name': skill_name,
            'custom_mod': custom_mod,
            'adv': adv,
        }
    if has_message:
        send_message(roll_message)
    return roll_result

def roll_initiative_with_companions(user_id):
    """Бросок инициативы: основной персонаж + все напарники, один вывод с именами и результатами."""
    results = []
    try:
        characters = load_characters(user_id)
        main_char = characters[get_main_char_id(user_id) - 1]
    except (IndexError, TypeError):
        main_char = None
    companions = load_companions(user_id)
    if main_char is not None:
        roll_val = random.randint(1, 20)
        mod = main_char['initiative']
        total = roll_val + mod
        results.append((total, main_char['name'], roll_val, mod))
    for nick, comp in companions.items():
        roll_val = random.randint(1, 20)
        mod = comp['initiative']
        total = roll_val + mod
        results.append((total, comp['name'], roll_val, mod))
    if not results:
        send_message("Нет персонажа или напарников для броска инициативы.")
        return
    results.sort(key=lambda x: -x[0])
    lines = ["Инициатива:"]
    for total, name, roll_val, mod in results:
        if mod >= 0:
            roll_mod = f"({roll_val}+{mod})"
        else:
            roll_mod = f"({roll_val}{mod})"
        lines.append(f"  {name}: d20 {roll_mod} = {total}")
    send_message("\n".join(lines))

def add_money(character, value, type, show_message=False):
    if len(type) == 1:
        type += 'м'
    if value < 0:
        if character['money'][f'{type}'] < abs(value):
            send_message(f"Недостаточно монет (У вас: {character['money'][f'{type}']} {type}).")
            return 'error'
    character['money'][f'{type}'] += value
    replace_char(character, load_characters(user_id))
    if show_message:
        send_message(f"Теперь у вас {character['money'][f'{type}']} {type}.")

def get_spell_stat(character):
    classs = character['class'].lower()
    if classs in dnd5e_data.class_spell_stat.keys():
        return dnd5e_data.class_spell_stat[f'{classs}']

def char_sheet_message(character): #
    header = f"{character['name']} · {character['subrace']} {character['class']} {character['level']}"
    if not character.get('milestone'):
        header += f" · {character['xp']} XP"

    inspiration = '✨' if character['inspiration'] else 'нет'
    line_meta = f"БМ +{character['proficiency_bonus']} · {inspiration} · {format_gp_total(character['money'])}"

    hp_line = f"❤️ {character['hit_points']}/{character['max_hit_points']}"
    if character['temp_hit_points']:
        hp_line += f" (+{character['temp_hit_points']})"
    hp_line += f" · КЗ {character['hit_dice_count']}/{character['hit_dice_max']}"

    initiative = f"+{character['initiative']}" if character['initiative'] >= 0 else str(character['initiative'])
    combat_line = f"🛡️ {character['armor_class']} · ⚡ {initiative} · {character['speed']} фт"

    lines = [header, line_meta, '', hp_line, combat_line]

    spell_stat = get_spell_stat(character)
    if spell_stat:
        spell_mod = get_mod(spell_stat.lower(), character) + character['proficiency_bonus']
        atk_str = f"+{spell_mod}" if spell_mod >= 0 else str(spell_mod)
        spell_dc = 8 + get_mod(spell_stat.lower(), character) + character['proficiency_bonus']
        stat_abbr = ABILITY_ABBR.get(spell_stat, spell_stat[:3].upper())
        lines += ['', f"🔮 {stat_abbr} · атк {atk_str} · СЛ {spell_dc}"]

    stats = character['stats']
    stat_vals = [stat_compact(stats[key]) for key in STAT_KEYS]
    lines += [
        '',
        f"{STAT_ABBR[0]} {stat_vals[0]}  {STAT_ABBR[1]} {stat_vals[1]}  {STAT_ABBR[2]} {stat_vals[2]}",
        f"{STAT_ABBR[3]} {stat_vals[3]}  {STAT_ABBR[4]} {stat_vals[4]}  {STAT_ABBR[5]} {stat_vals[5]}",
        '',
        f"Исп: {get_prof_string(character, 'prof_saves_dict', is_saving_throw=True)}",
        f"Нав: {get_prof_string(character, 'prof_mult_dict')}",
    ]
    return '\n'.join(lines)

#Генерация основных статических клавиатур

def get_race_keyboard(edition='2014'):
    """Клавиатура выбора расы в зависимости от редакции (2014 или 2024)."""
    race_dict = dnd5e_data.races_2024 if edition == '2024' else dnd5e_data.races
    return keyboard_maker(array_to_text_color_array(list(race_dict.values())), keyboard_columns=3, hasbackbutton=True)

race_keyboard = keyboard_maker(array_to_text_color_array(list(dnd5e_data.races.values())), keyboard_columns=3, hasbackbutton=True)
class_keyboard = keyboard_maker(array_to_text_color_array(list(dnd5e_data.classes.values())), keyboard_columns=3, hasbackbutton=True)

#Режимы программы: 1. Создание персонажа, 2. Управление персонажами

def create_character_flow(user_id, step, message_text, attachments=None, original_message_text=None): #создание персонажа
    """Обрабатывает процесс создания персонажа. attachments — список вложений сообщения (для шага загрузки картинки)."""
    attachments = attachments or []
    if original_message_text is None:
        original_message_text = message_text
    characters = load_characters(user_id)
    
    if len(characters) >=30:
        send_message("Слишком много персонажей (30).")
        return

    if user_id not in user_states:
        edition = get_user_edition(user_id)
        user_states[user_id] = {'state': 'create_character', 'step': 1, 'namestate': False, 'method': 'random', 'addracebonuses': edition != '2024', 'character': {}, 'edition': edition}
    state = user_states[user_id]
    edition = state.get('edition', get_user_edition(user_id))
    state['edition'] = edition
    races_data = dnd5e_data.races_2024 if edition == '2024' else dnd5e_data.races
    race_to_subrace_data = dnd5e_data.race_to_subrace_2024 if edition == '2024' else dnd5e_data.race_to_subrace
    r_keyboard = get_race_keyboard(edition)
    abilities_order = ["Сила", "Ловкость", "Выносливость", "Интеллект", "Мудрость", "Харизма"]
    point_buy_cost = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
    
    race_label = "вид" if edition == '2024' else "расу"
    subrace_label = "подвид" if edition == '2024' else "подрасу"

    if step == 1:  # Выбор расы/вида
        send_message(f"Выберите {race_label} вашего персонажа:", r_keyboard)
        state['step'] = 2
    
    elif step == 2:  # Обработка выбора расы/вида
        if message_text.lower() in races_data:
            state['character']['race'] = races_data[message_text.lower()]
            
            if state['character']['race'].lower() in race_to_subrace_data:
                send_message(f"Выберите {subrace_label}:", keyboard_maker('subraces_list', hasbackbutton=True))
                state['step'] = 3
            else: 
                send_message("Выберите класс:", class_keyboard)
                state['step'] = 4

        elif message_text.lower() == "назад":
            send_message("Главное меню:", keyboards.main_keyboard)
            del user_states[user_id]
        else:
            send_message(f"Пожалуйста, выберите {race_label} из предложенных вариантов.", r_keyboard)
    
    elif step == 3:  # Обработка выбора подрасы/подвида
        subrace_data = dnd5e_data.subraces_2024 if edition == '2024' else dnd5e_data.subraces

        if message_text.lower() in subrace_data:
            state['character']['subrace'] = subrace_data[message_text.lower()]
            send_message("Выберите класс:", class_keyboard)
            state['step'] = 4

        elif message_text.lower() == "назад":
            send_message(f"Выберите {race_label} вашего персонажа:", r_keyboard)
            state['step'] = 2
        else:
            send_message(f"Пожалуйста, выберите {subrace_label} из предложенных вариантов.", keyboard_maker('subraces_list', hasbackbutton=True))
        
    elif step == 4:  # Обработка выбора класса
        
        if message_text.lower() in dnd5e_data.classes:
            state['character']['class'] = dnd5e_data.classes[message_text.lower()]
            send_message("Введите имя вашего персонажа:", keyboards.back_keyboard)

            state['namestate'] = True # Бот обработает имя без знаков в беседе
            print(f"Введите имя:")
            state['step'] = 5
        elif message_text.lower() == "назад":
                if state['character']['race'].lower() in race_to_subrace_data:
                    send_message(f"Выберите {subrace_label}:", keyboard_maker('subraces_list', hasbackbutton=True))
                    state['step'] = 3
                else: 
                    send_message(f"Выберите {race_label} вашего персонажа:", r_keyboard)
                    state['step'] = 2
        else:
            send_message("Пожалуйста, выберите класс из предложенных вариантов.", class_keyboard)
    
    elif step == 5:  # Ввод имени
        if message_text == 'назад':
            send_message("Выберите класс:", class_keyboard)
            state['step'] = 4
        elif len(original_message_text) > 0 and len(original_message_text) < 41:
            state['character']['name'] = original_message_text
            state['namestate'] = False # выключение режима ввода имени
            send_message("Загрузите картинку персонажа (отправьте фото в сообщении) или нажмите «Пропустить».", keyboard_maker(array_to_text_color_array(["Пропустить"], "primary"), hasbackbutton=True))
            state['step'] = 'image_upload'
        elif len(original_message_text) > 40:
            send_message("Слишком длинное имя. Введите сокращенное имя вашего персонажа:")
        else:
            send_message("Имя не может быть пустым. Введите имя вашего персонажа:")

    elif step == 'image_upload':  # Загрузка картинки (можно пропустить)
        photo_att = get_photo_attachment(attachments)
        if photo_att:
            state['character']['image'] = photo_att
            url = get_photo_url_from_attachments(attachments)
            if url:
                state['character']['image_url'] = url
            send_message("Картинка сохранена.")
        if photo_att or message_text == 'пропустить':
            buttons = [
                ["Стандартный набор", "primary"],
                ["Случайный набор", "primary"],
                ["Приобретение за очки", "primary"],
                ["Ввести вручную", "secondary"],
            ]
            if edition != '2024':
                buttons.append(["Не применять расовые бонусы", "secondary"])
            send_message(
                "Определите значения характеристик одним из способов:\n"
                "• Стандартный набор (15, 14, 13, 12, 10, 8)\n"
                "• Случайный набор (4d6, сумма 3 наибольших; 6 раз)\n"
                "• Приобретение за очки (27 очков)\n"
                "• Ввести вручную",
                keyboard_maker(buttons, keyboard_columns=2, hasbackbutton=True),
            )
            state['step'] = 6
        elif message_text == 'назад':
            send_message("Введите имя вашего персонажа:", keyboards.back_keyboard)
            state['namestate'] = True
            state['step'] = 5
        else:
            send_message("Отправьте фото или нажмите «Пропустить».", keyboard_maker(array_to_text_color_array(["Пропустить"], "primary"), hasbackbutton=True))

    elif step == 6:  # Выбор способа создания характеристик
        msg = message_text.strip().lower()
        if msg == 'назад':
            send_message("Введите имя вашего персонажа:", keyboards.back_keyboard)
            state['namestate'] = True # Бот обработает имя без знаков в беседе
            print(f"Введите имя:")
            state['step'] = 5
            return

        if msg == 'не применять расовые бонусы' and edition != '2024':
            state['addracebonuses'] = False
            buttons = [
                ["Стандартный набор", "primary"],
                ["Случайный набор", "primary"],
                ["Приобретение за очки", "primary"],
                ["Ввести вручную", "secondary"],
                ["Не применять расовые бонусы", "secondary"],
            ]
            send_message(
                "Хорошо. Расовые бонусы к характеристикам применяться не будут.\n\nВыберите способ создания характеристик:",
                keyboard_maker(buttons, keyboard_columns=2, hasbackbutton=True),
            )
            return

        if msg in ('ввести вручную',):
            hint = "Введите характеристики в формате:\n\n" + " ".join(abilities_order) + "\n\nНапример: 15 14 13 12 10 8"
            if edition != '2024' and state.get('addracebonuses', True):
                hint = (
                    "Введите характеристики в формате (расовые бонусы будут применены позже):\n"
                    + " ".join(abilities_order)
                    + "\n\nНапример: 15 14 13 12 10 8"
                    + "\n\nЕсли вы полуэльф, +2 очка по выбору (+1 к двум характеристикам) можно будет добавить в редакторе персонажа."
                )
            send_message(hint, keyboard_maker(array_to_text_color_array(["Назад"], "secondary")))
            state['step'] = 'stats_manual'
            return

        if msg in ('стандартный набор',):
            pool = [15, 14, 13, 12, 10, 8]
            state['stats_pool'] = pool
            send_message(
                "Получены значения: " + ", ".join(map(str, pool)) + "\n\n"
                "Теперь распределите их по характеристикам.\n"
                "Введите 6 чисел в порядке:\n"
                + " ".join(abilities_order)
                + "\n\nНапример: 15 14 13 12 10 8",
                keyboard_maker(array_to_text_color_array(["Назад"], "secondary")),
            )
            state['step'] = 'stats_assign'
            return

        if msg in ('случайный набор',):
            pool = []
            for _ in range(6):
                rolls = [random.randint(1, 6) for _ in range(4)]
                rolls.remove(min(rolls))
                pool.append(sum(rolls))
            state['stats_pool'] = pool
            send_message(
                "Случайный набор (4d6, сумма 3 наибольших) дал значения:\n"
                + ", ".join(map(str, pool))
                + "\n\nТеперь распределите их по характеристикам.\n"
                "Введите 6 чисел в порядке:\n"
                + " ".join(abilities_order)
                + "\n\nПример: 15 14 13 12 10 8",
                keyboard_maker(array_to_text_color_array(["Назад"], "secondary")),
            )
            state['step'] = 'stats_assign'
            return

        if msg in ('приобретение за очки', 'приобр за очки', 'point buy (27)', 'point buy', 'поинт бай', 'покупка за очки'):
            send_message(
                "Приобретение за очки: у вас 27 очков. Введите 6 значений (8–15) в порядке:\n"
                + " ".join(abilities_order)
                + "\n\nНапример: 15 14 13 12 10 8\n\n"
                "Стоимость: 8=0, 9=1, 10=2, 11=3, 12=4, 13=5, 14=7, 15=9.\n"
                "Сумма стоимости должна быть ≤ 27.",
                keyboard_maker(array_to_text_color_array(["Назад"], "secondary")),
            )
            state['step'] = 'stats_point_buy'
            return

        else:
            buttons = [
                ["Стандартный набор", "primary"],
                ["Случайный набор", "primary"],
                ["Приобретение за очки", "primary"],
                ["Ввести вручную", "secondary"],
            ]
            if edition != '2024':
                buttons.append(["Не применять расовые бонусы", "secondary"])
            send_message("Пожалуйста, выберите вариант из меню:", keyboard_maker(buttons, keyboard_columns=2, hasbackbutton=True))

    elif step == 'stats_assign':  # Распределение полученных значений по характеристикам
        if message_text.strip().lower() == 'назад':
            state.pop('stats_pool', None)
            buttons = [
                ["Стандартный набор", "primary"],
                ["Случайный набор", "primary"],
                ["Приобретение за очки", "primary"],
                ["Ввести вручную", "secondary"],
            ]
            if edition != '2024':
                buttons.append(["Не применять расовые бонусы", "secondary"])
            send_message("Выберите способ создания характеристик:", keyboard_maker(buttons, keyboard_columns=2, hasbackbutton=True))
            state['step'] = 6
            return
        try:
            stats = list(map(int, message_text.replace(',', ' ').split()))
            if len(stats) != 6:
                raise ValueError
            pool = state.get('stats_pool')
            if not pool:
                raise ValueError
            if sorted(stats) != sorted(pool):
                send_message(
                    "Значения не совпадают с полученным набором.\n"
                    "Получены: " + ", ".join(map(str, pool)) + "\n"
                    "Введите 6 чисел (в любом порядке), распределив их как:\n"
                    + " ".join(abilities_order),
                    keyboard_maker(array_to_text_color_array(["Назад"], "secondary")),
                )
                return
            state['character']['stats'] = stats
            state['method'] = 'manual'
            state.pop('stats_pool', None)

            next_message = "Выберите умения в испытаниях через пробел, например:\n\n1 3\n\n"
            saves_array = list(dnd5e_data.abilities.values())
            for i in range(len(saves_array)):
                next_message += f"{i+1}. {saves_array[i]}\n"
            send_message(next_message, keyboards.back_keyboard)
            state['step'] = 'savingthrows'
        except ValueError:
            send_message(
                "Некорректный формат. Введите 6 чисел через пробел или запятую в порядке:\n"
                + " ".join(abilities_order)
                + "\n\nНапример: 15 14 13 12 10 8",
                keyboard_maker(array_to_text_color_array(["Назад"], "secondary")),
            )

    elif step == 'stats_point_buy':  # Приобретение за очки (27)
        if message_text.strip().lower() == 'назад':
            buttons = [
                ["Стандартный набор", "primary"],
                ["Случайный набор", "primary"],
                ["Приобретение за очки", "primary"],
                ["Ввести вручную", "secondary"],
            ]
            if edition != '2024':
                buttons.append(["Не применять расовые бонусы", "secondary"])
            send_message("Выберите способ создания характеристик:", keyboard_maker(buttons, keyboard_columns=2, hasbackbutton=True))
            state['step'] = 6
            return
        try:
            stats = list(map(int, message_text.replace(',', ' ').split()))
            if len(stats) != 6:
                raise ValueError
            if any(s not in point_buy_cost for s in stats):
                send_message(
                    "Можно использовать только значения 8–15.\n"
                    "Стоимость: 8=0, 9=1, 10=2, 11=3, 12=4, 13=5, 14=7, 15=9.\n"
                    "Введите 6 значений в порядке:\n" + " ".join(abilities_order),
                    keyboard_maker(array_to_text_color_array(["Назад"], "secondary")),
                )
                return
            spent = sum(point_buy_cost[s] for s in stats)
            if spent > 27:
                send_message(
                    f"Слишком дорого: {spent} очков (лимит 27). Попробуйте ещё раз.\n"
                    "Введите 6 значений в порядке:\n" + " ".join(abilities_order),
                    keyboard_maker(array_to_text_color_array(["Назад"], "secondary")),
                )
                return
            state['character']['stats'] = stats
            state['method'] = 'manual'

            next_message = f"Приобретение за очки: потрачено {spent}/27.\n\n"
            next_message += "Выберите умения в испытаниях через пробел, например:\n\n1 3\n\n"
            saves_array = list(dnd5e_data.abilities.values())
            for i in range(len(saves_array)):
                next_message += f"{i+1}. {saves_array[i]}\n"
            send_message(next_message, keyboards.back_keyboard)
            state['step'] = 'savingthrows'
        except ValueError:
            send_message(
                "Некорректный формат. Введите 6 чисел (8–15) через пробел или запятую в порядке:\n"
                + " ".join(abilities_order)
                + "\n\nПример: 15 14 13 12 10 8",
                keyboard_maker(array_to_text_color_array(["Назад"], "secondary")),
            )

    elif step == 'stats_manual':  # Ручной ввод характеристик
        if message_text.strip().lower() == 'назад':
            buttons = [
                ["Стандартный набор", "primary"],
                ["Случайный набор", "primary"],
                ["Приобретение за очки", "primary"],
                ["Ввести вручную", "secondary"],
            ]
            if edition != '2024':
                buttons.append(["Не применять расовые бонусы", "secondary"])
            send_message("Выберите способ создания характеристик:", keyboard_maker(buttons, keyboard_columns=2, hasbackbutton=True))
            state['step'] = 6
            return
        try:
            stats = list(map(int, message_text.replace(',', ' ').split()))
            if len(stats) != 6:
                raise ValueError
            state['character']['stats'] = stats
            state['method'] = 'manual'

            next_message = "Выберите умения в испытаниях через пробел, например:\n\n1 3\n\n"
            saves_array = list(dnd5e_data.abilities.values())
            for i in range(len(saves_array)):
                next_message += f"{i+1}. {saves_array[i]}\n"
            send_message(next_message, keyboards.back_keyboard)
            state['step'] = 'savingthrows'
        except ValueError:
            send_message(
                "Некорректный формат. Введите 6 чисел через пробел или запятую, например:\n\n15 14 13 12 10 8",
                keyboard_maker(array_to_text_color_array(["Назад"], "secondary")),
            )


    elif step == 'savingthrows':
        if message_text != 'назад':
            try:
                saves_array = list(dnd5e_data.abilities.values())
                chosen_saves_prof = list(map(int, message_text.split()))
                chosen_saves_prof = [x - 1 for x in chosen_saves_prof]

                prof_mult_dict = {} # словарь с множителями бонуса для испытаний

                for i in range(len(saves_array)):
                    if i in chosen_saves_prof:
                        prof_mult_dict[f'{saves_array[i]}'] = 1
                    else:
                        prof_mult_dict[f'{saves_array[i]}'] = 0

                state['character']['prof_saves_dict'] = prof_mult_dict
                state['step'] = 'skills'


                next_message = "Выберите умения в навыках через пробел (возможность выбрать двойной бонус умения будет далее), например:\n\n1 7 10 14\n\n"
                skills_array = list(dnd5e_data.skills.values())
                for i in range(len(skills_array)):
                    next_message += f"{i+1}. {skills_array[i]}\n"
                send_message(next_message, keyboards.back_keyboard)
            except ValueError:
                next_message = "Неверный формат. Выберите умения в испытаниях через пробел, например:\n\n1 3\n\n"
                saves_array = list(dnd5e_data.abilities.values())
                for i in range(len(saves_array)):
                    next_message += f"{i+1}. {saves_array[i]}\n"
                send_message(next_message, keyboards.back_keyboard)

        else:
            buttons = [
                ["Стандартный набор", "primary"],
                ["Случайный набор", "primary"],
                ["Приобретение за очки", "primary"],
                ["Ввести вручную", "secondary"],
            ]
            if edition != '2024':
                buttons.append(["Не применять расовые бонусы", "secondary"])
            send_message("Выберите способ создания характеристик:", keyboard_maker(buttons, keyboard_columns=2, hasbackbutton=True))
            state['step'] = 6


    elif step == 'skills': # Выбор умений в навыках
        if message_text != 'назад':
            try:
                skills_array = list(dnd5e_data.skills.values())

                chosen_skills_prof = list(map(int, message_text.split()))
                chosen_skills_prof = [x - 1 for x in chosen_skills_prof]

                prof_mult_dict = {} # словарь с множителями бонуса умения для каждого навыка

                for i in range(len(skills_array)):
                    if i in chosen_skills_prof:
                        prof_mult_dict[f'{skills_array[i]}'] = 1
                    else:
                        prof_mult_dict[f'{skills_array[i]}'] = 0

                state['character']['prof_mult_dict'] = prof_mult_dict


                state['step'] = 'double'

                next_message = "Выберите умения в навыках с двойным бонусом умения через пробел, например:\n\n7 16\n\n"
                skills_array = list(dnd5e_data.skills.values())
                for i in range(len(skills_array)):
                    next_message += f"{i+1}. {skills_array[i]}\n"
                send_message(next_message, keyboard_maker(array_to_text_color_array(["Пропустить"]), hasbackbutton=True))
            except ValueError:
                next_message = "Вы ввели неверные значения. Выберите умения в навыках через пробел (возможность выбрать двойной бонус умения будет далее), например:\n\n1 7 10 14\n\n"
                skills_array = list(dnd5e_data.skills.values())
                for i in range(len(skills_array)):
                    next_message += f"{i+1}. {skills_array[i]}\n"
                send_message(next_message, keyboard=keyboards.back_keyboard)
        else:
            next_message = "Выберите умения в испытаниях через пробел, например:\n\n1 3\n\n"
            saves_array = list(dnd5e_data.abilities.values())
            for i in range(len(saves_array)):
                next_message += f"{i+1}. {saves_array[i]}\n"
            send_message(next_message, keyboards.back_keyboard)
            state['step'] = 'savingthrows'

    elif step == 'double':
        skills_array = list(dnd5e_data.skills.values())
        try:
            if message_text != "пропустить" and message_text !="назад":
                chosen_double_prof = list(map(int, message_text.split()))
                if max(chosen_double_prof) > 18 or min(chosen_double_prof) < 1:
                    raise ValueError
                chosen_double_prof = [x - 1 for x in chosen_double_prof]

                prof_mult_dict = state['character']['prof_mult_dict'] # словарь с множителями бонуса умения для каждого навыка

                for i in range(len(skills_array)):
                    if i in chosen_double_prof:
                        prof_mult_dict[f'{skills_array[i]}'] = 2

                state['character']['prof_mult_dict'] = prof_mult_dict
        
            #state['step'] = 'double'
            if message_text !="назад":
                try:
                    subrace = state['character']['subrace']
                except KeyError:
                    subrace={}

                character = generate_character(
                    race=state['character']['race'],
                    saves_dict=state['character']['prof_saves_dict'],
                    subrace=subrace,
                    char_class=state['character']['class'],
                    stats_array=state['character']['stats'],
                    prof_dict=state['character']['prof_mult_dict'],
                    name=state['character']['name'],
                    method=state['method'],
                    addracebonuses=state['addracebonuses'],
                    money={
                        'пм': 0,
                        'зм': 5,
                        'эм': 0,
                        'см': 0,
                        'мм': 0,
                    }
                )
                character['image'] = state['character'].get('image', '')
                character['image_url'] = state['character'].get('image_url', '')
                character['edition'] = edition

                # Сохраняем персонажа
                save_character(user_id, character)

                if get_main_char_id(user_id) == -1:
                    change_main_char(user_id, character['id']) #определение персонажа основным, если нет других персонажей

                send_message(char_sheet_message(character), keyboard=keyboards.main_keyboard)
                exit_state(show_message=False)
            else:
                next_message = "Выберите умения в навыках через пробел (возможность выбрать двойной бонус умения будет далее), например:\n\n1 7 10 14\n\n"
                for i in range(len(skills_array)):
                    next_message += f"{i+1}. {skills_array[i]}\n"
                send_message(next_message, keyboards.back_keyboard)
                state['step'] == 'skills'

        except ValueError:
            next_message = "Вы ввели неверные значения. Попробуйте еще раз или нажмите \"Пропустить\"\n\nВыберите умения в навыках с двойным бонусом умения через пробел, например:\n\n7 16\n\n"
            skills_array = list(dnd5e_data.skills.values())
            for i in range(len(skills_array)):
                next_message += f"{i+1}. {skills_array[i]}\n"
            send_message(next_message, keyboard_maker(array_to_text_color_array(["Пропустить"]), hasbackbutton=True))


def manage_character_flow(user_id, step, message_text, attachments=None, original_message_text=None): #управление персонажами
    attachments = attachments or []
    if original_message_text is None:
        original_message_text = message_text
    if user_id not in user_states:
        user_states[user_id] = {'state': 'manage_character', 'step': 1, 'namestate': False, 'all_characters': [], 'character': {}, 'editparam': ''}
    state = user_states[user_id]

    if step == 1: #выбор персонажа
        state['all_characters'] = load_characters(user_id)
        characters = state['all_characters']

        show_characters(characters)

        state['step'] = 2

    if step == 2: #меню управления персонажем и выбор
        characters = state['all_characters']

        try: #попытка перевести текст в целое число
            message_int = int(message_text)
        except ValueError:
            message_int = -1 #ошибка, выставляем ложное значение для повтора

        

        if message_int <= len(characters) and message_int > 0: #успешно выбран персонаж

            state['character'] = characters[message_int - 1] #персонаж перенесен в состояние (индекс на 1 меньше номера в списке)

            message = char_sheet_message(state['character'])
            char_attachment = state['character'].get('image') or None

            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main, attachment=char_attachment)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main, attachment=char_attachment)

            state['step'] = 3

        elif message_text == "назад": #выход в главное меню
            exit_state()
        else: #повтор, неверное значение
            send_message("Пожалуйста, выберите персонажа из списка.", keyboard=keyboard_maker('chars_list'))

    if step == 3: #вывод персонажа подробно
        
        if message_text == 'удалить':

            send_message("Вы уверены, что хотите удалить этого персонажа?", keyboard_maker( #создине клавиатуры Удалить, не удалять
                [["Не удалять", "primary"], 
                ["Удалить", "negative"]],
                keyboard_columns=2,) 
                )
            state['step'] = 'del'

        elif message_text == 'сделать основным' and get_main_char_id(user_id) != state['character']['id']:
            change_main_char(user_id, state['character']['id'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message("Теперь данный персонаж основной.", keyboards.char_edit_keyboard_main)
            else:
                send_message("Теперь данный персонаж основной.", keyboards.char_edit_keyboard_not_main)

        elif message_text == 'навыки':
            show_all_skills(state['character'])

        elif message_text in ('снаряжение', 'экипировка'):
            state['step'] = 'equipment'
            show_equipment(state['character'])
        
        elif message_text == 'особенности':
            check = show_features(state['character'], rewrite=True)
            if check == -1:
                send_message("Выберите действие.",  keyboard_maker([["Новая особенность", "primary"]], keyboard_columns=2, hasbackbutton=True))
                state['step'] = 'editfeature'
                return
            send_message("Выберите действие. Либо введите номер черты, которую хотите посмотреть или изменить:",  keyboard_maker([["Новая особенность", "primary"],["Удаление особенностей", "secondary"]], keyboard_columns=2, hasbackbutton=True))
            state['step'] = 'editfeature'

            
        elif message_text == 'заклинания':
            state['step'] = 'spells'
            show_all_spells(state['character'])


        elif message_text == 'редактировать':
            send_message("Что вы хотели бы изменить?", keyboard_maker(array_to_text_color_array(
                ["Имя","Характеристики","Уровень","Опыт",
                "Пункты здоровья","Макс. ПЗ",
                "Испытания","Навыки","Инициатива",
                "Класс Брони","Картинка","Особенности","Макс. ячеек"
                ],"primary"),keyboard_columns=3,hasbackbutton=True))
            state['step'] = 'edit'



        elif message_text == 'дубликат':
            if len(state['all_characters']) < 30:
                newchar = state['character'].copy()
                newchar['id'] = len(['all_characters']) + 1
                state['all_characters'].append(newchar)
                write_characters(user_id, state['all_characters'])
                send_message("Дубликат успешно создан.")
            else:
                send_message("Слишком много персонажей (30).")
            
        elif message_text == 'назад':
            state['step'] = 2
            show_characters(state['all_characters'])

        else:
            message = 'Пожалуйста, выберите действие из списка.'
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
    
    elif step == 'equipment': #меню снаряжения
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3

        elif message_text == 'новый предмет':
            state['step'] = 'newitem'
            send_message(
                'Введите предметы через запятую или по одному на строке.\n'
                'Формат: название [количество] [вес] [стоимость]\n'
                'Пример: 5 Кинжал, рубин 5 фунтов (50 зм), ложка 1 фунт, зелье лечения 14, камень 14 зм',
                keyboards.back_keyboard,
            )
        elif message_text == 'удаление предметов':
            if len(state['character']['equipment']) > 0:
                send_message('Укажите через пробел номера предметов, которые хотите удалить, например:\n\n1 3 7 14', keyboards.back_keyboard)
                state['step'] = 'deleteitems'
            else:
                send_message("У вас нет предметов.")
        elif message_text == 'монеты':
            send_message("Укажите на одной строке, сколько монет вы получили или потратили с знаком + или - в начале. Также укажите тип монет (пм, зм, эм, см, мм), например:\n\n+5 зм -3 см +10 мм\n\nЧтобы выйти, нажмите \"Назад\".", keyboards.back_keyboard)
            state['step'] = 'moneymode'
        else:
            send_message("Выберите одну из доступных команд.")
          
    elif step == 'newitem':
        if message_text == 'назад':
            show_equipment(state['character'])
            state['step'] = 'equipment'
        else:
            character = state['character']
            try:
                parsed_items = []
                for line in original_message_text.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    parsed_items.extend(parse_equipment_bulk(line))
                if not parsed_items:
                    raise ValueError("Не найдено ни одного предмета.")
                for it in parsed_items:
                    create_item(
                        character,
                        name=it['name'],
                        amount=it['amount'],
                        cost=it['cost'] if it.get('cost') else None,
                        weight_str=it.get('weight_str', ''),
                    )
                replace_char(character, state['all_characters'])
                write_characters(user_id, state['all_characters'])
                send_message('Предметы успешно добавлены.')
                state['step'] = 'equipment'
                show_equipment(character)
            except ValueError as e:
                send_message(str(e) if str(e) else "Неверный формат. Повторите попытку.")

    elif step == 'deleteitems':
        if message_text == 'назад':
            show_equipment(state['character'])
        else:
            state['step'] = 'equipment'
            try:
                character = state['character']
                item_ids = list(map(int, message_text.split()))
                if len(item_ids) > len(state['character']['equipment']) or len(item_ids) < 1:
                    raise ValueError
                for i in range(len(item_ids)):
                    if item_ids[i] !='':
                        delete_item(character,item_ids[i])
                        replace_char(character,state['all_characters'])
                send_message('Предметы успешно удалены.')
                state['step'] = 'equipment'
                show_equipment(character)
            except ValueError:
                send_message("Неверный формат. Укажите через пробел номера предметов, которые хотите удалить, например:\n\n1 3 7 14")

    elif step == 'moneymode':
        character = state['character']
        if message_text == 'назад':
            show_equipment(state['character'])
            state['step'] = 'equipment'
        else:
            try:
                text = message_text.replace(" ", "")
                money_list = text.split('м')
                for i in range(len(money_list)):
                    if money_list[i] == '':
                        money_list.remove(money_list[i])
                for i in range(len(money_list)):
                    sign = money_list[i][0]
                    type = money_list[i][-1]
                    money_list[i] = money_list[i][:-1]
                    money_list[i] = money_list[i][1:]

                    mod = 1 if sign == '+' else -1

                    value = int(money_list[i]) * mod

                    if type in dnd5e_data.money_array:
                        check = add_money(character, value, type)
                    else:
                        raise ValueError
                if check != 'error':
                    message = 'Теперь у вас:\n'
                    message += money_message(character)
                    message += "Чтобы выйти, нажмите \"Назад\" (или напишите)."
                    send_message(message)
                
                
            except ValueError: 
                send_message("Неверный формат.")
            except IndexError:
                send_message("Неверный формат.")

    elif step == 'spells':
        try:
            num = int(message_text)
        except ValueError:
            num = 0
            print('Ошибка int(message_text)')
        spells = state['character']['known_spells']
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3


        elif num in range(1, len(spells) + 1):
            for i in range(len(spells)):
                if num == state['character']['known_spells'][i]['id']:
                    send_message(resolve_spell_link(state['character']['known_spells'][i]['name']))
                    break
            

        elif message_text == 'добавить новые': 
            state['step'] = 'newspells'
            send_message('Укажите названия новых заклинаний в формате:\n\n"X имя заклинания [english name]", \n\nгде X - круг заклинания (0 для фокуса), \nenglish name - название на английском в квадратных скобках (необязательно, но без него не будет работать ссылка на dnd5e.club). \n\nМожно ввести несколько, каждый на новой строке, например:\n\n0 Леденящее прикосновение [Chill Touch]\n2 Невидимость [Invisibility]', keyboards.back_keyboard)
        elif message_text == 'удаление заклинаний':
            if len(state['character']['known_spells']) > 0:
                # show_all_spells(state['character'], ttg_msg=False)
                send_message('Укажите через пробел номера заклинаний, которые хотите удалить, например:\n\n1 3 7 14', keyboards.back_keyboard)
                state['step'] = 'deletespells'
            else:
                send_message("У вас нет известных заклинаний.")
        elif message_text == 'списокподготовка заклинаний':
            #send_message("Укажите на одной строке, сколько монет вы получили или потратили с знаком + или - в начале. Также укажите тип монет (пм, зм, эм, см, мм), например:\n\n+5 зм -3 см +10 мм\n\nЧтобы выйти, нажмите \"Назад\".", keyboards.back_keyboard)
            #state['step'] = 'preparespells'
            print('kj[]')
        else: 
            send_message('Выберите заклинание или нужную вам функцию.')

    elif step == 'newspells':
        if message_text == 'назад':
            state['step'] = 'spells'
            show_all_spells(state['character'])
        else:
            try:
                character = state['character']
                spells = original_message_text.split('\n')
                for i in range(len(spells)):
                    if spells[i] !='':
                        lvl = int(spells[i][0])
                        spellname = spells[i][2:]
                        create_spell(character,name=spellname, lvl=lvl)
                replace_char(character, state['all_characters'])
                write_characters(user_id, state['all_characters'])
                send_message('Заклинания успешно добавлены.')
                state['step'] = 'spells'
                show_all_spells(character)
            except ValueError:
                send_message("Неверный формат.")

    elif step == 'deletespells':
        if message_text == 'назад':
            show_all_spells(state['character'])
        else:
            state['step'] = 'spells'
            try:
                character = state['character']
                spell_ids = list(map(int, message_text.split()))
                if len(spell_ids) > len(state['character']['known_spells']) or len(spell_ids) < 1:
                    raise ValueError
                for i in range(len(spell_ids)):
                    if spell_ids[i] !='':
                        delete_spell(character,spell_ids[i])
                        replace_char(character,state['all_characters'])
                send_message('Заклинания успешно удалены.')
                state['step'] = 'spells'
                show_all_spells(character)
            except ValueError:
                send_message("Неверный формат. Укажите через пробел номера заклинаний, которые хотите удалить, например:\n\n1 3 7 14")
    
    elif step == 'del':
        if message_text == "удалить":
            delete_character(user_id, state['character']['id'])
            exit_state()
        else: exit_state()

    elif step == 'edit':
        
        if message_text == 'назад':
            message = "Что вы хотите сделать с персонажем?"
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3

        elif message_text == 'имя':
            send_message("Укажите новое имя:", keyboards.back_keyboard)
            state['namestate'] = True
            state['step'] = 'editname'

        elif message_text == 'характеристики':
            send_message("Введите характеристики в формате (расовые бонусы не будут применены к вашим значениям):\n\nСила Ловкость Выносливость Интеллект Мудрость Харизма\n\nНапример: 15 14 13 12 10 8", keyboard_maker(array_to_text_color_array(["Назад"], "secondary")))

            state['step'] = 'editstats'

        elif message_text == 'пункты здоровья':
            send_message("Укажите количество пунктов здоровья:", keyboards.back_keyboard)
            state['step'] = 'edithp'
        elif message_text == 'кости здоровья':
            send_message("Укажите количество максимума пунктов здоровья:", keyboards.back_keyboard)
            state['step'] = 'editcurrhd'

        elif message_text == 'макс. пз':
            send_message("Укажите количество максимума пунктов здоровья:", keyboards.back_keyboard)
            state['step'] = 'editmaxhp'
        
        elif message_text == 'класс брони':
            send_message("Укажите значение КБ:", keyboards.back_keyboard)
            state['step'] = 'editac'

        elif message_text == 'картинка':
            send_message("Отправьте новое фото персонажа или нажмите «Удалить картинку» / «Назад».", keyboard_maker(array_to_text_color_array(["Удалить картинку"], "secondary"), hasbackbutton=True))
            state['step'] = 'editimage'

        elif message_text == 'испытания':
            next_message = "Выберите умения в испытаниях через пробел, например:\n\n1 3\n\n"
            saves_array = list(dnd5e_data.abilities.values())
            for i in range(len(saves_array)):
                next_message += f"{i+1}. {saves_array[i]}\n"
            send_message(next_message, keyboards.back_keyboard)
            state['step'] = 'editsaves'

        elif message_text == 'навыки':
            next_message = "Выберите умения в навыках через пробел (возможность выбрать двойной бонус умения будет далее), например:\n\n1 7 10 14\n\n"
            skills_array = list(dnd5e_data.skills.values())
            for i in range(len(skills_array)):
                next_message += f"{i+1}. {skills_array[i]}\n"
            send_message(next_message, keyboard=keyboards.back_keyboard)
            state['step'] = 'editskills'

        elif message_text == 'уровень':
            send_message("Укажите уровень:", keyboards.back_keyboard)
            state['step'] = 'editlvl'
        
        elif message_text == 'опыт':
            send_message("Укажите количество пунктов опыта:", keyboards.back_keyboard)
            state['step'] = 'editxp'
            
        elif message_text == 'инициатива':
            send_message(f"Введите новое значение инициативы (по умолчанию {get_mod('лов', state['character'])}):", keyboards.back_keyboard)
            state['step'] = 'editinit'

        elif message_text == 'особенности':
            check = show_features(state['character'], rewrite=True)
            if check == -1:
                send_message("Выберите действие.",  keyboard_maker([["Новая особенность", "primary"]], keyboard_columns=2, hasbackbutton=True))
                state['step'] = 'editfeature'
                return
            send_message("Выберите действие. Либо введите номер черты, которую хотите посмотреть или изменить:",  keyboard_maker([["Новая особенность", "primary"],["Удаление особенностей", "secondary"]], keyboard_columns=2, hasbackbutton=True))
            state['step'] = 'editfeature'
        
        elif message_text == 'макс. ячеек':
            show_spell_slots(state['character'])
            send_message("Максимум ячеек какого круга вы хотели бы изменить?", keyboard_maker('numbered_list', number= 9, hasbackbutton=True))
            state['step'] = 'editspellslots1'

    elif step == 'editimage':
        photo_att = get_photo_attachment(attachments)
        if photo_att:
            change_param(state['character'], 'image', photo_att, state['all_characters'])
            url = get_photo_url_from_attachments(attachments)
            if url:
                change_param(state['character'], 'image_url', url, state['all_characters'])
            send_message("Картинка персонажа обновлена.")
            message = char_sheet_message(state['character'])
            att = state['character'].get('image') or None
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main, attachment=att)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main, attachment=att)
            state['step'] = 3
        elif message_text == 'удалить картинку':
            change_param(state['character'], 'image', '', state['all_characters'])
            send_message("Картинка удалена.")
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        elif message_text == 'назад':
            message = char_sheet_message(state['character'])
            att = state['character'].get('image') or None
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main, attachment=att)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main, attachment=att)
            state['step'] = 3
        else:
            send_message("Отправьте фото или нажмите «Удалить картинку» / «Назад».", keyboard_maker(array_to_text_color_array(["Удалить картинку"], "secondary"), hasbackbutton=True))

    # РЕДАКТОР
    elif step == 'editname':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            if len(original_message_text) > 0 and len(original_message_text) < 41:
                change_param(state['character'],'name',original_message_text, state['all_characters'])
                state['namestate'] = False # выключение режима ввода имени
                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3
            elif len(original_message_text) > 40:
                send_message("Слишком длинное имя. Введите сокращенное имя вашего персонажа:")
            else:
                send_message("Имя не может быть пустым. Введите имя вашего персонажа:")

    elif step == 'edithp':    
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            try:
                hp = int(message_text)

                if hp > state['character']['max_hit_points']:
                    #send_message("Выбранные ПЗ больше максимума, также изменяю максимум ПЗ")
                    hp = state['character']['max_hit_points']
                elif hp < 0:
                    hp = 0
                change_param(state['character'],'hit_points',hp,state['all_characters'])
                
                send_message("ПЗ успешно изменены.")


                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3
            except ValueError:
                send_message("Введите число ПЗ без лишних символов.")
            
    elif step == 'editmaxhp':    
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            try:
                maxhp = int(message_text)
                if maxhp < state['character']['max_hit_points']:
                    if maxhp < state['character']['hit_points']:
                        newhp = maxhp
                        change_param(state['character'],'hit_points',newhp,state['all_characters'])
                elif maxhp == state['character']['max_hit_points']:
                    send_message("У вас уже такой максимум ПЗ.")
                    return
                elif maxhp < 1:
                    maxhp = 1
                change_param(state['character'],'max_hit_points',maxhp,state['all_characters'])
                send_message("Макс. ПЗ успешно изменены.")
                

                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3
            except ValueError:
                send_message("Введите число макс. ПЗ без лишних символов.")

    elif step == 'editac':    
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            try:
                ac = int(message_text)
                change_param(state['character'],'armor_class',ac,state['all_characters'])
                send_message("КБ успешно изменен.")

                

                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3
            except ValueError:
                send_message("Введите КБ без лишних символов.")


    elif step == 'editlvl':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            try:
                lvl = int(message_text)
                if lvl == state['character']['level']:
                    send_message("Вы уже этого уровня.")
                elif lvl > 1 or lvl < 20:
                    lvl = int(message_text)
                    lvldiff = lvl - state['character']['level']

                    change_param(state['character'],'level',lvl,state['all_characters'])
                    
                    hit_dice_curr = state['character']['hit_dice_count']

                    if state['character']['hit_dice_max'] - hit_dice_curr <= (lvldiff * -1):
                        hit_dice_curr = state['character']['lvl'] 
                    else:
                        hit_dice_curr += lvldiff
                    bonusnew = dnd5e_data.proficiency_bonus(lvl)
                    change_param(state['character'],'proficiency_bonus',bonusnew,state['all_characters'])
                    change_param(state['character'],'hit_dice_max',lvl,state['all_characters'])
                    change_param(state['character'],'hit_dice_count',hit_dice_curr,state['all_characters'])
                    send_message("Уровень успешно изменен.")

                

                    message = char_sheet_message(state['character'])
                    if get_main_char_id(user_id) == state['character']['id']:
                        send_message(message, keyboards.char_edit_keyboard_main)
                    else:
                        send_message(message, keyboards.char_edit_keyboard_not_main)
                    state['step'] = 3
                else:
                    send_message("Уровень не может быть меньше 1 или больше 20.")
            except ValueError:
                send_message("Введите уровень без лишних символов.")

    elif step == 'editstats':
        try:
            if message_text != 'назад':
                stats = list(map(int, message_text.replace(',', ' ').split()))
                if len(stats) != 6:
                    raise ValueError
                stats_dict = {
                'strength': stats[0],
                'dexterity': stats[1],
                'constitution': stats[2],
                'intelligence': stats[3],
                'wisdom': stats[4],
                'charisma': stats[5]
                }
                newinit = dnd5e_data.calc_mod(stats_dict['dexterity'])
                state['character']['initiative'] = newinit
                state['character']['stats'] = stats_dict
                replace_char(state['character'], load_characters(user_id))

                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3

            elif message_text == 'назад':
                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3
            else:
                send_message("Введите характеристики в формате (расовые бонусы не будут применены к вашим значениям):\n\nСила Ловкость Выносливость Интеллект Мудрость Харизма\n\nНапример: 15 14 13 12 10 8", keyboard_maker(array_to_text_color_array(["Назад"], "secondary")))
                state['step'] = 8

        except ValueError:
            send_message("Некорректный формат. Введите 6 чисел через пробел, например:\n\n15 14 13 12 10 8", keyboard_maker(array_to_text_color_array(["Назад"],'secondary')))


    elif step == 'editspellslots1':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            try:
                value = int(message_text)
                if value < 1 or value > 9:
                    raise ValueError
                send_message("Введите новое количество ячеек.", keyboard=keyboards.back_keyboard)
                state['editparam'] = value
                state['step'] = 'editspellslots2'
            except ValueError:
                send_message("Введите цифру от 1 до 9 (круг ячеек).")

    elif step == 'editspellslots2':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            try:
                value = int(message_text)
                if value > 4 or value < 0:
                    raise ValueError
                try: 
                    slots_arr = state['character']['spell_slots']
                except KeyError:
                    state['character']['spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                    slots_arr = state['character']['spell_slots']
                
                curr_slots_arr = state['character']['current_spell_slots']
                slots_arr[state['editparam']] = value
                if curr_slots_arr[state['editparam']] > value:
                    curr_slots_arr[state['editparam']] = value

                state['character']['current_spell_slots'] = curr_slots_arr
                state['character']['spell_slots'] = slots_arr
                replace_char(state['character'], state['all_characters'])
                
                send_message("Количество ячеек успешно изменено.")

                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3

            except ValueError:
                send_message("Вы ввели неверное значение. Введите количество ячеек заклинаний на этом кругу.")



    elif step == 'editsaves':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else:
            try:
                saves_array = list(dnd5e_data.abilities.values())
                chosen_saves_prof = list(map(int, message_text.split()))
                chosen_saves_prof = [x - 1 for x in chosen_saves_prof]

                prof_mult_dict = {} # словарь с множителями бонуса для испытаний

                for i in range(len(saves_array)):
                    if i in chosen_saves_prof:
                        prof_mult_dict[f'{saves_array[i]}'] = 1
                    else:
                        prof_mult_dict[f'{saves_array[i]}'] = 0

                state['character']['prof_saves_dict'] = prof_mult_dict
                replace_char(state['character'], load_characters(user_id))
            
                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3

            except ValueError:
                next_message = "Неверный формат. Выберите умения в испытаниях через пробел, например:\n\n1 3\n\n"
                saves_array = list(dnd5e_data.abilities.values())
                for i in range(len(saves_array)):
                    next_message += f"{i+1}. {saves_array[i]}\n"
                send_message(next_message, keyboards.back_keyboard)



    elif step == 'editskills': # Выбор умений в навыках
        if message_text != 'назад':
            try:
                skills_array = list(dnd5e_data.skills.values())

                chosen_skills_prof = list(map(int, message_text.split()))
                chosen_skills_prof = [x - 1 for x in chosen_skills_prof]

                prof_mult_dict = {} # словарь с множителями бонуса умения для каждого навыка

                for i in range(len(skills_array)):
                    if i in chosen_skills_prof:
                        prof_mult_dict[f'{skills_array[i]}'] = 1
                    else:
                        prof_mult_dict[f'{skills_array[i]}'] = 0

                state['character']['prof_mult_dict'] = prof_mult_dict
                replace_char(state['character'], load_characters(user_id))

                state['step'] = 'editdouble'

                next_message = "Выберите умения в навыках с двойным бонусом умения через пробел, например:\n\n7 16\n\n"
                skills_array = list(dnd5e_data.skills.values())
                for i in range(len(skills_array)):
                    next_message += f"{i+1}. {skills_array[i]}\n"
                send_message(next_message, keyboard_maker(array_to_text_color_array(["Пропустить"]), hasbackbutton=True))
            except ValueError:
                next_message = "Вы ввели неверные значения. Выберите умения в навыках через пробел (возможность выбрать двойной бонус умения будет далее), например:\n\n1 7 10 14\n\n"
                skills_array = list(dnd5e_data.skills.values())
                for i in range(len(skills_array)):
                    next_message += f"{i+1}. {skills_array[i]}\n"
                send_message(next_message, keyboard=keyboards.back_keyboard)
        else:
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3



    elif step == 'editdouble':
        skills_array = list(dnd5e_data.skills.values())
        try:
            if message_text != "пропустить" and message_text !="назад":
                chosen_double_prof = list(map(int, message_text.split()))
                if max(chosen_double_prof) > 18 or min(chosen_double_prof) < 1:
                    raise ValueError
                chosen_double_prof = [x - 1 for x in chosen_double_prof]

                prof_mult_dict = state['character']['prof_mult_dict'] # словарь с множителями бонуса умения для каждого навыка

                for i in range(len(skills_array)):
                    if i in chosen_double_prof:
                        prof_mult_dict[f'{skills_array[i]}'] = 2

                state['character']['prof_mult_dict'] = prof_mult_dict

                replace_char(state['character'], load_characters(user_id))
                
                
            elif message_text !="назад":
                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3

            else:
                next_message = "Выберите умения в навыках с двойным бонусом умения через пробел, например:\n\n7 16\n\n"
                skills_array = list(dnd5e_data.skills.values())
                for i in range(len(skills_array)):
                    next_message += f"{i+1}. {skills_array[i]}\n"
                send_message(next_message, keyboard_maker(array_to_text_color_array(["Пропустить"]), hasbackbutton=True))

        except ValueError:
            next_message = "Вы ввели неверные значения. Попробуйте еще раз или нажмите \"Пропустить\"\n\nВыберите умения в навыках с двойным бонусом умения через пробел, например:\n\n7 16\n\n"
            skills_array = list(dnd5e_data.skills.values())
            for i in range(len(skills_array)):
                next_message += f"{i+1}. {skills_array[i]}\n"
            send_message(next_message, keyboard_maker(array_to_text_color_array(["Пропустить"]), hasbackbutton=True))

    elif step == 'editbonus':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            try:
                bonus = int(message_text)
                change_param(state['character'],'proficiency_bonus',bonus,state['all_characters'])
                send_message("Значение бонуса мастерства успешно изменено.")

                

                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3
            except ValueError:
                send_message("Введите значение бонуса мастерства без лишних символов.")

    elif step == 'editfeature':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        elif message_text.isdigit():
            numberfeatures = len(state['character']['proficiencies'])
            if numberfeatures == 0:
                send_message("У вас нет особенностей.")
                return
            id = int(message_text)

            if id > numberfeatures or id < 1:
                send_message("У вас нет особенности под таким номером.")
                return
            
            show_desc_feature(state['character'], id)
            send_message("Что хотите сделать с этой чертой?", keyboard_maker([["Изменить", "primary"], ["Удалить", "secondary"]],keyboard_columns=2, hasbackbutton=True))
            state['editparam'] = id
            state['step'] = 'editcurrfeature'
        else: 
            if message_text == 'новая особенность':
                state['step'] = 'newfeature'
                send_message('Выберите тип особенности:', keyboard_maker(array_to_text_color_array(["Основная","Классовая", "Расовая", "Предыстории"]),hasbackbutton=True))

            elif message_text == 'удаление особенностей':
                state['step'] = 'delfeature'
                send_message('Укажите через пробел номера особенностей, которые хотите удалить, например:\n\n1 3 7 14', keyboards.back_keyboard)


    elif step == 'newfeature':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            if message_text == 'классовая':
                state['editparam'] = 'class'
            elif message_text == 'основная':
                state['editparam'] = 'main'
            elif message_text == 'расовая':
                state['editparam'] = 'race'
            elif message_text == 'предыстории':
                state['editparam'] = 'background'
            send_message("Укажите название черты и описание (на новой строке).", keyboards.back_keyboard)
            state['step'] = 'createfeature'



    elif step == 'createfeature':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            parts = original_message_text.split('\n', maxsplit=1)
            if len(parts) > 2 or len(parts) < 2:
                send_message("Неверный формат.")
                return
            create_feature(state['character'], name=parts[0], desc=parts[1], type=state['editparam'])
            send_message("Особенность успешно записана.")
            show_features(state['character'], rewrite=True)
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3

    elif step == 'editcurrfeature':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else:
            if message_text == 'изменить':
                send_message("Укажите новое описание.")
                state['step'] = 'newdescfeature'
            if message_text == 'удалить':
                delete_feature(state['character'], state['editparam'])
                send_message("Особенность удалена.")
                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3

    elif step == 'newdescfeature':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else:
            char = state['character']
            for i in range(len(char['proficiencies'])):
                if char['proficiencies'][i]['id'] == state['editparam']:
                    char['proficiencies'][i]['desc'] = original_message_text
            send_message("Описание черты успешно изменено.")

            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3

            


    elif step == 'editcurrhd':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            try:
                hd = int(message_text)
                change_param(state['character'],'armor_class',hd,state['all_characters'])
                send_message("Количество текущих КЗ успешно изменено.")

                

                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3
            except ValueError:
                send_message("Введите количество текущих КЗ без лишних символов.")

    elif step == 'editxp':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            try:
                xp = int(message_text)
                if xp > 0:
                    change_param(state['character'],'xp',xp,state['all_characters'])
                    send_message("Количество пунктов опыта успешно изменено.")

                

                    message = char_sheet_message(state['character'])
                    if get_main_char_id(user_id) == state['character']['id']:
                        send_message(message, keyboards.char_edit_keyboard_main)
                    else:
                        send_message(message, keyboards.char_edit_keyboard_not_main)
                    state['step'] = 3
                else:
                    send_message("Количество пунктов опыта не может быть меньше 0.")
            except ValueError:
                send_message("Введите количество текущих пунктов опыта без лишних символов.")

    elif step == 'editinit':
        if message_text == 'назад':
            message = char_sheet_message(state['character'])
            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            state['step'] = 3
        else: 
            try:
                init = int(message_text)

                change_param(state['character'],'initiative',init,state['all_characters'])
                send_message("Значение инициативы успешно изменено.")

            

                message = char_sheet_message(state['character'])
                if get_main_char_id(user_id) == state['character']['id']:
                    send_message(message, keyboards.char_edit_keyboard_main)
                else:
                    send_message(message, keyboards.char_edit_keyboard_not_main)
                state['step'] = 3

            except ValueError:
                send_message("Введите значение инициативы без лишних символов.")


        



    
def is_xdy_format(text):
    if 'd' not in text:
        if 'к' not in text:
            if 'д' not in text:
                return False
    text = text.replace(" ", "")
    parts = text.split('d')
    if len(parts) < 2:
        parts = text.split('к')
    if len(parts) < 2:
        parts = text.split('д')
    p = parts[1].split('+')
    m = parts[1].split('-')
    if len(parts) > 2:
        return False
    if len(p) < 3 and len(p) > 1:
        if p[0].isdigit() and p[1].isdigit():
            return True
    if len(m) < 3 and len(m) > 1:
        if m[0].isdigit() and m[1].isdigit():
            return True
    if parts[0] != "" and parts[0].isdigit() == False:
        return False
    # print(int(parts[0]))
    return parts[1].isdigit()


def parse_complex_dice(text):
    """
    Парсит сложные формулы: 3d20+4+8, d20+d4, 2d6+3d4+5.
    Возвращает ([(amount, die), ...], total_mod) или None при ошибке.
    """
    s = text.replace(" ", "").replace("к", "d").replace("д", "d")
    if "d" not in s:
        return None
    dice_terms = []
    total_mod = 0
    parts = s.split("+")
    for token in parts:
        if not token:
            continue
        if "d" in token:
            # Термин вида XdY или XdY-N
            if "-" in token and token[-1].isdigit():
                token, _, neg = token.rpartition("-")
                if neg.isdigit():
                    total_mod -= int(neg)
                    if not token:
                        continue
            if "d" not in token:
                return None
            d_parts = token.split("d", 1)
            try:
                amount = int(d_parts[0]) if d_parts[0].strip() else 1
                die_str = d_parts[1].strip()
                if not die_str or not die_str.isdigit():
                    return None
                die = int(die_str)
                if amount < 1 or die < 1 or amount > 500 or die > 10000:
                    return None
                dice_terms.append((amount, die))
            except (ValueError, IndexError):
                return None
        else:
            try:
                # Позволяем "4-2" как два модификатора: +4 и -2
                for part in token.replace("-", "+-").split("+"):
                    if part.strip():
                        total_mod += int(part)
            except ValueError:
                return None
    if not dice_terms:
        return None
    return (dice_terms, total_mod)


def roll_complex_dice(dice_terms, total_mod, has_message=False):
    """Бросок по сложной формуле: несколько типов костей и суммарный модификатор."""
    total_roll = 0
    parts_desc = []
    for amount, die in dice_terms:
        group_sum = 0
        rolls = []
        for _ in range(amount):
            r = random.randint(1, die)
            group_sum += r
            rolls.append(r)
        total_roll += group_sum
        if amount == 1:
            parts_desc.append(f"d{die}({rolls[0]})")
        else:
            parts_desc.append(f"{amount}d{die}({'+'.join(map(str, rolls))})")
    total = total_roll + total_mod
    mod_str = f" + {total_mod}" if total_mod > 0 else (f" - {-total_mod}" if total_mod < 0 else "")
    msg = " + ".join(parts_desc) + mod_str + f" = {total} 🎲"
    if has_message:
        send_message(msg)
    return total

# Справка по командам (краткое описание и ключи для детальной помощи)
HELP_TOPICS = {
    'нап': ('Напарник (нап, напар)', (
        "Напарник — компаньон с короткой кличкой. Все команды — раздельными словами.\n\n"
        "• Список: нап / напарник / напар (без аргументов)\n"
        "• Добавить: нап <имя> [кличка], например: нап Римус рим\n"
        "• Удалить: нап уд [кличка] или нап удалить [кличка], например: нап уд рим\n"
        "• Карточка: введите только кличку (например: рим)\n"
        "• Инициатива: [кличка] ини <число>. ПЗ: [кличка] пз ±число. Макс. ПЗ: [кличка] макс / [кличка] мпз <число>\n"
        "• КБ: [кличка] кб <число>. Бонус атаки: [кличка] атк <число>; бросок атаки: [кличка] атк\n"
        "• Испытания: [кличка] исп лов | исп сил | исп вын | исп инт | исп муд | исп хар (например: рим исп лов)\n"
        "• Навыки: [кличка] <код> [число], например: рим лов 5, рим сил -1, рим лов (бросок)"
    )),
    'справка': ('Справка dnd5e.club (справ, dnd, спр)', (
        "Поиск заклинаний: справка <запрос> или справ / dnd / спр.\n"
        "Пример: справка огненный шар или спр fireball → ссылка на dnd5e.club\n"
        "По номеру заклинания: спр закл N — ссылка на N-е заклинание из вашего списка (например: спр закл 1)."
    )),
    'поиск': ('Поиск по справочнику dnd5e.club', (
        "Поиск по всему справочнику: поиск <запрос>.\n"
        "Пример: поиск дракон или поиск fireball.\n"
        "Бот покажет до 5 результатов — название каждого элемента будет ссылкой на dnd5e.club.\n"
        "Индекс загружается при первом поиске. Обновить вручную: обновить поиск (или поиск обновить)."
    )),
    'кубики': ('Броски кубиков XdY и по характеристикам', (
        "• Формула XdY: 2d6, d20, 10d100. С модификатором: 3d20+4.\n"
        "• Несколько модификаторов суммируются: 3d20+4+8 = 3d20+12.\n"
        "• Несколько костей: d20+d4, 2d6+3d4+5.\n"
        "• По характеристикам: одно слово (сил, лов, про и т.д.). Испытания: исп лов, исп сил, исп вын, исп инт, исп муд, исп хар.\n"
        "• Помеха: пом лов. Преимущество: пре лов."
    )),
    'инициатива': ('Инициатива (ини, иниц)', (
        "Команда ини / инициатива бросает инициативу за основного персонажа и всех напарников.\n"
        "В одном сообщении выводятся имя, бросок и результат для каждого."
    )),
    'вдох': ('Вдохновение (вдох, +вдох, -вдох)', (
        "• вдох — показать, есть ли у персонажа вдохновение.\n"
        "• +вдох — получить вдохновение (установить наличие).\n"
        "• -вдох — потратить вдохновение: перебросить последнюю кость с теми же модификаторами. Если вдохновения нет или не было броска — выдаётся сообщение."
    )),
    'персонажи': ('Персонажи и меню', (
        "• Создать персонажа — начать создание.\n"
        "• Мои персонажи — список и выбор персонажа.\n"
        "• Я — карточка основного персонажа."
    )),
    'помощь': ('Помощь по командам', (
        "Помощь — показать список команд.\n"
        "Помощь <команда> — подробная справка по команде, например: помощь нап.\n"
        "Команда «пом» используется только для броска с помехой (пом лов, пом про и т.д.)."
    )),
    'редакция': ('Редакция (2014 / 2024)', (
        "Редакция — выбор правил для создания персонажей.\n\n"
        "• 2014 — классические расы PHB с расовыми бонусами к характеристикам и подрасами.\n"
        "• 2024 — виды из PHB 2024 (Аасимар, Дварф, Драконорождённый, Гном, Голиаф, Орк, Полурослик, Тифлинг, Человек, Эльф); расовые бонусы к характеристикам не применяются."
    )),
}

def show_help(message_id, topic=None):
    """Показать справку: список команд или детальную справку по теме (помощь нап, помощь справка и т.д.)."""
    try:
        if topic:
            topic_lower = topic.strip().lower()
            for key, (short, long_text) in HELP_TOPICS.items():
                if key == topic_lower or topic_lower in key or short.lower().startswith(topic_lower):
                    text = "".join(long_text) if isinstance(long_text, (tuple, list)) else long_text
                    send_message(f"{short}\n\n{text}", keyboards.main_keyboard)
                    return
            send_message("Не найдена команда для уточнения. Напишите «помощь» для списка команд.", keyboards.main_keyboard)
            return
        lines = ["Список команд (для подробностей: помощь <команда>):\n"]
        for key, (short, _) in HELP_TOPICS.items():
            lines.append(f"• {short}")
        lines.append("\nБот для персонажей D&D 5e: создание, кубики, напарники, справка.")
        send_message("\n".join(lines), keyboards.main_keyboard)
    except Exception as e:
        print("show_help error:", e)
        send_message("Список команд: Создать персонажа, Мои персонажи, Редакция (2014/2024), Помощь, Напарник (нап), Поиск (поиск), Справка (справ/dnd/спр), Кубики XdY и по навыкам, Инициатива (ини). Напишите «помощь команда» для подробностей.")

# Основной цикл бота
class _TelegramObject:
    def __init__(self, message):
        self.message = message


class _TelegramEvent:
    def __init__(self, update):
        message = update.get('message') or update.get('edited_message') or {}
        chat = message.get('chat') or {}
        from_user = message.get('from') or {}
        text = message.get('text') or message.get('caption') or ''
        attachments = []
        photos = message.get('photo') or []
        if photos:
            best_photo = photos[-1]
            file_url = get_telegram_file_url(best_photo['file_id'])
            if file_url:
                attachments.append({'type': 'photo', 'photo': {'url': file_url}})
        self.type = VkBotEventType.MESSAGE_NEW
        self.chat_id = None if chat.get('type') == 'private' else chat.get('id')
        self.message = {'text': text, 'attachments': attachments}
        self.obj = _TelegramObject({
            'from_id': from_user.get('id') or chat.get('id'),
            'text': text,
            'attachments': attachments,
        })


def handle_bot_event(incoming_event):
    global event, chat_id, user_id, message_id
    event = incoming_event

    if event.type == VkBotEventType.MESSAGE_NEW:
        chat_id = event.chat_id
        user_id = event.obj.message['from_id']
        if chat_id != None:  # Определение, личные сообщения или беседа
            message_id = chat_id
            if (f'{symbol}' in event.message.get('text')
                or f'@ezgamednd' in event.message.get('text')) == False:
                    if user_id in user_states:
                        if user_states[user_id]['namestate'] == False:
                            return # Пропуск сообщения, если боту пишут в чат без упоминания или не пишут '/' перед сообщением
                    else:
                        return
        else: message_id = user_id

        message_text = event.obj.message['text'] # Получение сообщения пользователя
        if f'[club179538565|@ezgamednd] ' or f'{symbol}' in message_text: # Удаляем упоминание и слэш из текста сообщения
            message_text = message_text.replace(f'[club179538565|@ezgamednd] ', '')
            message_text = message_text.replace(f'{symbol}', '')
        
        original_message_text = message_text
        message_text = message_text.lower() 
        
        print(f'{message_text}') #текст в терминал

        # Команда справки: ссылка на dnd5e.club (справка/справ/dnd/спр + текст запроса)
        # Специальный формат: спр закл N — ссылка на N-е заклинание из списка персонажа (dnd5e.club)
        dnd_ref_commands = ('справка ', 'справ ', 'dnd ', 'спр ')
        msg_stripped = message_text.strip()
        dnd_ref_handled = False
        for cmd in dnd_ref_commands:
            if msg_stripped.startswith(cmd):
                query = original_message_text.strip()[len(cmd):].strip()
                query_lower = query.lower()
                # Проверка "спр закл N" — поиск по номеру заклинания в списке персонажа
                if query_lower.startswith('закл '):
                    rest = query_lower[5:].strip()
                    if rest.isdigit():
                        try:
                            char = load_main_character(user_id)
                            spells = char.get('known_spells', [])
                            num = int(rest)
                            if num > 0 and num <= len(spells):
                                for s in spells:
                                    if s.get('id') == num:
                                        send_message(resolve_spell_link(s.get('name', '')))
                                        dnd_ref_handled = True
                                        break
                                else:
                                    send_message("Заклинания под таким номером не найдено.")
                                    dnd_ref_handled = True
                            else:
                                send_message("Укажите номер заклинания из вашего списка (1–" + str(len(spells)) + ").")
                        except (ValueError, KeyError, IndexError, TypeError):
                            send_message("Персонаж не подключен или нет заклинаний. Создайте персонажа и добавьте заклинания.")
                        dnd_ref_handled = True
                        break
                if not dnd_ref_handled and query:
                    link = find_dnd5e_spell_link(query) or DND5E_CLUB_SPELLS_URL
                    send_message(link)
                    dnd_ref_handled = True
                elif not dnd_ref_handled:
                    send_message("Укажите поисковый запрос после команды, например: справка огненный шар или спр fireball\nИли: спр закл 1 — ссылка на первое заклинание из вашего списка.")
                    dnd_ref_handled = True
                break
        if not dnd_ref_handled and msg_stripped in ('справка', 'справ', 'dnd', 'спр'):
            send_message("Использование: справка <запрос>\nНапример: справка огненный шар или спр fireball\nИли: спр закл 1 — ссылка на заклинание по номеру в списке.")
            dnd_ref_handled = True
        if dnd_ref_handled:
            return

        # Обновление индекса поиска по dnd5e.club
        if msg_stripped in ('обновить поиск', 'поиск обновить'):
            send_dnd5e_handbook_refresh_message(*refresh_dnd5e_handbook_index())
            return

        # Поиск по справочнику dnd5e.club
        if msg_stripped.startswith('поиск '):
            query = original_message_text.strip()[len('поиск '):].strip()
            if query.lower() == 'обновить':
                send_dnd5e_handbook_refresh_message(*refresh_dnd5e_handbook_index())
            elif query:
                start_dnd5e_handbook_search(user_id, query)
            else:
                send_message("Укажите запрос после команды, например: поиск дракон")
            return
        if msg_stripped == 'поиск':
            send_message(
                "Использование: поиск <запрос>\n"
                "Например: поиск дракон или поиск fireball\n"
                "Покажет до 5 результатов — названия будут ссылками на dnd5e.club.\n"
                "Обновить индекс: обновить поиск"
            )
            return

        # --- Напарники: список, добавление и просмотр ---
        companions = load_companions(user_id)
        companion_handled = False
        # Только «нап» / «напарник» / «напар» без аргументов — список напарников
        if msg_stripped in ('напарник', 'нап', 'напар'):
            send_message(companions_list_text(companions))
            return
        # Удалить напарника: нап уд [кличка] / нап удалить [кличка]
        _words = msg_stripped.split()
        if len(_words) >= 3 and _words[0] == 'нап' and _words[1] in ('уд', 'удалить'):
            nick = _words[2].lower()
        else:
            nick = None
        if nick is not None:
            if not nick:
                send_message("Укажите кличку: нап уд [кличка] или нап удалить [кличка], например: нап уд рим")
            elif nick in companions:
                name = companions[nick]['name']
                del companions[nick]
                save_companions(user_id, companions)
                send_message(f"Напарник «{name}» (кличка {nick}) удалён.")
            else:
                send_message("Нет напарника с такой кличкой. Удаление: нап уд [кличка] или нап удалить [кличка]")
            return
        # Добавить напарника: "напарник Имя [кличка]" / "нап Имя [кличка]" / "напар Имя [кличка]"
        for add_cmd in ('напарник ', 'нап ', 'напар '):
            if msg_stripped.startswith(add_cmd):
                rest = original_message_text.strip()[len(add_cmd):].strip().split()
                if len(rest) >= 2:
                    comp_name, nick = rest[0], rest[1].lower()
                    if nick in RESERVED_NICKNAMES:
                        send_message(f"Кличка «{nick}» занята системной командой. Выберите другую.")
                    elif nick in companions:
                        send_message(f"Напарник с кличкой «{nick}» уже есть.")
                    else:
                        companions[nick] = companion_default(comp_name)
                        save_companions(user_id, companions)
                        send_message(f"Напарник «{comp_name}» добавлен с кличкой «{nick}». Команда: /{nick}")
                else:
                    send_message(companions_list_text(companions))
                companion_handled = True
                break
        if companion_handled:
            return
        # Показать карточку напарника по кличке (точное совпадение)
        if msg_stripped in companions:
            send_message(companion_card_text(companions[msg_stripped]))
            return
        # Команды напарника (раздельные слова): [кличка] исп лов, [кличка] атк, [кличка] ини 5 и т.д.
        _words = msg_stripped.split()
        if len(_words) >= 2 and _words[0] in companions:
            nick = _words[0]
            rest_words = _words[1:]
            comp = companions[nick]
            matched = False
            # Испытание: [кличка] исп <характеристика> (например: рим исп лвк, рим испытание мудрость)
            if len(rest_words) == 2 and rest_words[0] in ('исп', 'испытание') and rest_words[1] in COMPANION_TRIAL_CODE_MAP:
                code = COMPANION_TRIAL_CODE_MAP[rest_words[1]]
                mod = comp.get('skills', {}).get(code, 0)
                roll_val = random.randint(1, 20)
                name_trial = COMPANION_TRIAL_NAMES.get(code, code)
                send_message(format_companion_roll(comp['name'], name_trial, roll_val, mod))
                matched = True
            # Атака: [кличка] атк / [кличка] атак
            elif len(rest_words) == 1 and rest_words[0] in ('атк', 'атак'):
                mod = comp['attack_bonus']
                roll_val = random.randint(1, 20)
                send_message(format_companion_roll(comp['name'], 'Атака', roll_val, mod))
                matched = True
            # Остальные команды: [кличка] суффикс [число]
            elif rest_words and rest_words[0] in COMPANION_STAT_SUFFIXES:
                suf = rest_words[0]
                try:
                    val = int(rest_words[1]) if len(rest_words) > 1 else None
                except (ValueError, IndexError):
                    val = None
                if suf == 'ини':
                    if val is not None:
                        comp['initiative'] = val
                        send_message(f"{comp['name']}: инициатива {val:+d}.")
                    else:
                        send_message("Укажите число: [кличка] ини <число>, например: рим ини 1")
                    matched = True
                elif suf in ('пз',):
                    if val is not None:
                        comp['hp'] = max(0, min(comp['max_hp'], comp['hp'] + val))
                        send_message(f"{comp['name']}: ПЗ теперь {comp['hp']}/{comp['max_hp']}.")
                    else:
                        send_message("Укажите число: [кличка] пз ±число, например: рим пз -5")
                    matched = True
                elif suf in ('макс', 'мпз'):
                    if val is not None:
                        comp['max_hp'] = max(1, val)
                        if comp['hp'] > comp['max_hp']:
                            comp['hp'] = comp['max_hp']
                        send_message(f"{comp['name']}: макс. ПЗ = {comp['max_hp']}.")
                    else:
                        send_message("Укажите число: [кличка] макс <число> или [кличка] мпз <число>")
                    matched = True
                elif suf == 'кб':
                    if val is not None:
                        comp['ac'] = val
                        send_message(f"{comp['name']}: КБ = {val}.")
                    else:
                        send_message("Укажите число: [кличка] кб <число>")
                    matched = True
                elif suf in ('атак', 'атк'):
                    if val is not None:
                        comp['attack_bonus'] = val
                        send_message(f"{comp['name']}: бонус атаки {val:+d}.")
                    else:
                        send_message("Бросок атаки: [кличка] атк. Изменить бонус: [кличка] атк <число>, например: рим атк 3")
                    matched = True
                elif suf in ('уров', 'ур', 'уровень'):
                    if val is not None:
                        comp['level'] = max(1, min(20, val))
                        send_message(f"{comp['name']}: уровень {comp['level']}.")
                    else:
                        send_message("Укажите число: [кличка] ур / [кличка] уров / [кличка] уровень <число>")
                    matched = True
                elif suf in COMPANION_STAT_SUFFIXES:
                    if val is not None:
                        if 'skills' not in comp:
                            comp['skills'] = {}
                        storage_key = COMPANION_SKILL_STORAGE_KEY(suf)
                        comp['skills'][storage_key] = val
                        skill_name = COMPANION_SKILL_DISPLAY.get(suf, suf)
                        send_message(f"{comp['name']}: {skill_name} {val:+d}.")
                    else:
                        storage_key = COMPANION_SKILL_STORAGE_KEY(suf)
                        mod = comp.get('skills', {}).get(storage_key, 0)
                        roll_val = random.randint(1, 20)
                        check_name = COMPANION_CHECK_NAMES.get(suf, COMPANION_SKILL_DISPLAY.get(suf, suf))
                        send_message(format_companion_roll(comp['name'], check_name, roll_val, mod))
                    matched = True
            if matched:
                save_companions(user_id, companions)
                companion_handled = True
        if companion_handled:
            return

        # Помощь: только «помощь» (пом — помеха в бросках)
        if msg_stripped == "помощь":
            show_help(message_id)
            return
        if msg_stripped.startswith("помощь "):
            show_help(message_id, msg_stripped[7:].strip())
            return

        # Проверяем, находится ли пользователь в каком-либо из процессов (создание персонажа, управление персонажами)

        if user_id in user_states:
            if user_states[user_id]['state'] == 'hpincrease':
                state = user_states[user_id]
                if state['step'] == 1:
                    if message_text == 'да':
                        hitdie = state['character']['hit_die']
                        con_mod = dnd5e_data.calc_mod(state['character']['stats']['constitution'])
                        sign_con = "+" if con_mod >=0 else ""
                        average = hitdie // 2 + 1
                        send_message(f"Ваша Кость здоровья — d{hitdie}. Вы можете кинуть ее и добавить ваш модификатор Выносливости ({sign_con}{con_mod}).\n\nВместо броска взять среднее значение: {average+con_mod}.\n\nТакже можете ввести насколько повысится ваш максимум ПЗ вручную, если бросаете кость вживую (максимум — {hitdie+con_mod})", keyboard_maker(array_to_text_color_array(
                                        ["Кинуть","Среднее","Вручную"]),onetime=True))
                        state['step'] = 2
                        return
                    if message_text == 'нет':
                        exit_state(show_message=False)
                        return
                    else:
                        send_message(f"Выберите \"да\" или \"нет\".",keyboard=keyboard_maker(array_to_text_color_array(["Да","Нет"]),keyboard_columns=2,onetime=True))

                if state['step'] == 2:
                    char = state['character']
                    maxhp = state['character']['max_hit_points']
                    hitdie = char['hit_die']
                    average = hitdie // 2 + 1
                    con_mod = dnd5e_data.calc_mod(char['stats']['constitution'])
                    if message_text == 'кинуть':
                        newmaxhp = roll(char, 1, hitdie, 'вын', has_message=True)
                    elif message_text == 'среднее':
                        newmaxhp = average + con_mod
                    # elif message_text == 'вручную':
                    #     try:
                    #         newmaxhp = int(message_text)
                    #         if newmaxhp <1 or newmaxhp > hitdie + con_mod:
                    #             raise ValueError
                    #     except ValueError:
                    #         send_message(f"Введите значение от 1 до {hitdie + con_mod}")
                    else:
                        send_message(f"Выберите один из вариантов:", keyboard_maker(array_to_text_color_array(
                                        ["Кинуть","Среднее","Вручную"]),onetime=True))
                    newmaxhp+=maxhp
                    change_param(char, 'max_hit_points', newmaxhp)
                    send_message(f"Максимум ПЗ успешно узменен. Новый максимум — {newmaxhp} ПЗ.")
                    exit_state(show_message=False)
                    return


        if chat_id == None:
            if message_text in ['дом','домой','главная','начальный экран','начало']:
                if user_id in user_states:
                    exit_state(show_message=False)
                main_menu_message()
                return
        if user_id in user_states:
            attachments = event.obj.message.get('attachments', [])
            if user_states[user_id]['state'] == 'choose_edition':
                if message_text == '2014':
                    set_user_edition(user_id, '2014')
                    send_message("Редакция правил: 2014. Создание персонажей будет по правилам 2014 года.", keyboards.main_keyboard)
                    del user_states[user_id]
                elif message_text == '2024':
                    set_user_edition(user_id, '2024')
                    send_message("Редакция правил: 2024. Создание персонажей будет по правилам 2024 года (виды из PHB 2024, без расовых бонусов к характеристикам).", keyboards.main_keyboard)
                    del user_states[user_id]
                elif message_text.lower() == 'назад':
                    send_message("Главное меню:", keyboards.main_keyboard)
                    del user_states[user_id]
                else:
                    send_message("Выберите редакцию: 2014 или 2024.", keyboards.edition_keyboard)
                return
            print(user_states[user_id]['step'])
            if user_states[user_id]['state'] == 'create_character':
                create_character_flow(user_id, user_states[user_id]['step'], message_text, attachments, original_message_text)
            elif user_states[user_id]['state'] == 'manage_character':
                manage_character_flow(user_id, user_states[user_id]['step'], message_text, attachments, original_message_text)

            return

        # Вдохновение: вдох (показать), +вдох (получить), -вдох (переброс последней кости)
        if msg_stripped in ('вдох', '+вдох', '-вдох'):
            try:
                char = load_main_character(user_id)
            except (IndexError, TypeError):
                send_message("Персонаж не подключен. Создайте или выберите персонажа.")
                return
            if msg_stripped == 'вдох':
                send_message("Вдохновение: ✨" if char['inspiration'] else "Вдохновение: нет")
            elif msg_stripped == '+вдох':
                change_param(char, 'inspiration', True)
                send_message("Вдохновение получено. ✨")
            else:  # -вдох
                if not char['inspiration']:
                    send_message("Вдохновения нет.")
                    return
                last = last_roll_by_user.get(user_id)
                if not last:
                    send_message("Не было броска для переброса. Сначала сделайте бросок (например, проверку или d20).")
                    return
                change_param(char, 'inspiration', False)
                roll(character=last['character'], amount=last['amount'], die=last['die'], skill_name=last['skill_name'],
                     custom_mod=last['custom_mod'], has_message=True, adv=last['adv'], user_id=user_id)
            return

        # Сложные формулы: несколько костей (d20+d4) или несколько модификаторов (3d20+4+8 → 3d20+12)
        parsed = parse_complex_dice(message_text)
        if parsed:
            dice_terms, total_mod = parsed
            normalized = message_text.replace(" ", "").replace("к", "d").replace("д", "d")
            use_complex = len(dice_terms) > 1 or "+" in normalized
            if use_complex:
                roll_complex_dice(dice_terms, total_mod, has_message=True)
                return

        if is_xdy_format(message_text): #обработка броска кубиков
            parts = message_text.split('d')
            if len(parts) < 2:
                parts = message_text.split('к')
            if len(parts) < 2:
                parts = message_text.split('д')
            try:
                try:
                    amount = int(parts[0])
                except ValueError:
                    amount = 1
                if '+' in parts[1] or '-' in parts[1]:
                    diemod = parts[1].replace(" ", "")
                    i = diemod.find('+')
                    sign = 1
                    if i == -1:
                        i = diemod.find('-')
                        sign = -1
                    die = int(diemod[0:i])
                    mod = int(diemod[i+1:]) * sign
                else:
                    mod = 0
                    die = int(parts[1])

                characters = load_characters(user_id)
                roll(characters[get_main_char_id(user_id) - 1], amount, die, has_message=True, custom_mod = mod, user_id=user_id)
                return
            except ValueError:
                send_message("Пожалуйста, введите правильное значение кости в формате XdY.", keyboards.main_keyboard)
            except IndexError:
                if not user_id in user_warnings:
                    send_message("Персонаж не подключен. Создайте персонажа, чтобы роллить с учетом его характеристик.")
                    user_warnings[user_id] = ''
                roll(character='none', amount=amount, die=die, has_message=True, custom_mod=mod, user_id=user_id)
                return
            return
        
        # Бросок по испытанию: раздельные команды «исп лвк», «исп ловкость», «испытание муд» и т.д.
        _roll_words = msg_stripped.split()
        if len(_roll_words) == 2 and _roll_words[0] in ('исп', 'испытание'):
            _trial_map = {
                'сил': 'испсил', 'сила': 'испсил',
                'лвк': 'исплвк', 'лов': 'исплвк', 'ловкость': 'исплвк',
                'вын': 'испвын', 'выносливость': 'испвын',
                'инт': 'испинт', 'интеллект': 'испинт',
                'мдр': 'испмдр', 'муд': 'испмдр', 'мудр': 'испмдр', 'мудрость': 'испмдр',
                'хар': 'испхар', 'харизма': 'испхар',
            }
            _skill_key = _trial_map.get(_roll_words[1])
            if not _skill_key:
                _skill_key = None
        else:
            _skill_key = None

        if _skill_key:
            try:
                characters = load_characters(user_id)
                roll(characters[get_main_char_id(user_id) - 1], skill_name=_skill_key, has_message=True, user_id=user_id)
            except IndexError:
                if user_id not in user_warnings:
                    send_message("Персонаж не подключен. Создайте персонажа, чтобы роллить с учетом его характеристик.", keyboard=keyboards.main_keyboard)
                    user_warnings[user_id] = ''
                roll(character='none', amount=1, die=20, has_message=True, user_id=user_id)
            return
        elif message_text in dnd5e_data.code_word_list:
            if not ('пом' in message_text or 'пре' in message_text):
                if message_text in ['ини', 'иниц', 'инициатива']:
                    roll_initiative_with_companions(user_id)
                    return
                try:
                    characters = load_characters(user_id)
                    roll(characters[get_main_char_id(user_id) - 1], skill_name=message_text, has_message=True, user_id=user_id)
                    return
                except IndexError:
                    if not user_id in user_warnings:
                        send_message("Персонаж не подключен. Создайте персонажа, чтобы роллить с учетом его характеристик.", keyboard=keyboards.main_keyboard)
                        user_warnings[user_id] = ''
                    roll(character='none', amount=1, die=20, has_message=True, user_id=user_id) 
                    return   

        # Помеха/преимущество: поддерживаем как слитно (прелов), так и раздельно (пре лов / пре исп лвк)
        # Важно: если формат не распознан — не делаем fallback в другой бросок.
        _adv_words = msg_stripped.split()
        _adv_prefix = None
        _adv_handled = False
        if _adv_words and _adv_words[0] in ('пом', 'пре'):
            _adv_prefix = _adv_words[0]
        else:
            _joined = msg_stripped.replace(" ", "")
            if _joined.startswith('пом') and _joined != 'помощь':
                _adv_prefix = 'пом'
            elif _joined.startswith('пре'):
                _adv_prefix = 'пре'

        if _adv_prefix in ('пом', 'пре'):
            try:
                adv = _adv_prefix

                # 1) Раздельный формат: пре исп <...> / пом испытание <...>
                # Поддерживаем:
                # - Испытания: пре исп лвк / пом испытание мудрость
                # - Проверки/навыки: пре исп лрк / пре исп ловрук / пре исп ловкость рук
                if len(_adv_words) >= 3 and _adv_words[0] == adv and _adv_words[1] in ('исп', 'испытание'):
                    _trial_map = {
                        'сил': 'испсил', 'сила': 'испсил',
                        'лвк': 'исплвк', 'лов': 'исплвк', 'ловкость': 'исплвк',
                        'вын': 'испвын', 'выносливость': 'испвын',
                        'инт': 'испинт', 'интеллект': 'испинт',
                        'мдр': 'испмдр', 'муд': 'испмдр', 'мудр': 'испмдр', 'мудрость': 'испмдр',
                        'хар': 'испхар', 'харизма': 'испхар',
                    }
                    # Сначала пробуем как испытание по одной характеристике (ровно 3 слова)
                    if len(_adv_words) == 3 and _adv_words[2] in _trial_map:
                        skill_tag = _trial_map[_adv_words[2]]
                    else:
                        # Иначе — пробуем как проверку/навык: одно слово или несколько (например "ловкость рук")
                        skill_phrase = " ".join(_adv_words[2:]).strip()
                        if skill_phrase in dnd5e_data.code_word_list:
                            skill_tag = skill_phrase
                        elif len(_adv_words) == 3 and _adv_words[2] in dnd5e_data.code_word_list:
                            skill_tag = _adv_words[2]
                        else:
                            send_message("Команда не распознана.", keyboard=keyboards.main_keyboard)
                            return

                    try:
                        characters = load_characters(user_id)
                        roll(characters[get_main_char_id(user_id) - 1], skill_name=skill_tag, has_message=True, adv=adv, user_id=user_id)
                    except IndexError:
                        if user_id not in user_warnings:
                            send_message("Персонаж не подключен. Создайте персонажа, чтобы роллить с учетом его характеристик.", keyboard=keyboards.main_keyboard)
                            user_warnings[user_id] = ''
                        roll(character='none', amount=1, die=20, has_message=True, adv=adv, user_id=user_id)
                    return

                # 2) Раздельный формат проверок навыка/характеристики: пре лов / пом про / пре акр / т.п.
                if len(_adv_words) == 2 and _adv_words[0] == adv:
                    skill_tag = _adv_words[1]
                    if skill_tag in dnd5e_data.code_word_list:
                        try:
                            characters = load_characters(user_id)
                            roll(characters[get_main_char_id(user_id) - 1], skill_name=skill_tag, has_message=True, adv=adv, user_id=user_id)
                        except IndexError:
                            if user_id not in user_warnings:
                                send_message("Персонаж не подключен. Создайте персонажа, чтобы роллить с учетом его характеристик.", keyboard=keyboards.main_keyboard)
                                user_warnings[user_id] = ''
                            roll(character='none', amount=1, die=20, has_message=True, adv=adv, user_id=user_id)
                        return
                    send_message("Команда не распознана.", keyboard=keyboards.main_keyboard)
                    return

                # 3) Слитный формат (без пробелов): прелов / помпро / пре+5 / пом-2
                _joined = msg_stripped.replace(" ", "")
                if _joined.startswith(adv):
                    rest = _joined[len(adv):]
                    # модификатор без кода: пре+5 / пом-2
                    if rest and (rest[0] in '+-' or rest.isdigit()):
                        try:
                            mod = int(rest)
                        except ValueError:
                            send_message("Команда не распознана.", keyboard=keyboards.main_keyboard)
                            return
                        roll(character='none', die=20, has_message=True, adv=adv, custom_mod=mod, user_id=user_id)
                        return
                    # пре<код>
                    if rest in dnd5e_data.code_word_list:
                        try:
                            characters = load_characters(user_id)
                            roll(characters[get_main_char_id(user_id) - 1], skill_name=rest, has_message=True, adv=adv, user_id=user_id)
                        except IndexError:
                            if user_id not in user_warnings:
                                send_message("Персонаж не подключен. Создайте персонажа, чтобы роллить с учетом его характеристик.", keyboard=keyboards.main_keyboard)
                                user_warnings[user_id] = ''
                            roll(character='none', amount=1, die=20, has_message=True, adv=adv, user_id=user_id)
                        return

                send_message("Команда не распознана.", keyboard=keyboards.main_keyboard)
                return

            except (ValueError, KeyError):
                send_message("Команда не распознана.", keyboard=keyboards.main_keyboard)
                return
        try:
            # Ячейки заклинаний: -яч 1 / -яч1 (потратить), +яч 1 2 (восстановить). Для колдуна: +яч / -яч / +яч 2 (без круга).
            _msg = message_text.strip().lower()
            if _msg.startswith('-яч') or _msg.startswith('+яч'):
                sign = -1 if _msg[0] == '-' else 1
                rest = _msg[1:].strip()  # "яч 1 2" или "яч1 2" или "яч" или "яч 2"
                if not rest.startswith('яч'):
                    send_message("Команда не распознана.", keyboard=keyboards.main_keyboard)
                    return
                rest = rest[2:].strip()  # "1 2" / "1" / "" / "2"
                try:
                    char = load_main_character(user_id)
                except (IndexError, TypeError):
                    send_message("Персонаж не подключен.", keyboard=keyboards.main_keyboard)
                    return
                is_warlock = (char.get('class') or '').lower() == 'колдун'
                parts = rest.split() if rest else []

                if is_warlock and (len(parts) == 0 or len(parts) == 1):
                    # Колдун: +яч / -яч (1 ячейка) или +яч 2 / -яч 2 (количество)
                    amount = int(parts[0]) if len(parts) == 1 else 1
                    if amount < 1:
                        send_message("Количество — не менее 1.", keyboard=keyboards.main_keyboard)
                        return
                    level = max(1, min(20, int(char.get('level', 1))))
                    # Таблица колдуна: уровень -> (круг ячеек, макс. ячеек). PHB 5e.
                    if level == 1:
                        circle, max_for_circle = 1, 1
                    elif level == 2:
                        circle, max_for_circle = 1, 2
                    elif level <= 4:
                        circle, max_for_circle = 2, 2
                    elif level <= 6:
                        circle, max_for_circle = 3, 2
                    elif level <= 8:
                        circle, max_for_circle = 4, 2
                    elif level <= 10:
                        circle, max_for_circle = 5, 2
                    elif level <= 16:
                        circle, max_for_circle = 5, 3
                    else:
                        circle, max_for_circle = 5, 4
                    try:
                        curr = char['current_spell_slots']
                        max_slots = char['spell_slots']
                    except KeyError:
                        char['spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                        char['current_spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                        curr = char['current_spell_slots']
                        max_slots = char['spell_slots']
                    while len(max_slots) <= circle:
                        max_slots.append(0)
                    max_slots[circle] = max_for_circle
                    cur_val = curr[circle] if circle < len(curr) else 0
                    new_val = cur_val + sign * amount
                    new_val = max(0, min(max_for_circle, new_val))
                    if circle >= len(curr):
                        while len(curr) <= circle:
                            curr.append(0)
                    curr[circle] = new_val
                    char['current_spell_slots'] = curr
                    char['spell_slots'] = max_slots
                    change_param(char, 'current_spell_slots', curr)
                    change_param(char, 'spell_slots', max_slots)
                    send_message(f"Ячейки колдуна ({circle}-й круг): теперь {new_val} из {max_for_circle}.")
                    return

                if not rest:
                    send_message("Укажите круг (1–9), например: -яч 1 или +яч 1 2. Колдун: -яч / +яч без числа.", keyboard=keyboards.main_keyboard)
                    return
                try:
                    circle = int(parts[0])
                    amount = int(parts[1]) if len(parts) > 1 else 1
                except (ValueError, IndexError):
                    send_message("Команда не распознана. Формат: -яч 1 (потратить), +яч 1 2 (восстановить 2 ячейки 1 круга).", keyboard=keyboards.main_keyboard)
                    return
                if circle < 1 or circle > 9 or amount < 1:
                    send_message("Круг — от 1 до 9, количество — не менее 1.", keyboard=keyboards.main_keyboard)
                    return
                try:
                    curr = char['current_spell_slots']
                    max_slots = char['spell_slots']
                except KeyError:
                    char['spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                    char['current_spell_slots'] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                    curr = char['current_spell_slots']
                    max_slots = char['spell_slots']
                max_for_circle = max_slots[circle] if circle < len(max_slots) else 0
                if max_for_circle == 0:
                    send_message(f"У персонажа нет ячеек {circle}-го круга.", keyboard=keyboards.main_keyboard)
                    return
                cur_val = curr[circle] if circle < len(curr) else 0
                new_val = cur_val + sign * amount
                new_val = max(0, min(max_for_circle, new_val))
                curr[circle] = new_val
                char['current_spell_slots'] = curr
                change_param(char, 'current_spell_slots', curr)
                send_message(f"Ячейки {circle}-го круга: теперь {new_val} из {max_for_circle}.")
                return

            # Команда «сн очистить …» / «сн очисть …» / «сн очист …» — удалить ВСЕ предметы с указанным названием (по имени)
            _msg_lower = message_text.strip().lower()
            equipment_cmd_handled = False
            clear_prefixes = (
                'снаряжение очистить ', 'снаряжение очисть ', 'снаряжение очист ',
                'экипировка очистить ', 'экипировка очисть ', 'экипировка очист ',
                'снар очистить ', 'снар очисть ', 'снар очист ',
                'экип очистить ', 'экип очисть ', 'экип очист ',
                'сн очистить ', 'сн очисть ', 'сн очист ',
            )
            for prefix in clear_prefixes:
                if _msg_lower.startswith(prefix):
                    rest = message_text.strip()[len(prefix):].strip()
                    if rest:
                        try:
                            char = load_main_character(user_id)
                            characters = load_characters(user_id)
                            names = [s.strip() for s in rest.split(',') if s.strip()]
                            if not names:
                                send_message("Укажите название предмета, например: сн очистить зелье лечение", keyboard=keyboards.main_keyboard)
                            else:
                                deleted, not_found = delete_equipment_by_name_all(char, names)
                                replace_char(char, characters)
                                write_characters(user_id, characters)
                                msg = f"Удалено предметов: {deleted}."
                                if not_found:
                                    msg += "\n" + "\n".join(not_found)
                                send_message(msg, keyboard=keyboards.main_keyboard)
                                show_equipment(char, show_keyboard=False)
                        except Exception:
                            send_message("Ошибка при очистке. Формат: сн очистить название (удалит все с таким названием).", keyboard=keyboards.main_keyboard)
                    else:
                        send_message("Укажите название предмета, например: сн очистить зелье лечение", keyboard=keyboards.main_keyboard)
                    equipment_cmd_handled = True
                    break
            if not equipment_cmd_handled:
                delete_prefixes = ('снаряжение удалить ', 'снаряжение удал ', 'экипировка удалить ', 'экипировка удал ', 'снар удалить ', 'снар удал ', 'экип удалить ', 'экип удал ', 'сн удалить ', 'сн удал ')
                for prefix in delete_prefixes:
                    if _msg_lower.startswith(prefix):
                        rest = message_text.strip()[len(prefix):].strip()
                        if rest:
                            try:
                                char = load_main_character(user_id)
                                characters = load_characters(user_id)
                                parsed_items = parse_equipment_bulk(rest)
                                if not parsed_items:
                                    send_message("Не найдено ни одного предмета. Укажите что удалить: сн удал 5 Кинжал, рубин (50 зм)", keyboard=keyboards.main_keyboard)
                                else:
                                    deleted, errors = delete_equipment_bulk(char, parsed_items)
                                    replace_char(char, characters)
                                    write_characters(user_id, characters)
                                    msg = f"Удалено предметов: {deleted}."
                                    if errors:
                                        msg += "\n" + "\n".join(errors)
                                    send_message(msg, keyboard=keyboards.main_keyboard)
                                    show_equipment(char, show_keyboard=False)
                            except Exception:
                                send_message("Ошибка при удалении. Формат: сн удал название [кол-во] [вес] [стоимость]. Совпадение по названию и стоимости.", keyboard=keyboards.main_keyboard)
                        else:
                            send_message("Укажите предметы для удаления, например: сн удал 5 Кинжал, рубин (50 зм)", keyboard=keyboards.main_keyboard)
                        equipment_cmd_handled = True
                        break
            if not equipment_cmd_handled:
                for prefix in ('снаряжение ', 'экипировка ', 'снар ', 'экип ', 'сн '):
                    if _msg_lower.startswith(prefix):
                        rest = message_text.strip()[len(prefix):].strip()
                        if rest:
                            try:
                                char = load_main_character(user_id)
                                characters = load_characters(user_id)
                                parsed_items = parse_equipment_bulk(rest)
                                if not parsed_items:
                                    send_message("Не найдено ни одного предмета. Формат: 5 Кинжал, рубин (50 зм), ложка 1 фунт", keyboard=keyboards.main_keyboard)
                                else:
                                    for it in parsed_items:
                                        create_item(char, name=it['name'], amount=it['amount'], cost=it['cost'] if it.get('cost') else None, weight_str=it.get('weight_str', ''))
                                    replace_char(char, characters)
                                    write_characters(user_id, characters)
                                    send_message('Предметы добавлены.')
                                    show_equipment(char, show_keyboard=False)
                            except Exception:
                                send_message("Ошибка при добавлении. Проверьте формат: название [кол-во] [вес] [стоимость].", keyboard=keyboards.main_keyboard)
                        else:
                            char = load_main_character(user_id)
                            show_equipment(char, show_keyboard=False)
                        equipment_cmd_handled = True
                        break
            if equipment_cmd_handled:
                return
            if message_text in dnd5e_data.code_fast_no_value:
                if message_text in ['снар', 'снаряжение', 'сн', 'экип', 'экипировка']:
                    char = load_main_character(user_id)
                    show_equipment(char, show_keyboard=False)
                if message_text in ['ячвосст','восстяч', 'восстановить ячейки']:
                    char = load_main_character(user_id)
                    show_equipment(char, show_keyboard=False)
                if message_text in ['ос','особ', 'особенности']:
                    char = load_main_character(user_id)
                    show_features(char)
                if message_text in ['сл','заклсл', 'сложность испытаний']:
                    char = load_main_character(user_id)
                    send_message(f"Ваша СЛ испытаний для заклинаний: {8 + get_mod(get_spell_stat(char),char) + char['proficiency_bonus']}")
                if message_text in ['закл','заклин','зак', 'заклинания']:
                    char = load_main_character(user_id)
                    show_all_spells(char, show_keyboard=False, ttg_msg = False)
                if message_text in ['деньги','монеты','мон']:
                    money = money_message(load_main_character(user_id))
                    send_message(money)
                if message_text in ['долгий отдых','до']:
                    char = load_main_character(user_id)
                    hitpoints = char['max_hit_points']
                    spellslots = char['spell_slots']
                    hitdice = char['hit_dice_count']
                    hitdicenew = char['hit_dice_max'] // 2
                    if hitdice == 0:
                        hitdice = 1
                    hitdice += hitdicenew
                    if hitdice > char['hit_dice_max']:
                        hitdice = char['hit_dice_max']
                    change_param(char, 'hit_points', hitpoints)
                    change_param(char, 'hit_dice_count', hitdice)
                    change_param(char, 'current_spell_slots', spellslots)
                    send_message(f"Вы совершаете долгий отдых.\n\nВсе ваши ПЗ и ячейки заклинаний восстанавливаются. Вы также восстанавливаете половину ваших КЗ (минимум 1). \n\nТеперь у вас {hitdice}/{char['hit_dice_max']} КЗ.")
                if message_text in ['короткий отдых','ко']:
                    char = load_main_character(user_id)
                    send_message(f"Вы совершаете короткий отдых и можете потратить {char['hit_dice_count']} КЗ, чтобы восстановить здоровье. \n\nНапишите /ко [количество КЗ], которое вы хотите потратить. Ваше здоровье восстановится после автоматичесткого броска.")
                if message_text in ['lvlup','лвлап','повышение','повыш','новый уровень','новур']:
                    char = load_main_character(user_id)
                    lvl = char['level']
                    if lvl == 20:
                        send_message("Вы уже максимального уровня.")
                    elif lvl > 1 or lvl < 20:
                        change_param(char,'level',lvl+1)
                        hit_dice_new_curr = char['hit_dice_count'] + 1
                        newbonus = dnd5e_data.proficiency_bonus(lvl+1)
                        change_param(char,'proficiency_bonus',newbonus)
                        change_param(char,'hit_dice_max',lvl+1)
                        change_param(char,'hit_dice_count',hit_dice_new_curr)
                        send_message(f"Уровень успешно повышен. Теперь вы {lvl+1} уровня. Хотите ли изменить максимум пунктов здоровья?",keyboard=keyboard_maker(array_to_text_color_array(["Да","Нет"]),keyboard_columns=2,onetime=True))
                        user_states[user_id] = {'character': char, 'state': 'hpincrease', 'step': 1}
                return
            elif message_text == 'я':
                try:
                    char = load_main_character(user_id)
                    message = char_sheet_message(char)
                    attachment, temp_path = character_image_for_send(char)
                    send_message(message, attachment=attachment)
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
                except Exception:
                    send_message("Не удалось загрузить персонажа. Проверьте, что выбран основной персонаж.")
                return
            elif message_text == 'лист':
                sheet_path = None
                portrait_path = None
                try:
                    char = load_main_character(user_id)
                    if char.get('image'):
                        portrait_path = download_character_photo(char['image'], image_url=char.get('image_url'))
                    sheet_path = character_sheet_image.generate_character_sheet_image(char, portrait_path=portrait_path)
                    if current_platform == 'telegram':
                        send_message("Лист персонажа:", attachment=sheet_path)
                    else:
                        peer_id = (2000000000 + message_id) if chat_id is not None else message_id
                        photo_list = vk_upload.photo_messages(sheet_path, peer_id=peer_id)
                        if photo_list and len(photo_list) > 0:
                            att = f"photo{photo_list[0]['owner_id']}_{photo_list[0]['id']}"
                            send_message("Лист персонажа:", attachment=att)
                        else:
                            send_message(char_sheet_message(char))
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    try:
                        char = load_main_character(user_id)
                        send_message(char_sheet_message(char))
                    except Exception:
                        send_message("Не удалось загрузить персонажа или сформировать лист. Проверьте, что выбран основной персонаж.")
                    print(f"Генерация листа персонажа (картинка): {e}")
                finally:
                    if sheet_path and os.path.exists(sheet_path):
                        try:
                            os.remove(sheet_path)
                        except OSError:
                            pass
                    if portrait_path and os.path.exists(portrait_path) and portrait_path != sheet_path:
                        try:
                            os.remove(portrait_path)
                        except OSError:
                            pass
                return
            elif message_text == 'навыки':
                show_all_skills(load_main_character(user_id),horizontal_format=True, show_all=True)
                return

            elif message_text[0:2] in dnd5e_data.code_fast_value:
                if len(message_text)>2:
                    parts = message_text.split(' ')
                    original_parts = original_message_text.split(' ')
                    original_value = original_parts[1][0:]
                    if len(parts) > 2:
                        for i in range(2, len(parts)):
                            if not (parts[i][0] =='+' or parts[i][0] =='-' or  parts[i].isdigit()):
                                original_value+=' ' + parts[i]
                    sign = ''
                    value = ''
                    sign2 = ''
                    value2 = ''

                    word2 = parts[-1]
                    if len(parts) > 2 and (word2[0] == '+' or word2[0] == '-' or word2.isdigit()):
                        sign2 = word2[0]
                        if sign2 == '+' or sign2 == '-':
                            value2 = word2[1:]
                        if sign2.isdigit():
                            value2 = word2[0:]
                            sign2 = ''
                        if (not value2.isdigit()) or original_value[0] == '+' or original_value[0] == '-':
                            send_message("Неверный формат бонуса.")
                            return
                    if len(parts) <1:
                        send_message("Неверный формат бонуса.")
                        return
                    
                    
                    code = parts[0]
                    sign = parts[1][0]
                    if sign == '+' or sign == '-':
                        value = parts[1][1:]
                    else:
                        value = parts[1][0:]
                        sign = ''
                    
                    
                    if value.isdigit():
                        try:
                            value = int(value)
                        except ValueError:
                            send_message("Неверный формат бонуса.")
                            return
                        except IndexError:
                            send_message("Неверный формат бонуса.")
                            return
            
                    if sign == '-':
                        value = value * -1
                    elif sign != '+' and sign !='':
                        send_message("Неверный формат бонуса.")
                        return
                    if code in ['кб']:
                        char = load_main_character(user_id)
                        if value >= 0:
                            change_param(char,'armor_class', value)
                            send_message(f"Ваш новый КБ — {value}.")
                        else:
                            send_message("КБ не может быть меньше 0.")
                    if code in ['зм','пм','эм','см','мм']:
                        add_money(load_main_character(user_id),type=code,value=value,show_message=True)
                    if code in ['ос']:
                        show_desc_feature(load_main_character(user_id), value)
                    if code in ['сн']:
                        char = load_main_character(user_id)
                        if sign2 == '-':
                            delete = True
                        else: 
                            delete = False
                        if value2 == '':
                            value2 = 1
                        else:
                            value2 = int(value2)
                        check = create_item(char, name=original_value, amount=value2, delete=delete)
                        if check == 1:
                            replace_char(char, load_characters(user_id))
                            if delete == False:
                                send_message(f"Вы добавили в инвентарь предмет «{original_value}» в количестве {value2}.")
                            else:
                                send_message(f"Вы убрали из инвентаря предмет «{original_value}» в количестве {value2}.")
                        elif check == -1:
                            return
                    if code in ['ко']:
                        char = load_main_character(user_id)
                        hp = char['hit_points']
                        hitdie = char['hit_die']
                        average = hitdie // 2 + 1
                        con_mod = dnd5e_data.calc_mod(char['stats']['constitution'])
                        if value > char['hit_dice_count'] or value < 1:
                            send_message("Неправильное количество КЗ.")
                            return
                        newhp = 0
                        for i in range(value):
                            newhp += roll(char, 1, hitdie, 'вын', has_message=True, user_id=user_id)

                        # elif message_text == 'вручную':
                        #     try:
                        #         newmaxhp = int(message_text)
                        #         if newmaxhp <1 or newmaxhp > hitdie + con_mod:
                        #             raise ValueError
                        #     except ValueError:
                        #         send_message(f"Введите значение от 1 до {hitdie + con_mod}")
                        newhp
                        sumhp = newhp + hp
                        if sumhp > char['max_hit_points']:
                            sumhp = char['max_hit_points']
                        change_param(char, 'hit_dice_count', char['hit_dice_count'] - value)
                        change_param(char, 'hit_points', sumhp)
                        send_message(f"Вы прибавляете {newhp} к вашем текущим {hp} ПЗ.\n\nТеперь у вас {sumhp} из {char['max_hit_points']} ПЗ.")
                    if code in ['пз','хп']:
                        char = load_main_character(user_id)
                        newhp= char['hit_points'] + value
                        if newhp < 0:
                            newhp = 0
                            #send_message('Вы падаете без сознания!')
                        if newhp > char['max_hit_points']:
                            newhp = char['max_hit_points']
                        change_param(char,'hit_points', newhp)
                        send_message(f"У вас теперь {newhp} из {char['max_hit_points']} ПЗ.")
                    if code in ['яч']:
                        send_message("Используйте формат: -яч 1 (потратить 1 ячейку 1 круга), +яч 1 2 (восстановить 2 ячейки 1 круга). Только «яч» — показать ячейки.", keyboard=keyboards.main_keyboard)
                    if code in ['кз']:
                        char = load_main_character(user_id)
                        newhd= char['hit_dice_count'] + value
                        if newhd < 0:
                            newhd = 0
                            #send_message('Вы падаете без сознания!')
                        if newhd > char['hit_dice_max']:
                            newhd = char['hit_dice_max']
                        change_param(char,'hit_dice_count', newhd)
                        charhdmax = load_main_character(user_id)['hit_dice_max']
                        charhdie = load_main_character(user_id)['hit_die']
                        send_message(f"У вас {newhd} из {charhdmax} КЗ (d{charhdie}).")
                    if code in ['по','оп']:
                        char = load_main_character(user_id)
                        newxp= char['xp'] + value
                        if newxp < 0:
                            newxp = 0
                            #send_message('Вы падаете без сознания!')
                        change_param(char,'xp', newxp)
                        charxp = char['xp']
                        charlvl = char['level']
                        if charlvl <20:
                            send_message(f"У вас теперь {charxp} из {dnd5e_data.xp_threshold[charlvl]} ПО (нужных для {charlvl+1} уровня).")
                        else:
                            send_message(f"У вас {charxp} ПО. Вы достигли 20 уровня.")
                    if code in ['вр','вз']:
                        char = load_main_character(user_id)
                        newthp= char['temp_hit_points'] + value
                        if newthp < 0:
                            newthp = 0
                            #send_message('Вы падаете без сознания!')
                        change_param(char,'temp_hit_points', newthp)
                        send_message(f"У вас теперь {newthp} временных ПЗ.")
                else:
                    if message_text in ['кб']:
                        charac = load_main_character(user_id)['armor_class']
                        send_message(f"Ваш КБ — {charac}.")
                    if message_text in ['яч']:
                        char = load_main_character(user_id)
                        show_current_spell_slots(char)
                    if message_text in ['зм','пм','эм','см','мм']:
                        charmoney = load_main_character(user_id)['money'][f'{message_text}']
                        send_message(f"У вас {charmoney} {message_text}.")
                    if message_text in ['пз','хп']:
                        char = load_main_character(user_id)
                        charhp = char['hit_points']
                        charmaxhp = char['max_hit_points']
                        send_message(f"У вас {charhp} из {charmaxhp} ПЗ.")
                    if message_text in ['по','оп']:
                        char = load_main_character(user_id)
                        charxp = char['xp']
                        charlvl = char['level']
                        if charlvl <20:
                            send_message(f"У вас {charxp} из {dnd5e_data.xp_threshold[charlvl]} ПО (нужных для {charlvl+1} уровня).")
                        else:
                            send_message(f"У вас {charxp} ПО. Вы достигли 20 уровня.")
                    if message_text in ['кз']:
                        charhd = load_main_character(user_id)['hit_dice_count']
                        charhdmax = load_main_character(user_id)['hit_dice_max']
                        charhdie = load_main_character(user_id)['hit_die']
                        send_message(f"У вас {charhd} из {charhdmax} КЗ (d{charhdie}).")
                    if message_text in ['вр','вз']:
                        charthp = load_main_character(user_id)['temp_hit_points']
                        send_message(f"У вас {charthp} временных ПЗ.")
                return
        except ValueError:
            send_message("Персонаж не подключен. Создайте персонажа, чтобы использовать эту функцию.")
            return
        except KeyError:
            send_message("Персонаж не подключен. Создайте персонажа, чтобы использовать эту функцию.")
            return
        except IndexError:
            send_message("Персонаж не подключен. Создайте персонажа, чтобы использовать эту функцию.")
            return

        if message_text in ['закрыть клавиатуру','закрклав','-клав','-кл','зкл']:
            send_message("Клавиатура закрыта.", remove_keyboard=(current_platform == 'telegram'))
            return

        elif chat_id == None:
            if  message_text == "создать персонажа" or message_text == "создать":
                create_character_flow(user_id, 1, "")

            elif message_text == "мои персонажи":
                manage_character_flow(user_id, 1, "")

            elif message_text.lower() == "редакция":
                user_states[user_id] = {'state': 'choose_edition'}
                current = get_user_edition(user_id)
                send_message(f"Текущая редакция: {current}. Выберите редакцию правил (2014 или 2024). В 2024 доступны виды из PHB 2024, расовые бонусы к характеристикам не применяются.", keyboards.edition_keyboard)

            elif message_text == "помощь":
                show_help(message_id)

            elif message_text.startswith("помощь "):
                show_help(message_id, message_text[7:].strip())

            elif message_text == "привет" or message_text == "начать":
                send_message("Привет! Я бот для создания персонажей D&D 5e. Чем могу помочь?", keyboards.main_keyboard)

            else:
                send_message("Команда не распознана.", keyboard=keyboards.main_keyboard)

        # Обработка команд, доступных в личке бота


def init_vk():
    global vk_session, longpoll, vk, vk_upload
    if not TOKEN:
        raise RuntimeError('VK_TOKEN is not set')
    vk_session = vk_api.VkApi(token=TOKEN)
    longpoll = VkBotLongPoll(vk_session, int(GROUP_ID))
    vk = vk_session.get_api()
    vk_upload = VkUpload(vk_session)


def run_vk_bot():
    global current_platform
    init_vk()
    print('VK bot started')
    for vk_event in longpoll.listen():
        with transport_lock:
            current_platform = 'vk'
            handle_bot_event(vk_event)


def run_telegram_bot():
    global current_platform, telegram_chat_id, telegram_message_id, chat_id, user_id, message_id
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is not set')
    try:
        telegram_api('deleteWebhook', drop_pending_updates=True)
        print('Telegram webhook cleared, long polling enabled')
    except Exception as exc:
        print('Telegram deleteWebhook warning:', exc)
    offset = None
    print('Telegram bot started')
    while True:
        params = {'timeout': 30}
        if offset is not None:
            params['offset'] = offset
        try:
            updates = telegram_api('getUpdates', **params)
            for update in updates:
                offset = update['update_id'] + 1
                if update.get('callback_query'):
                    continue
                message = update.get('message') or update.get('edited_message')
                if not message:
                    continue
                text = message.get('text') or message.get('caption') or ''
                chat = message.get('chat') or {}
                is_private = chat.get('type') == 'private'
                mentioned = TELEGRAM_BOT_USERNAME and f'@{TELEGRAM_BOT_USERNAME}' in text.lower()
                if not is_private and not (text.startswith(symbol) or mentioned):
                    continue
                with transport_lock:
                    current_platform = 'telegram'
                    telegram_chat_id = chat.get('id')
                    telegram_message_id = message.get('message_id')
                    handle_bot_event(_TelegramEvent(update))
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 409:
                print(
                    'Telegram polling error: 409 Conflict — '
                    'уже работает другой экземпляр бота с этим токеном. '
                    'Остановите все другие копии (терминалы, сервер, VK+TG одновременно в двух процессах).'
                )
            else:
                print('Telegram polling error:', exc)
            time.sleep(5)
        except Exception as exc:
            print('Telegram polling error:', exc)
            time.sleep(5)


def run_selected_bots():
    platforms = {part.strip() for part in BOT_PLATFORM.replace('+', ',').split(',') if part.strip()}
    if not platforms:
        platforms = {'vk'}
    threads = []
    if 'vk' in platforms or 'both' in platforms:
        thread = threading.Thread(target=run_vk_bot, daemon=False)
        thread.start()
        threads.append(thread)
    if 'telegram' in platforms or 'tg' in platforms or 'both' in platforms:
        thread = threading.Thread(target=run_telegram_bot, daemon=False)
        thread.start()
        threads.append(thread)
    if not threads:
        raise RuntimeError(f'Unknown BOT_PLATFORM: {BOT_PLATFORM}')
    for thread in threads:
        thread.join()


if __name__ == '__main__':
    run_selected_bots()
