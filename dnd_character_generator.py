import random
import dnd5e_data

def generate_ability_scores(method='random'):
    """Генерирует характеристики персонажа"""
    if method == 'standard':
        # Стандартный метод: 15, 14, 13, 12, 10, 8
        return [15, 14, 13, 12, 10, 8]
    else:
        # Метод "4d6 drop lowest"
        stats = []
        for _ in range(6):
            rolls = [random.randint(1, 6) for _ in range(4)]
            rolls.remove(min(rolls))
            stats.append(sum(rolls))
        return stats

def apply_racial_bonuses(race, stats):
    """Применяет бонусы расы к характеристикам"""

    
    if race in dnd5e_data.race_bonuses:
        return [s + b for s, b in zip(stats, dnd5e_data.race_bonuses[race])]
    return stats

def apply_subracial_bonuses(subrace, stats):
    """Применяет бонусы подрасы к характеристикам"""

    
    if subrace in dnd5e_data.subrace_bonuses:
        return [s + b for s, b in zip(stats, dnd5e_data.subrace_bonuses[subrace])]
    return stats

def set_speed(race, subrace):
    if race == 'Эльф':
        if subrace == 'Лесной эльф':
            return 35
    elif race in ['Полурослик', 'Дварф', 'Гном']:
        return 25
    return 30 # По умолчанию

def set_hit_die(char_class):
    """Определяет кость здоровья"""
    if char_class == 'Варвар':
        return 12
    elif char_class in ['Воин', 'Паладин', 'Следопыт']:
        return 10
    elif char_class in ['Бард', 'Жрец', 'Друид', 'Монах', 'Плут', 'Колдун']:
        return 8
    elif char_class in ['Чародей', 'Волшебник']:
        return 6
    return 8 # По умолчанию

def calculate_armor_class(dexterity):
    """Рассчитывает класс доспеха"""
    return 10 + (dexterity - 10) // 2



def generate_character(race, subrace, char_class, name, stats_array, saves_dict, prof_dict, money, method='random', addracebonuses=True):
    """Генерирует персонажа с заданными расой, классом и именем"""
    # Генерируем характеристики
    if method == 'manual':
        stats = stats_array
    else:
        stats = generate_ability_scores(method)
    
    # Применяем бонусы расы


    stats_with_race = apply_racial_bonuses(race, stats) if addracebonuses == True else stats
    if subrace == {}:
        subrace = race
    else: 
        stats_with_race = apply_subracial_bonuses(subrace, stats_with_race) if addracebonuses == True else stats
    # Создаем словарь характеристик
    stats_dict = {
        'strength': stats_with_race[0],
        'dexterity': stats_with_race[1],
        'constitution': stats_with_race[2],
        'intelligence': stats_with_race[3],
        'wisdom': stats_with_race[4],
        'charisma': stats_with_race[5]
    }


    
    # Создаем персонажа
    character = {
        'id': 0,
        'name': name,
        'race': race,
        'subrace': subrace,
        'class': char_class,
        'level': 1,
        'background': "",
        'alignment': "",
        'xp': 0,
        'milestone': False,
        'inspiration': False,

        'stats': stats_dict,
        'prof_saves_dict': saves_dict,
        'prof_mult_dict': prof_dict,
        'proficiency_bonus': 2,
        'armor_class': calculate_armor_class(stats_dict['dexterity']),
        'max_hit_points': set_hit_die(char_class) +  dnd5e_data.calc_mod(stats_dict['constitution']),
        'hit_points': set_hit_die(char_class) +  dnd5e_data.calc_mod(stats_dict['constitution']),
        'temp_hit_points': 0,

        'hit_die': set_hit_die(char_class),
        'hit_dice_max': 1,
        'hit_dice_count': 1,
        'initiative': dnd5e_data.calc_mod(stats_dict['dexterity']),

        'speed': set_speed(race, subrace),

        'proficiencies': [],
        'languages': '',
        'weapons': '',
        'attack_macro_array': [],


        'money': money,
        'equipment': [],

        'spell_slots': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        'current_spell_slots': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        'known_spells': [],
        'prepared_spells': [],
        'image': '',
    }

    return character