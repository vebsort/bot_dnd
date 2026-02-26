import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import random
import json
import os
import dnd5e_data

import keyboards #импорт клавиатур
from dnd_character_generator import generate_character # Это ваш модуль для генерации персонажей

# Настройки бота
GROUP_ID = '179538565'
TOKEN = 'vk1.a.Gntrp6vhQlJziwlEvLLjdukd2V3jbJW0BAwU19plh7Xmwf3EoDeypRyP-M5AsdcjOrb81e98s9HdGq1nbDnHjIevKn1qj-l5TOteOGS86jdDjDEPD_mV4nGKELzu9Amr0ExDI1q6YjYRKO4heMN1QjegoDwatNIPlAnRKLOuz40koSjYX6Llhzcy6XBN0eXHl5YS_rj1Ix5_fglGiEuMWg'

symbol = '/'

# Инициализация API ВКонтакте
vk_session = vk_api.VkApi(token=TOKEN)
longpoll = VkBotLongPoll(vk_session, GROUP_ID)
vk = vk_session.get_api()

# Состояния пользователей (для простой машины состояний)
user_states = {}
user_warnings = {}


#функция отправки сообщения (в зависимости от лички/беседы меняет параметры)
def send_message(message, keyboard=None): 
    """Отправляет сообщение пользователю"""
    if event.chat_id != None:
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
    if keyboard:
        params['keyboard'] = json.dumps(keyboard)
    
    vk.messages.send(**params)

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
        numbered_keyboard_array[keyboard_rows+1].append({ #добавление кнопки назад на последнюю строку
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


def subrace_keyboard_array_maker(race):
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
        button_array = subrace_keyboard_array_maker(user_states[user_id]['character']['race'])
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

def get_prof_string(character, profkey = 'prof_mult_dict', is_saving_throw = False, horizontal_format = False, show_all = False):
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
            if mod >= 0:
                text += f'{i} +{mod}, '
            else:
                text += f'{i} {mod}, '
        if horizontal_format == True:
            text = text[:-2] + "\n"
    if horizontal_format == False:
        text = text[:-2]
    return text

def show_all_skills(character, horizontal_format=True, show_all=True):
    message = get_prof_string(character, horizontal_format=True, show_all=True)
    send_message(message)
    
def change_param(character, param, value, characters='none'):
    if characters == 'none':
        characters = load_characters(user_id)
    character[param] = value
    replace_char(character, characters)

def money_sum(money_dict):
    return round(money_dict['пм']*10 + money_dict['зм'] + money_dict['эм'] / 2 + money_dict['см'] /10 + money_dict['мм']/100, 2)

def create_item(character, name, desc='', amount=1, value=0, valuetype='зм', weight=0, itemtype='none', damage='none', damagetype='none'):
    equipment_list = character['equipment']
    equipment_list.append({
        'id': len(equipment_list),
        'name': name,
        'desc': desc,
        'amount': amount,
        'value': value,
        'valuetype': valuetype,
        'weight': weight,
        'itemtype': itemtype,
        'damage': damage,
        'damagetype': damagetype,     
    })


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
        'id': len(spell_list),
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

def show_equipment(character, show_keyboard=True):
    equipment_list = character['equipment']
    money_dict = character['money']
    message = 'Снаряжение:\n\n'
    message += f"---Монеты---\n" \
            f"Платина: {money_dict['пм']}\n" \
            f"Золото: {money_dict['зм']}\n" \
            f"Электрум: {money_dict['эм']}\n" \
            f"Серебро: {money_dict['см']}\n" \
            f"Медь: {money_dict['мм']}\n\n" \
            f"Всего в золоте: {money_sum(money_dict)} зм\n\n"

    message += '---Предметы---\n'
    item_count = 0

    for i in range(len(equipment_list)):
        if equipment_list[i]['itemtype'] == 'оружие':
            item_count += 1
            message += f"{item_count}. {equipment_list[i]['name']}\n"
            equipment_list[i]['id'] = item_count
    if item_count > 0:
        message += "\n"

    for i in range(len(equipment_list)):
        if equipment_list[i]['itemtype'] == 'броня':
            item_count += 1
            message += f"{item_count}. {equipment_list[i]['name']}\n"
            equipment_list[i]['id'] = item_count   
    if item_count > 0:
        message += "\n"

    for i in range(len(equipment_list)):
        if equipment_list[i]['itemtype'] == 'магия':
            item_count += 1
            message += f"{item_count}. {equipment_list[i]['name']}\n"
            equipment_list[i]['id'] = item_count
    if item_count > 0:
            message += "\n"
    
    for i in range(len(equipment_list)):
        if equipment_list[i]['itemtype'] == 'none':
            item_count += 1
            message += f"{item_count}. {equipment_list[i]['name']}\n"
            equipment_list[i]['id'] = item_count

    if show_keyboard == True:            
        message += "\nВведите номер предмета:"
        send_message(message, keyboard_maker([["Монеты", "primary"],["Новый предмет", "primary"],["Удаление предметов", "secondary"]], keyboard_columns=2, hasbackbutton=True))
    else:
        send_message(message)

def get_ttg_link(spellname):
    link = ''
    start = spellname.find('[') + 1  # +1, чтобы не включать '['
    end = spellname.find(']')
    if start != -1 and end != -1:  # Проверяем, что оба символа найдены
        result = spellname[start:end]
        spellwords = result.split(" ")
        for i in range(len(spellwords)):
            link +=spellwords[i]+"_"
        link = link[:-1]
        link = "https://ttg.club/spells/" + link
        return link
    else:
        print("Символы не найдены")

    
    

def show_all_spells(character, show_keyboard=True, ttg_msg=True):
    spell_list = character['known_spells']
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
        message += "\n---1 круг---:\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 1:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count   
    if spells_left > 0:
        message += "\n---2 круг---:\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 2:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if spells_left > 0:
            message += "\n---3 круг---:\n"
    
    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 3:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if spells_left > 0:
            message += "---4 круг---:\n"
    
    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 4:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if spells_left > 0:
            message += "---5 круг---:\n"        

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 5:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if spells_left > 0:
            message += "---6 круг---:\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 6:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
            
    if spells_left > 0:
            message += "---7 круг---:\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 7:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
            
    if spells_left > 0:
            message += "---8 круг---:\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 8:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
            
    if spells_left > 0:
            message += "---9 круг---:\n"

    for i in range(len(spell_list)):
        if spell_list[i]['lvl'] == 9:
            item_count += 1
            spells_left -= 1
            message += f"{item_count}. {spell_list[i]['name']}\n"
            spell_list[i]['id'] = item_count
    if ttg_msg:
        message += "\nВведите номер заклинания, чтобы получить ссылку на ttg.club:" # ["Список (не доступно)", "primary"],
    if show_keyboard == True:
        change_param(character, 'known_spells', spell_list)
        send_message(message, keyboard_maker([["Добавить новые", "primary"],["Удаление заклинаний", "secondary"]], keyboard_columns=1, hasbackbutton=True))
    else:
        send_message(message)
    
def show_prepared_spells(character, show_keyboard=True):

            
    message += "\nВведите номер заклинания:" # ["Список (не доступно)", "primary"],
    send_message(message, keyboard_maker([["Добавить новые", "primary"],["Удаление заклинаний", "secondary"]], keyboard_columns=1, hasbackbutton=True))
    

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
    elif skill_name in ['лр','ловрук','лврк','лвкрук','ловкрук','рук','лрук','лрк','ловкость рук']:
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

def roll(character='none', amount = 1, die = 20, skill_name = 'none', custom_mod = 0, has_message=False, adv = ''):
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
    roll_history= f"\n\n["
    for i in range (amount):
        current_roll = random.randint(1, die)
        roll_result += current_roll
        roll_history_arr.append(current_roll)
        if has_message:
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
    
    if character != 'none':
        roll_message = f"{character['name']},\n"+ roll_message
    if has_message:
        send_message(roll_message)
    return roll_result

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
    if character['inspiration']:
        inspiration = '✨' 
    else:
        inspiration = 'нет'

    if character['initiative'] >= 0:
        initiative = f"+{character['initiative']}"
    else:
        initiative = f"{character['initiative']}"

    if character['milestone']:
        xp_str = '\n'
    else:
        xp_str = f"Опыт: {character['xp']}\n\n"

    stats_msg = (
    f"Имя: {character['name']}\n"
    f"Раса: {character['subrace']}\n"
    f"Класс: {character['class']}\n"
    f"Уровень: {character['level']}\n"
    f"{xp_str}"

    f"Вдохновение: {inspiration}\n"
    f"Бонус умения: +{character['proficiency_bonus']}\n\n"

    f"❤️ ПЗ: {character['hit_points']}\n"
    f"(временные: {character['temp_hit_points']})\n"
    f"Макс. ПЗ: {character['max_hit_points']}\n\n"

    f"КЗ: {character['hit_dice_count']} из {character['hit_dice_max']}\n\n"
    

    f"🛡️ КБ: {character['armor_class']}\n"
    f"Инициатива: {initiative}\n"
    f"Скорость: {character['speed']} футов\n\n"

    f"Монеты: {money_sum(character['money'])} зм\n\n"

    f"---Заклинания---\n"
    f"Характеристика: {get_spell_stat(character)}\n"
    f"Бонус атаки: {get_mod(get_spell_stat(character).lower(),character) + character['proficiency_bonus']}\n"
    f"CЛ испытаний: {8 + get_mod(get_spell_stat(character).lower(),character) + character['proficiency_bonus']}\n\n"

    f"---Характеристики---\n"
    f"Сила: {stat_format(character['stats']['strength'])}\n"
    f"Ловкость: {stat_format(character['stats']['dexterity'])}\n"
    f"Выносливость: {stat_format(character['stats']['constitution'])}\n"
    f"Интеллект: {stat_format(character['stats']['intelligence'])}\n"
    f"Мудрость: {stat_format(character['stats']['wisdom'])}\n"
    f"Харизма: {stat_format(character['stats']['charisma'])}\n\n"

    f"Испытания: {get_prof_string(character, 'prof_saves_dict', is_saving_throw=True)}\n"
    f"Навыки: {get_prof_string(character, 'prof_mult_dict')}"

    )
    return stats_msg

#Генерация основных статических клавиатур

race_keyboard = keyboard_maker(array_to_text_color_array(list(dnd5e_data.races.values())), keyboard_columns=3, hasbackbutton=True)
class_keyboard = keyboard_maker(array_to_text_color_array(list(dnd5e_data.classes.values())), keyboard_columns=3, hasbackbutton=True)

#Режимы программы: 1. Создание персонажа, 2. Управление персонажами

def create_character_flow(user_id, step, message_text): #создание персонажа
    """Обрабатывает процесс создания персонажа"""
    characters = load_characters(user_id)
    
    if len(characters) >=30:
        send_message("Слишком много персонажей (30).")
        return

    if user_id not in user_states:
        user_states[user_id] = {'state': 'create_character', 'step': 1, 'namestate': False, 'method': 'random', 'addracebonuses': True, 'character': {}}
    state = user_states[user_id]
    
    
    if step == 1:  # Выбор расы
        send_message("Выберите расу вашего персонажа:", race_keyboard)
        state['step'] = 2
    
    elif step == 2:  # Обработка выбора расы
        if message_text.lower() in dnd5e_data.races:
            state['character']['race'] = dnd5e_data.races[message_text.lower()]
            
            if state['character']['race'].lower() in dnd5e_data.race_to_subrace:
                send_message("Выберите подрасу:", keyboard_maker('subraces_list', hasbackbutton=True))
                state['step'] = 3
            else: 
                send_message("Выберите класс:", class_keyboard)
                state['step'] = 4

        elif message_text.lower() == "назад":
            send_message("Главное меню:", keyboards.main_keyboard)
            del user_states[user_id]
        else:
            send_message("Пожалуйста, выберите расу из предложенных вариантов.", race_keyboard)
    
    elif step == 3:  # Обработка выбора подрасы
        
        if message_text.lower() in dnd5e_data.subraces:
            state['character']['subrace'] = dnd5e_data.subraces[message_text.lower()]
            send_message("Выберите класс:", class_keyboard)
            state['step'] = 4

        elif message_text.lower() == "назад":
            send_message("Выберите расу вашего персонажа:", race_keyboard)
            state['step'] = 2
        else:
            send_message("Пожалуйста, выберите подрасу из предложенных вариантов.", keyboard_maker('subraces_list', hasbackbutton=True))
        
    elif step == 4:  # Обработка выбора класса
        
        if message_text.lower() in dnd5e_data.classes:
            state['character']['class'] = dnd5e_data.classes[message_text.lower()]
            send_message("Введите имя вашего персонажа:", keyboards.back_keyboard)

            state['namestate'] = True # Бот обработает имя без знаков в беседе
            print(f"Введите имя:")
            state['step'] = 5
        elif message_text.lower() == "назад":
                if state['character']['race'].lower() in dnd5e_data.race_to_subrace:
                    send_message("Выберите подрасу:", keyboard_maker('subraces_list', hasbackbutton=True))
                    state['step'] = 3
                else: 
                    send_message("Выберите расу вашего персонажа:", race_keyboard)
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
            #send_message("Хотите сгенерировать случайные характеристики или ввести вручную?", keyboard_maker([["Сгенерировать","primary"],["Ввести вручную","primary"]],hasbackbutton=True))
            send_message("Хотите сгенерировать случайные характеристики или ввести вручную? (Сейчас метод генерации не работает)", keyboard_maker([["Ввести вручную","primary"]],hasbackbutton=True))
            state['step'] = 6
        elif len(original_message_text) > 40:
            send_message("Слишком длинное имя. Введите сокращенное имя вашего персонажа:")
        else:
            send_message("Имя не может быть пустым. Введите имя вашего персонажа:")
    
    elif step == 6:  # Выбор способа создания характеристик
        #if message_text in ['1', 'сгенерировать']:
        if message_text == "годзилла нас съест":
            # Генерация характеристик
            # try:
            #     subrace = state['character']['subrace']
            # except KeyError:
            #     subrace={}
            # character = generate_character(
            #     race=state['character']['race'],
            #     subrace=subrace,
            #     stats_array=[],
            #     char_class=state['character']['class'],
            #     prof_dict={},
            #     name=state['character']['name'],
            # )
            
            # Сохраняем персонажа
            # save_character(user_id, character)
            
            # Выводим сообщение с характеристиками
            
            send_message(char_sheet_message(character), keyboards.main_keyboard)
            state['step'] = 'savingthrows'
        
        elif message_text in ['2', 'ввести вручную']:
            send_message("Введите характеристики в формате (расовые бонусы будут применены позже):\nСила Ловкость Выносливость Интеллект Мудрость Харизма\n\nНапример: 15 14 13 12 10 8", keyboard_maker(array_to_text_color_array(["Не применять расовые бонусы"]),hasbackbutton=True))
            state['step'] = 7
        elif message_text == 'назад':
            send_message("Введите имя вашего персонажа:", keyboards.back_keyboard)
            state['namestate'] = True # Бот обработает имя без знаков в беседе
            print(f"Введите имя:")
            state['step'] = 5
        else:
            #send_message("Пожалуйста, выберите вариант:", keyboard_maker([["Сгенерировать","primary"],["Ввести вручную","primary"]],hasbackbutton=True))
            send_message("Пожалуйста, выберите вариант:", keyboard_maker([["Ввести вручную","primary"]],hasbackbutton=True))
    
    elif step == 7:  # Ручной ввод характеристик
            if message_text == 'назад':
                #send_message("Хотите сгенерировать случайные характеристики или ввести вручную?", keyboard_maker([["Сгенерировать","primary"],["Ввести вручную","primary"]],hasbackbutton=True))
                send_message("Хотите сгенерировать случайные характеристики или ввести вручную? (Сейчас метод генерации не работает)", keyboard_maker([["Ввести вручную","primary"]],hasbackbutton=True))
                state['step'] = 6
            

            elif message_text == 'не применять расовые бонусы':
                send_message("Хорошо. Введите характеристики в формате (расовые бонусы не будут применены к вашим значениям):\n\nСила Ловкость Выносливость Интеллект Мудрость Харизма\n\nНапример: 15 14 13 12 10 8", keyboard_maker(array_to_text_color_array(["Назад"], "secondary")))
                state['step'] = 8
            else:
                try:    
                    stats = list(map(int, message_text.split()))
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
                    send_message("Некорректный формат. Введите 6 чисел через пробел, например:\n\n15 14 13 12 10 8", keyboard_maker(array_to_text_color_array(["Не применять расовые бонусы"]),hasbackbutton=True))
            
            
        

    elif step == 8:  # Ручной ввод характеристик без прибавления бонусов
        try:
            if message_text != 'назад' and message_text != 'не применять расовые бонусы':
                stats = list(map(int, message_text.split()))
                if len(stats) != 6:
                    raise ValueError
                
                state['character']['stats'] = stats
                state['method'] = 'manual'
                state['addracebonuses'] = False
                
                # send_message(char_sheet_message(character), keyboards.main_keyboard)
                # del user_states[user_id]
                next_message = "Выберите умения в испытаниях через пробел, например:\n\n1 3\n\n"
                saves_array = list(dnd5e_data.abilities.values())
                for i in range(len(saves_array)):
                    next_message += f"{i+1}. {saves_array[i]}\n"
                send_message(next_message, keyboards.back_keyboard)
                state['step'] = 'savingthrows'

            elif message_text == 'назад':
                #send_message("Хотите сгенерировать случайные характеристики или ввести вручную?", keyboard_maker([["Сгенерировать","primary"],["Ввести вручную","primary"]],hasbackbutton=True))
                send_message("Хотите сгенерировать случайные характеристики или ввести вручную? (Сейчас метод генерации не работает)", keyboard_maker([["Ввести вручную","primary"]],hasbackbutton=True))
                state['step'] = 6
            else:
                send_message("Хорошо. Введите характеристики в формате (расовые бонусы не будут применены к вашим значениям):\n\nСила Ловкость Выносливость Интеллект Мудрость Харизма\n\nНапример: 15 14 13 12 10 8", keyboard_maker(array_to_text_color_array(["Назад"], "secondary")))
                state['step'] = 8

        except ValueError:
            send_message("Некорректный формат. Введите 6 чисел через пробел, например:\n\n15 14 13 12 10 8", keyboard_maker(array_to_text_color_array(["Назад"],'secondary')))


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
            #send_message("Хотите сгенерировать случайные характеристики или ввести вручную?", keyboard_maker([["Сгенерировать","primary"],["Ввести вручную","primary"]],hasbackbutton=True))
            send_message("Хотите сгенерировать случайные характеристики или ввести вручную? (Сейчас метод генерации не работает)", keyboard_maker([["Ввести вручную","primary"]],hasbackbutton=True))
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


def manage_character_flow(user_id, step, message_text): #управление персонажами
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

            if get_main_char_id(user_id) == state['character']['id']:
                send_message(message, keyboards.char_edit_keyboard_main)
            else:
                send_message(message, keyboards.char_edit_keyboard_not_main)
            
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

        elif message_text == 'снаряжение':
            state['step'] = 'equipment'
            show_equipment(state['character'])

            
        elif message_text == 'заклинания':
            state['step'] = 'spells'
            show_all_spells(state['character'])


        elif message_text == 'редактировать':
            send_message("Что вы хотели бы изменить?", keyboard_maker(array_to_text_color_array(
                ["Имя","Характеристики","Уровень","Опыт",
                "Пункты здоровья","Макс. ПЗ",
                "Испытания","Навыки","Инициатива",
                 "Класс Брони","Вдохновение"
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
            send_message('Укажите имена новых предметов (можно ввести несколько, каждый на новой строке):', keyboards.back_keyboard)
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
            items = original_message_text.split('\n')
            for i in range(len(items)):
                if items[i] !='':
                    create_item(character,name=items[i])
            replace_char(character, state['all_characters'])
            write_characters(user_id, state['all_characters'])
            send_message('Предметы успешно добавлены.')
            state['step'] = 'equipment'
            show_equipment(character)

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
                    try:
                        msg =  get_ttg_link(state['character']['known_spells'][i]['name']).lower()
                        send_message(msg)
                    except AttributeError:
                        send_message("Неверный формат для вывода ссылки.")
                    break
            

        elif message_text == 'добавить новые': 
            state['step'] = 'newspells'
            send_message('Укажите названия новых заклинаний в формате:\n\n"X имя заклинания [english name]", \n\nгде X - круг заклинания (0 для фокуса), \nenglish name - название на английском в квадратных скобках (необязательно, но без него не будет работать ссылка на ttg.club). \n\nМожно ввести несколько, каждый на новой строке, например:\n\n0 Леденящее прикосновение [Chill Touch]\n2 Невидимость [Invisibility]', keyboards.back_keyboard)
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
            send_message("Не готово", keyboards.back_keyboard)
            # state['step'] = 'editstats'

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

        elif message_text == 'испытания':
            send_message("Не готово", keyboards.back_keyboard)
            # state['step'] = 'editsaves'

        elif message_text == 'навыки':
            send_message("Не готово", keyboards.back_keyboard)
            # state['step'] = 'editskills'

        elif message_text == 'уровень':
            send_message("Укажите уровень:", keyboards.back_keyboard)
            state['step'] = 'editlvl'
        
        elif message_text == 'опыт':
            send_message("Укажите количество пунктов опыта:", keyboards.back_keyboard)
            state['step'] = 'editxp'
            
        # elif message_text == 'бонус мастерства':
        #     send_message("Не готово", keyboards.back_keyboard)
        #     # state['step'] = 'editbonus'

        elif message_text == 'вдохновение':
            send_message("Не готово", keyboards.back_keyboard)
            # state['step'] = 'editinsp'
        
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
                        hit_dice_curr = state['character']['hit_dice_max'] 
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

    # elif step == 'editstats':
    #     if message_text == 'назад':
    #         message = char_sheet_message(state['character'])
    #         if get_main_char_id(user_id) == state['character']['id']:
    #             send_message(message, keyboards.char_edit_keyboard_main)
    #         else:
    #             send_message(message, keyboards.char_edit_keyboard_not_main)
    #         state['step'] = 3
    #     else: 
            
    # elif step == 'edithp':
    #     if message_text == 'назад':
    #         message = char_sheet_message(state['character'])
    #         if get_main_char_id(user_id) == state['character']['id']:
    #             send_message(message, keyboards.char_edit_keyboard_main)
    #         else:
    #             send_message(message, keyboards.char_edit_keyboard_not_main)
    #         state['step'] = 3
    #     else: 

    # elif step == 'editsaves':
    #     if message_text == 'назад':
    #         message = char_sheet_message(state['character'])
    #         if get_main_char_id(user_id) == state['character']['id']:
    #             send_message(message, keyboards.char_edit_keyboard_main)
    #         else:
    #             send_message(message, keyboards.char_edit_keyboard_not_main)
    #         state['step'] = 3
    #     else: 

    # elif step == 'editskills':
    #     if message_text == 'назад':
    #         message = char_sheet_message(state['character'])
    #         if get_main_char_id(user_id) == state['character']['id']:
    #             send_message(message, keyboards.char_edit_keyboard_main)
    #         else:
    #             send_message(message, keyboards.char_edit_keyboard_not_main)
    #         state['step'] = 3
    #     else: 

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

    # elif step == 'editinsp':
    #     if message_text == 'назад':
    #         message = char_sheet_message(state['character'])
    #         if get_main_char_id(user_id) == state['character']['id']:
    #             send_message(message, keyboards.char_edit_keyboard_main)
    #         else:
    #             send_message(message, keyboards.char_edit_keyboard_not_main)
    #         state['step'] = 3
    #     else: 

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

#Выводит информацию о боте
def show_help(message_id):
    """Показывает справку по боту"""
    help_text = (
        "Этот бот помогает создавать персонажей для D&D 5e.\n\n"
        "Доступные команды:\n"
        "• Создать персонажа - начать процесс создания нового персонажа\n"
        "• Мои персонажи - просмотреть список ваших персонажей. Функционал редактора пока не готов (в процессе)\n"
        "• Бросать кубики по формуле XdY, например, 10d20 или d100. Просто напишите ее в чат"
        "• Бросать кубики с учетом ваших характеристик! Просто создайте персонажа, а после этого напишите команду с кодовым словом (первые 3 буквы характеристики или навыка): сил, мдр, про, вын. Также можно использовать полное названи характеристики, например: Внимание. Испытания (спасброски) можно сделать, добавив перед кодовым словом букву «и» или слово «исп». Наслаждайтесь!\n"
        "• Если вы хотите бросать за другого персонажа, поменяйте его на основного.\n"
        "• Помощь - показать это сообщение\n\n"
        "Бот поддерживает создание персонажей с случайными или заданными характеристиками."
    )
    send_message(help_text, keyboards.main_keyboard)

# Основной цикл бота
for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        chat_id = event.chat_id
        user_id = event.obj.message['from_id']
        if chat_id != None:  # Определение, личные сообщения или беседа
            message_id = chat_id
            if (f'{symbol}' in event.message.get('text')
                or f'@ezgamednd' in event.message.get('text')) == False:
                    if user_id in user_states:
                        if user_states[user_id]['namestate'] == False:
                            continue # Пропуск сообщения, если боту пишут в чат без упоминания или не пишут '/' перед сообщением
                    else:
                        continue
        else: message_id = user_id

        message_text = event.obj.message['text'] # Получение сообщения пользователя
        if f'[club179538565|@ezgamednd] ' or f'{symbol}' in message_text: # Удаляем упоминание и слэш из текста сообщения
            message_text = message_text.replace(f'[club179538565|@ezgamednd] ', '')
            message_text = message_text.replace(f'{symbol}', '')
        
        original_message_text = message_text
        message_text = message_text.lower() 
        
        print(f'{message_text}') #текст в терминал
        

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
                        continue
                    if message_text == 'нет':
                        exit_state(show_message=False)
                        continue
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
                    continue


        if chat_id == None:
            if message_text in ['дом','домой','главная','начальный экран','начало']:
                if user_id in user_states:
                    exit_state(show_message=False)
                main_menu_message()
                continue
            if user_id in user_states:
                print(user_states[user_id]['step'])
                if user_states[user_id]['state'] == 'create_character':
                    create_character_flow(user_id, user_states[user_id]['step'], message_text)
                elif user_states[user_id]['state'] == 'manage_character':
                    manage_character_flow(user_id, user_states[user_id]['step'], message_text)
                # elif user_states['state'] == 
                # elif user_states['state'] == 
                
                elif user_states[user_id]['state'] == 'hpincrease':
                    state = user_states[user_id]
                    if state['step'] == 1:
                        if message_text == 'да':
                            hitdie = state['character']['hit_die']
                            con_mod = dnd5e_data.calc_mod(state['character']['stats']['constitution'])
                            sign_con = "+" if con_mod >=0 else ""
                            average = hitdie // 2 + 1
                            send_message(f"Ваша Кость здоровья — d{hitdie}. Вы можете кинуть ее и добавить ваш модификатор Выносливости ({sign_con}{con_mod}).\n\nВместо броска взять среднее значение: {average+con_mod}).\n\nТакже можете ввести насколько повысится ваш максимум ПЗ вручную, если бросаете кость вживую (максимум — {hitdie+con_mod})", keyboard_maker(array_to_text_color_array(
                                            ["Кинуть","Среднее","Вручную"]),onetime=True))
                            state['step'] = 2
                            continue
                        if message_text == 'нет':
                            exit_state(show_message=False)
                            continue
                        else:
                            send_message(f"Выберите \"да\" или \"нет\".",keyboard=keyboard_maker(array_to_text_color_array(["Да","Нет"]),keyboard_columns=2,onetime=True))

                    if state['step'] == 2:
                        char = state['character']
                        maxhp = state['character']['max_hit_points']
                        hitdie = char['hit_die']
                        average = hitdie // 2 + 1
                        con_mod = dnd5e_data.calc_mod(char['stats']['constitution'])
                        if message_text == 'кинуть':
                            newmaxhp = random.randint(1, hitdie) + con_mod
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
                        continue
                continue

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
                roll(characters[get_main_char_id(user_id) - 1], amount, die, has_message=True, custom_mod = mod)
                continue
            except ValueError:
                send_message("Пожалуйста, введите правильное значение кости в формате XdY.", keyboards.main_keyboard)
            except IndexError:
                if not user_id in user_warnings:
                    send_message("Персонаж не подключен. Создайте персонажа, чтобы роллить с учетом его характеристик.")
                    user_warnings[user_id] = ''
                roll(character='none', amount=amount, die=die, has_message=True, custom_mod=mod)
                continue
            continue
        
        elif message_text in dnd5e_data.code_word_list:
            if not 'пом' in message_text and not 'пре' in message_text:
                try:
                    characters = load_characters(user_id)
                    roll(characters[get_main_char_id(user_id) - 1], skill_name=message_text, has_message=True)
                    continue
                except IndexError:
                    if not user_id in user_warnings:
                        send_message("Персонаж не подключен. Создайте персонажа, чтобы роллить с учетом его характеристик.", keyboard=keyboards.main_keyboard)
                        user_warnings[user_id] = ''
                    roll(character='none', amount=1, die=20, has_message=True) 
                    continue   

        elif 'пом' in message_text or 'пре' in message_text:
            try:   
                newtext = message_text.replace(" ", "")
                if newtext[4:].isdigit():
                    i = newtext.find('+')
                    sign = 1
                    if i == -1:
                        sign = -1
                    skill_tag = 'none'
                    mod = int(newtext[4:])
                else:
                    mod = 0
                    skill_tag = message_text[3:]
                adv = message_text[0:3]
                if skill_tag in dnd5e_data.code_word_list:
                    try:
                        characters = load_characters(user_id)
                        roll(characters[get_main_char_id(user_id) - 1], skill_name=skill_tag, has_message=True, adv=adv)
                    except IndexError:
                        if not user_id in user_warnings:
                            send_message("Персонаж не подключен. Создайте персонажа, чтобы роллить с учетом его характеристик.", keyboard=keyboards.main_keyboard)
                            user_warnings[user_id] = ''
                        roll(character='none', amount=1, die=20, has_message=True, adv=adv)
                        continue
                elif len(message_text) == 3 or mod > 0 or mod < 0:
                    roll(character='none', die=20, has_message=True, adv=adv, custom_mod = mod)
                    continue
        
            except ValueError:
                send_message("Персонаж не подключен. Создайте персонажа, чтобы использовать эту функцию.")
                continue
            except KeyError:
                send_message("Персонаж не подключен. Создайте персонажа, чтобы использовать эту функцию.")
                continue
            except IndexError:
                send_message("Персонаж не подключен. Создайте персонажа, чтобы использовать эту функцию.")
                continue
            continue
        try:
            if message_text in dnd5e_data.code_fast_no_value:
                if message_text in ['снар','снаряжение', 'сн']:
                    char = load_main_character(user_id)
                    show_equipment(char, show_keyboard=False)
                if message_text in ['сл','заклсл', 'сложность испытаний']:
                    char = load_main_character(user_id)
                    send_message(f"Ваша СЛ испытаний для заклинаний: {8 + get_mod(get_spell_stat(char),char) + char['proficiency_bonus']}") 
                if message_text in ['закл','заклин','зак', 'заклинания']:
                    char = load_main_character(user_id)
                    show_all_spells(char, show_keyboard=False)
                if message_text in ['деньги','монеты','мон']:
                    money = money_message(load_main_character(user_id))
                    send_message(money)
                if message_text in ['длиный отдых','до']:
                    # charhp = load_main_character(user_id)['hit_points']
                    send_message(f"Долгий отдых это долгий период длительностью как минимум 8 часов, во время которого персонаж спит не менее 6 часов и совершает лёгкую деятельность: читает, разговаривает, ест и стоит на страже не более 2 часов. Если отдых прерывается напряжённой активностью (как минимум 1 час ходьбы, сражения, накладывания заклинаний или другой подобной деятельности), персонажи должны начать отдых с начала, чтобы получить от него преимущества. В конце долгого отдыха персонаж восстанавливает все потерянные Пункты здоровья, а также половину от максимума Костей здоровья (минимум 1). \n\nНапример, если у персонажа восемь Костей здоровья, в конце долгого отдыха он может восстановить четыре из них.\n\nПерсонаж не может получить преимущества от второго долгого отдыха за 24-часовой период, и у персонажа должен быть хотя бы 1 пункт здоровья в начале отдыха, чтобы получить от него преимущества.")
                if message_text in ['короткий отдых','ко']:
                    # charhp = load_main_character(user_id)['hit_points']
                    send_message(f"Короткий отдых это период длиной как минимум 1 час, во время которого персонаж не делает ничего напряжённого кроме поглощения пищи, питья, чтения и обработки ран. \n\nВ конце короткого отдыха персонаж может потратить одну или несколько Костей здоровья. Каждая потраченная кость позволяет совершить бросок соответствующей кости, добавить к ней модификатор Выносливости и восстановить получившееся количество пунктов здоровья. После каждого броска можно решить, что будет потрачена ещё одна Кость здоровья. \n\nПотраченные Кости здоровья восстанавливаются после окончания долгого отдыха, как описано ниже.")
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
                        change_param(char,'hit_dice_max',lvl)
                        change_param(char,'hit_dice_count',hit_dice_new_curr)
                        send_message(f"Уровень успешно повышен. Теперь вы {lvl+1} уровня. Хотите ли изменить максимум пунктов здоровья?",keyboard=keyboard_maker(array_to_text_color_array(["Да","Нет"]),keyboard_columns=2,onetime=True))
                        user_states[user_id] = {'character': char, 'state': 'hpincrease', 'step': 1}
                continue
            elif message_text == 'я':
                send_message(char_sheet_message(load_main_character(user_id)))
                continue
            elif message_text == 'навыки':
                show_all_skills(load_main_character(user_id),horizontal_format=True, show_all=True)
                continue

            elif message_text[0:2] in dnd5e_data.code_fast_value:
                if len(message_text)>2:
                    parts = message_text.split(' ')
                    if len(parts) > 2:
                        send_message("Неверный формат бонуса.")
                        continue
                    if len(parts) <1:
                        send_message("Неверный формат бонуса.")
                        continue
                    try:
                        code = parts[0]
                        sign = parts[1][0]
                        if sign == '+' or sign == '-':
                            value = int(parts[1][1:])
                        if sign.isdigit():
                            value = int(parts[1][0:])
                            sign = ''

                    except ValueError:
                        send_message("Неверный формат бонуса.")
                        continue
                    except IndexError:
                        send_message("Неверный формат бонуса.")
                        continue
                    if sign == '-':
                        value = value * -1
                    elif sign != '+' and sign !='':
                        send_message("Неверный формат бонуса.")
                        continue
                    if code in ['кб']:
                        char = load_main_character(user_id)
                        if value >= 0:
                            change_param(char,'armor_class', value)
                            send_message(f"Ваш новый КБ — {value}.")
                        else:
                            send_message("КБ не может быть меньше 0.")
                    if code in ['зм','пм','эм','см','мм']:
                        add_money(load_main_character(user_id),type=code,value=value,show_message=True)
                    if code in ['пз','хп']:
                        char = load_main_character(user_id)
                        newhp= char['hit_points'] + value
                        if newhp < 0:
                            newhp = 0
                            #send_message('Вы падаете без сознания!')
                        if newhp > char['max_hit_points']:
                            newhp = char['max_hit_points']
                        change_param(char,'hit_points', newhp)
                        send_message(f"У вас теперь {newhp} ПЗ.")
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
                        send_message(f"У вас {newhd} из {charhdmax} КЗ. (d{charhdie}).")
                    if code in ['по','оп']:
                        char = load_main_character(user_id)
                        newxp= char['xp'] + value
                        if newxp < 0:
                            newxp = 0
                            #send_message('Вы падаете без сознания!')
                        change_param(char,'xp', newxp)
                        send_message(f"У вас теперь {newxp} ПО.")
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
                    if message_text in ['зм','пм','эм','см','мм']:
                        charmoney = load_main_character(user_id)['money'][f'{message_text}']
                        send_message(f"У вас {charmoney} {message_text}.")
                    if message_text in ['пз','хп']:
                        charhp = load_main_character(user_id)['hit_points']
                        send_message(f"У вас {charhp} ПЗ.")
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
                continue
            elif message_text[0:3] in dnd5e_data.code_fast_value: #трехбуквенные коды, ттг
                if len(message_text)>3:
                    parts = message_text.split(' ')
                    if len(parts) > 2:
                        send_message("Неверный формат бонуса.")
                        continue
                    if len(parts) <1:
                        send_message("Неверный формат бонуса.")
                        continue
                    try:
                        code = parts[0]
                        value = parts[1]
                        value = int(value)
                    except ValueError:
                        send_message("Пожалуйста, введите правильный номер заклинания для получения ссылки.")
                        continue
                    if code in ['ttg','ттг']:
                        char = load_main_character(user_id)
                        spells = char['known_spells']
                        if value > 0 and value <= len(spells):
                            for i in range(len(spells)):
                                if value == char['known_spells'][i]['id']:
                                    try:
                                        msg =  get_ttg_link(char['known_spells'][i]['name']).lower()
                                        send_message(msg)
                                    except AttributeError:
                                        send_message("Неверный формат для вывода ссылки.")
                                    break
                        else:
                            send_message("Заклинания под таким номером не существует.")
                        continue
                continue
        except ValueError:
            send_message("Персонаж не подключен. Создайте персонажа, чтобы использовать эту функцию.")
            continue
        except KeyError:
            send_message("Персонаж не подключен. Создайте персонажа, чтобы использовать эту функцию.")
            continue
        except IndexError:
            send_message("Персонаж не подключен. Создайте персонажа, чтобы использовать эту функцию.")
            continue

        if message_text in ['закрыть клавиатуру','закрклав','-клав','-кл','зкл']:
            send_message("Клавиатура закрыта.")
            continue

        elif chat_id == None:
            if  message_text == "создать персонажа" or message_text == "создать":
                create_character_flow(user_id, 1, "")


            elif message_text == "мои персонажи":
                manage_character_flow(user_id, 1, "")
            
            elif message_text == "помощь":
                show_help(message_id)
            
            elif message_text == "привет" or message_text == "начать":
                send_message("Привет! Я бот для создания персонажей D&D 5e. Чем могу помочь?", keyboards.main_keyboard)

            else:
                send_message("Команда не распознана.", keyboard=keyboards.main_keyboard)

        # Обработка команд, доступных в личке бота
        

         