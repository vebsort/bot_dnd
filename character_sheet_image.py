# -*- coding: utf-8 -*-
"""
Генерация изображения листа персонажа D&D 5e по данным персонажа.
Эмодзи рисуются через pilmoji (подстановка картинок эмодзи), если библиотека установлена.
Картинки эмодзи кэшируются в памяти и на диске (cache/pilmoji), чтобы не скачивать заново при каждом запуске.
"""

import hashlib
import os
import random
import tempfile
import time
from io import BytesIO
from contextlib import contextmanager
import dnd5e_data

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

try:
    from pilmoji import Pilmoji
    from pilmoji.source import BaseSource, Twemoji
except ImportError:
    Pilmoji = None
    BaseSource = None
    Twemoji = None

# Порядок характеристик и названия
ABILITY_NAMES = ['Сила', 'Ловкость', 'Выносливость', 'Интеллект', 'Мудрость', 'Харизма']
STAT_KEYS = ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma']

# Навыки в порядке, как на листе
SKILLS_ORDER = [
    'Атлетика', 'Акробатика', 'Ловкость рук', 'Скрытность', 'Выживание',
    'История', 'Магия', 'Природа', 'Расследование', 'Религия',
    'Внимание', 'Дрессировка', 'Медицина', 'Проницательность',
    'Обман', 'Запугивание', 'Исполнение', 'Убеждение',
]

# Стиль: фон «бумаги», тёмные рамки
PAPER_COLOR = (248, 244, 232)  # тёплый кремовый
COLOR_BG = (255, 255, 255)  # запасной
COLOR_BORDER = (45, 35, 25)
COLOR_BORDER_INNER = (90, 70, 50)
COLOR_BANNER_BG = (248, 246, 240)
COLOR_BANNER_BORDER = (45, 35, 25)
COLOR_TEXT = (30, 25, 20)
COLOR_LABEL = (60, 50, 40)
COLOR_DOTS = (140, 130, 115)  # приглушённые точки-лидеры
LINE_W = 2
BANNER_LINE_W = 2
RADIUS = 8  # скругление рамок

# При установленном pilmoji эмодзи рендерятся как картинки (Twemoji и т.п.)
USE_EMOJI = Pilmoji is not None

# Символы эмодзи, которые мы используем на листе (для быстрой проверки — Pilmoji только для таких строк)
_EMOJI_CHARS = frozenset('💪🎯🛡️📋⚔️❤️💫🎲⚡👣💰📜✨🔮📊⭐')

# Кэш картинок эмодзи: в памяти и на диске (папка cache/pilmoji рядом со скриптом)
_emoji_bytes_cache = {}
_emoji_cache_preloaded = False


def _emoji_cache_path(emoji: str):
    """Путь к файлу кэша для одного эмодзи (по хэшу строки)."""
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'pilmoji')
    name = hashlib.md5(emoji.encode('utf-8')).hexdigest() + '.png'
    return os.path.join(d, name)


if BaseSource is not None and Twemoji is not None:
    class _CachingEmojiSource(BaseSource):
        """Источник эмодзи с кэшем в памяти и на диске."""

        def __init__(self):
            self._source = Twemoji()

        def get_emoji(self, emoji: str, /):
            global _emoji_bytes_cache
            if emoji in _emoji_bytes_cache:
                return BytesIO(_emoji_bytes_cache[emoji])
            path = _emoji_cache_path(emoji)
            if os.path.isfile(path):
                try:
                    with open(path, 'rb') as f:
                        data = f.read()
                    _emoji_bytes_cache[emoji] = data
                    return BytesIO(data)
                except Exception:
                    pass
            stream = self._source.get_emoji(emoji)
            if stream:
                data = stream.read()
                _emoji_bytes_cache[emoji] = data
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, 'wb') as f:
                        f.write(data)
                except Exception:
                    pass
                return BytesIO(data)
            return None

        def get_discord_emoji(self, id: int, /):
            return self._source.get_discord_emoji(id)

    _caching_emoji_source = _CachingEmojiSource()
else:
    _CachingEmojiSource = None
    _caching_emoji_source = None


def _preload_emoji_cache():
    """Один раз загружает все используемые эмодзи в кэш (при первой генерации листа)."""
    global _emoji_cache_preloaded
    if not _caching_emoji_source or _emoji_cache_preloaded:
        return
    t0 = time.perf_counter()
    for char in _EMOJI_CHARS:
        _caching_emoji_source.get_emoji(char)
    _emoji_cache_preloaded = True
    print(f"[лист] предзагрузка эмодзи в кэш ({len(_EMOJI_CHARS)} шт.): {time.perf_counter() - t0:.3f} с")


def _has_emoji(text):
    """Есть ли в строке эмодзи (используем Pilmoji только тогда)."""
    return any(c in _EMOJI_CHARS for c in text)

def _pre(e_emoji, e_ascii):
    """Префикс: эмодзи-версия или ASCII в зависимости от наличия pilmoji."""
    return e_emoji if USE_EMOJI else e_ascii


def _skill_to_ability(skill_name):
    skill_ability = {
        'Атлетика': 'strength',
        'Акробатика': 'dexterity', 'Ловкость рук': 'dexterity', 'Скрытность': 'dexterity',
        'Выживание': 'wisdom',
        'История': 'intelligence', 'Магия': 'intelligence', 'Природа': 'intelligence',
        'Расследование': 'intelligence', 'Религия': 'intelligence',
        'Внимание': 'wisdom', 'Дрессировка': 'wisdom', 'Медицина': 'wisdom', 'Проницательность': 'wisdom',
        'Обман': 'charisma', 'Запугивание': 'charisma', 'Исполнение': 'charisma', 'Убеждение': 'charisma',
    }
    return skill_ability.get(skill_name, 'intelligence')


def _ability_to_stat_key(ability_name):
    a = ability_name.lower()
    if a == 'сила': return 'strength'
    if a == 'ловкость': return 'dexterity'
    if a == 'выносливость': return 'constitution'
    if a == 'интеллект': return 'intelligence'
    if a == 'мудрость': return 'wisdom'
    if a == 'харизма': return 'charisma'
    return 'strength'


def get_skill_mod(character, skill_name):
    if skill_name not in character.get('prof_mult_dict', {}):
        return 0
    key = _skill_to_ability(skill_name)
    stats = character.get('stats') or {}
    base = dnd5e_data.calc_mod(stats.get(key, 10))
    prof = character['prof_mult_dict'][skill_name] * character.get('proficiency_bonus', 0)
    return base + prof


def get_save_mod(character, ability_name):
    key = _ability_to_stat_key(ability_name)
    stats = character.get('stats') or {}
    base = dnd5e_data.calc_mod(stats.get(key, 10))
    pd = character.get('prof_saves_dict', {})
    prof = pd.get(ability_name, 0) * character.get('proficiency_bonus', 0)
    return base + prof


# Путь к ресурсам рядом со скриптом (фон бумаги, рукописный шрифт)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_TEXTURE_PATH = os.path.join(_SCRIPT_DIR, 'assets', 'paper_bg.png')
HANDWRITING_FONT_PATH = os.path.join(_SCRIPT_DIR, 'fonts', 'BadScript-Regular.ttf')

_font_cache = {}

def _find_font(size=14):
    if size in _font_cache:
        return _font_cache[size]
    # Сначала рукописный шрифт с кириллицей (Bad Script), затем системные
    candidates = [
        HANDWRITING_FONT_PATH,
        'C:/Windows/Fonts/segoeui.ttf',
        'C:/Windows/Fonts/segoeui.ttc',
        'C:/Windows/Fonts/calibri.ttf',
        'C:/Windows/Fonts/calibril.ttf',
        'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/tahoma.ttf',
        '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                font = ImageFont.truetype(path, size)
                _font_cache[size] = font
                return font
            except Exception:
                continue
    font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def _make_paper_texture(width, height):
    """Фон: картинка старой бумаги из файла или процедурная текстура."""
    if Image is None:
        return Image.new('RGB', (width, height), PAPER_COLOR)
    if os.path.isfile(PAPER_TEXTURE_PATH):
        try:
            bg = Image.open(PAPER_TEXTURE_PATH).convert('RGB')
            try:
                bg = bg.resize((width, height), Image.Resampling.LANCZOS)
            except AttributeError:
                bg = bg.resize((width, height), Image.LANCZOS)
            return bg
        except Exception:
            pass
    # Запасной вариант: тёплый цвет + зернистость
    tile = 128
    try:
        noise = Image.new('L', (tile, tile))
        noise.putdata([random.randint(0, 255) for _ in range(tile * tile)])
        noise = noise.resize((width, height), Image.Resampling.BILINEAR)
    except AttributeError:
        noise = noise.resize((width, height), Image.BILINEAR)
    r, g, b = PAPER_COLOR
    strength = 14
    R = noise.point(lambda v: max(0, min(255, r + (v - 128) * strength // 128)))
    G = noise.point(lambda v: max(0, min(255, g + (v - 128) * strength // 128)))
    B = noise.point(lambda v: max(0, min(255, b + (v - 128) * strength // 128)))
    return Image.merge('RGB', (R, G, B))


def _money_sum(money_dict):
    if not money_dict:
        return 0
    m = money_dict
    return (m.get('зм', 0) or 0) + (m.get('см', 0) or 0) / 10 + (m.get('эм', 0) or 0) / 50 + (m.get('пм', 0) or 0) / 100 + (m.get('мм', 0) or 0) / 1000


def get_spell_stat(character):
    classs = character.get('class', '').lower()
    return dnd5e_data.class_spell_stat.get(classs, None)


def _draw_fancy_box(draw, x1, y1, x2, y2, border_color=COLOR_BORDER, radius=RADIUS):
    """Рамка со скруглением (одна обводка для чистого вида)."""
    try:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, outline=border_color, width=LINE_W)
    except Exception:
        draw.rectangle([x1, y1, x2, y2], outline=border_color, width=LINE_W)


def _draw_box(draw, x1, y1, x2, y2, border_color=COLOR_BORDER, width=LINE_W, corners=False):
    """Рамка (скруглённая или простая)."""
    try:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=RADIUS, outline=border_color, width=width)
    except Exception:
        draw.rectangle([x1, y1, x2, y2], outline=border_color, width=width)


def generate_character_sheet_image(character, width=1280, path=None, portrait_path=None, use_pilmoji=True):
    """
    Рисует лист персонажа D&D 5e. Портрет под баннером по центру, ~80% ширины; ниже — блок характеристик.
    use_pilmoji=False — быстрая генерация без картинок эмодзи (буквы * вместо звёзд и т.д.).
    """
    if Image is None:
        raise RuntimeError("Требуется установить Pillow: pip install Pillow")

    use_emoji_img = use_pilmoji and USE_EMOJI
    def pre(e, a):
        return e if use_emoji_img else a

    t0 = time.perf_counter()
    margin = int(width * 0.03)
    gap = int(width * 0.02)
    banner_h = int(width * 0.10)
    line_h = int(width * 0.032)
    line_small = int(width * 0.026)
    line_step = line_small + 3  # чуть больше отступ между строками в списках

    content_area_w = width - 2 * margin - 2 * BANNER_LINE_W
    # Портрет под баннером по центру, ~80% ширины листа
    portrait_w = int(content_area_w * 0.80) if portrait_path else 0
    portrait_h = portrait_w  # квадрат
    portrait_x = margin + BANNER_LINE_W + (content_area_w - portrait_w) // 2 if portrait_w else 0
    portrait_y = margin + BANNER_LINE_W + banner_h + gap

    content_start_y = portrait_y + portrait_h + gap if portrait_w else (margin + BANNER_LINE_W + banner_h + gap)
    content_x = margin + BANNER_LINE_W
    content_width = content_area_w

    col_lines = max(6 + 2 + 6 + 4, len([s for s in SKILLS_ORDER if s in (character.get('prof_mult_dict') or {})]) + 4, 14)
    block_h = (col_lines * line_step) + 180
    box_bottom = content_start_y + line_small + gap + block_h
    height = box_bottom + margin

    img = _make_paper_texture(width, height)
    draw = ImageDraw.Draw(img)
    font_title = _find_font(int(width * 0.042))
    font_section = _find_font(int(width * 0.030))
    font_body = _find_font(int(width * 0.026))
    font_small = _find_font(int(width * 0.023))
    print(f"[лист] инициализация (холст, шрифты): {time.perf_counter() - t0:.3f} с")

    t1 = time.perf_counter()
    @contextmanager
    def _text_drawer():
        if Pilmoji is not None and use_pilmoji:
            _preload_emoji_cache()
            pilmoji_kw = dict(source=_caching_emoji_source) if _caching_emoji_source else {}
            with Pilmoji(img, **pilmoji_kw) as pilmoji:
                def _txt(x, y, text, font=font_body, color=COLOR_TEXT):
                    if _has_emoji(text):
                        pilmoji.text((x, y), text, color, font)
                    else:
                        draw.text((x, y), text, font=font, fill=color)
                yield _txt
        else:
            def _txt(x, y, text, font=font_body, color=COLOR_TEXT):
                draw.text((x, y), text, font=font, fill=color)
            yield _txt

    # —— Имя персонажа (без фона и рамки, текст прямо на бумаге) ——
    banner_y1 = margin + BANNER_LINE_W
    banner_y2 = banner_y1 + banner_h
    banner_x1 = margin + BANNER_LINE_W
    banner_x2 = width - margin - BANNER_LINE_W
    print(f"[лист] рамки: {time.perf_counter() - t1:.3f} с")

    t2 = time.perf_counter()
    # —— Портрет под баннером по центру, ~80% ширины, в рамочке ——
    if portrait_path and os.path.isfile(portrait_path) and portrait_w > 0:
        try:
            photo = Image.open(portrait_path).convert('RGB')
            pw, ph = photo.size
            if pw >= ph:
                crop_x = (pw - ph) // 2
                photo = photo.crop((crop_x, 0, crop_x + ph, ph))
            else:
                crop_y = (ph - pw) // 2
                photo = photo.crop((0, crop_y, pw, crop_y + pw))
            try:
                resample = Image.Resampling.BILINEAR  # быстрее LANCZOS, качество приемлемое
            except AttributeError:
                resample = Image.BILINEAR
            photo = photo.resize((portrait_w, portrait_h), resample)
            img.paste(photo, (portrait_x, portrait_y))
            _draw_fancy_box(draw, portrait_x, portrait_y, portrait_x + portrait_w, portrait_y + portrait_h)
        except Exception:
            pass
    print(f"[лист] портрет: {time.perf_counter() - t2:.3f} с")

    t3 = time.perf_counter()
    with _text_drawer() as txt:
        name = character.get('name', '—')
        subrace = character.get('subrace', character.get('race', ''))
        cls = character.get('class', '')
        lvl = character.get('level', 1)
        insp = pre(" ✨", " *") if character.get('inspiration') else ''
        banner_text = f"{name}  ·  {subrace}  ·  {cls} {lvl} ур.{insp}"
        txt_y = banner_y1 + (banner_h - line_h) // 2 - 2
        try:
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((0, 0), banner_text, font=font_title)
            elif hasattr(font_title, 'getbbox'):
                bbox = font_title.getbbox(banner_text)
            else:
                raise AttributeError('no bbox')
            tw = bbox[2] - bbox[0]
            txt_x = banner_x1 + max(0, (banner_x2 - banner_x1 - tw) // 2)
        except Exception:
            txt_x = banner_x1 + 20
        txt(txt_x, txt_y, banner_text, font=font_title, color=COLOR_TEXT)

        def _text_width(s, font=font_body):
            try:
                bbox = draw.textbbox((0, 0), s, font=font)
                return bbox[2] - bbox[0]
            except Exception:
                return 0

        # Опыт и три колонки — под портретом на всю ширину
        content_y = content_start_y
        if not character.get('milestone', False):
            exp_text = pre("📊 ", "") + "Опыт: " + str(character.get('xp', 0))
            exp_x = content_x + (content_width - _text_width(exp_text, font_small)) // 2
            txt(exp_x, content_y, exp_text, font=font_small, color=COLOR_LABEL)
            content_y += line_small + 4
        content_y += gap
        t3a = time.perf_counter()
        print(f"  [текст] баннер + опыт: {t3a - t3:.3f} с")

        # Три колонки с рамками на всю ширину контента
        col_w = (content_width - 2 * gap) // 3
        col1_x1 = content_x + 10
        col1_x2 = col1_x1 + col_w - gap
        col2_x1 = col1_x2 + gap
        col2_x2 = col2_x1 + col_w - gap
        col3_x1 = col2_x2 + gap
        col3_x2 = content_x + content_width - 10
        box_top = content_y

        def _draw_leader_dots(left_end, right_start, y, font=font_body, color=COLOR_DOTS):
            """Точечки между названием и модификатором, чтобы глаз не терял связь."""
            gap_w = right_start - left_end
            if gap_w < 10:
                return
            cell = " ."
            try:
                bbox = draw.textbbox((0, 0), cell, font=font)
                cell_w = bbox[2] - bbox[0]
            except Exception:
                cell_w = 8
            n = max(1, gap_w // (cell_w or 1))
            dots_str = cell * n
            try:
                draw.text((left_end, y), dots_str, font=font, fill=color)
            except Exception:
                pass

        # —— Колонка 1: Характеристики и испытания (цифры по правому краю) ——
        stats = character.get('stats') or {}
        _draw_box(draw, col1_x1, box_top, col1_x2, box_bottom)
        x, y = col1_x1 + 8, box_top + 10
        r1 = col1_x2 - 8
        w1 = col1_x2 - col1_x1
        line_w1 = int(w1 * 0.70)
        line_x1_0 = col1_x1 + (w1 - line_w1) // 2
        hdr1 = pre("💪 ", "") + "Характеристики"
        txt(col1_x1 + (w1 - _text_width(hdr1, font_section)) // 2, y, hdr1, font=font_section, color=COLOR_TEXT)
        y += line_h + 16
        draw.line([(line_x1_0, y), (line_x1_0 + line_w1, y)], fill=COLOR_BORDER, width=1)
        y += 14
        for abbr, key in zip(ABILITY_NAMES, STAT_KEYS):
            val = stats.get(key, 10)
            mod = dnd5e_data.calc_mod(val)
            mod_str = f"+{mod}" if mod >= 0 else str(mod)
            val_str = f"{val} ({mod_str})"
            txt(x, y, f"{abbr}:", font=font_body, color=COLOR_TEXT)
            txt(r1 - _text_width(val_str), y, val_str, font=font_body, color=COLOR_TEXT)
            y += line_step
        y += 6
        pb_str = "+" + str(character.get('proficiency_bonus', 0))
        txt(x, y, pre("🎯 ", "* ") + "Бонус умения:", font=font_body, color=COLOR_TEXT)
        txt(r1 - _text_width(pb_str), y, pb_str, font=font_body, color=COLOR_TEXT)
        y += line_step + 14
        draw.line([(line_x1_0, y), (line_x1_0 + line_w1, y)], fill=COLOR_BORDER, width=1)
        y += 20
        hdr2 = pre("🛡️ ", "") + "Испытания"
        txt(col1_x1 + (w1 - _text_width(hdr2, font_section)) // 2, y, hdr2, font=font_section, color=COLOR_TEXT)
        y += line_h + 16
        draw.line([(line_x1_0, y), (line_x1_0 + line_w1, y)], fill=COLOR_BORDER, width=1)
        y += 14
        star_str = pre(" ⭐", " *")
        for ab in ABILITY_NAMES:
            save_mod = get_save_mod(character, ab)
            sm = f"+{save_mod}" if save_mod >= 0 else str(save_mod)
            prof = character.get('prof_saves_dict', {}).get(ab, 0)
            left_part = f"  {ab}{star_str}" if prof else f"  {ab}"
            txt(x, y, left_part, font=font_body, color=COLOR_TEXT)
            left_end = x + _text_width(left_part)
            right_start = r1 - _text_width(sm)
            _draw_leader_dots(left_end, right_start, y)
            txt(r1 - _text_width(sm), y, sm, font=font_body, color=COLOR_TEXT)
            y += line_step
        t3b = time.perf_counter()
        print(f"  [текст] колонка 1 (характеристики, испытания): {t3b - t3a:.3f} с")

        # —— Колонка 2: Навыки (цифры по правому краю) ——
        _draw_box(draw, col2_x1, box_top, col2_x2, box_bottom)
        x2, y2 = col2_x1 + 8, box_top + 10
        r2 = col2_x2 - 8
        w2 = col2_x2 - col2_x1
        line_w2 = int(w2 * 0.70)
        line_x2_0 = col2_x1 + (w2 - line_w2) // 2
        hdr_skills = pre("📋 ", "") + "Навыки"
        txt(col2_x1 + (w2 - _text_width(hdr_skills, font_section)) // 2, y2, hdr_skills, font=font_section, color=COLOR_TEXT)
        y2 += line_h + 16
        draw.line([(line_x2_0, y2), (line_x2_0 + line_w2, y2)], fill=COLOR_BORDER, width=1)
        y2 += 14
        skills_list = sorted(s for s in SKILLS_ORDER if s in character.get('prof_mult_dict', {}))
        for skill_name in skills_list:
            mod = get_skill_mod(character, skill_name)
            mod_str = f"+{mod}" if mod >= 0 else str(mod)
            prof = character['prof_mult_dict'][skill_name]
            left_part = f"  {skill_name}{star_str}" if prof else f"  {skill_name}"
            txt(x2, y2, left_part, font=font_body, color=COLOR_TEXT)
            left_end = x2 + _text_width(left_part)
            right_start = r2 - _text_width(mod_str)
            _draw_leader_dots(left_end, right_start, y2)
            txt(r2 - _text_width(mod_str), y2, mod_str, font=font_body, color=COLOR_TEXT)
            y2 += line_step
        t3c = time.perf_counter()
        print(f"  [текст] колонка 2 (навыки): {t3c - t3b:.3f} с")

        # —— Колонка 3: Бой и заклинания ——
        _draw_box(draw, col3_x1, box_top, col3_x2, box_bottom)
        x3, y3 = col3_x1 + 8, box_top + 10
        w3 = col3_x2 - col3_x1
        line_w3 = int(w3 * 0.70)
        line_x3_0 = col3_x1 + (w3 - line_w3) // 2
        hdr_combat = pre("⚔️ ", "") + "Бой"
        txt(col3_x1 + (w3 - _text_width(hdr_combat, font_section)) // 2, y3, hdr_combat, font=font_section, color=COLOR_TEXT)
        y3 += line_h + 16
        draw.line([(line_x3_0, y3), (line_x3_0 + line_w3, y3)], fill=COLOR_BORDER, width=1)
        y3 += 14
        txt(x3, y3, pre("🛡️ ", "- ") + "КБ: " + str(character.get('armor_class', 0)), font=font_body, color=COLOR_TEXT)
        y3 += line_step
        hp_cur = character.get('hit_points', 0)
        hp_max = character.get('max_hit_points', 0)
        hp_temp = character.get('temp_hit_points', 0)
        txt(x3, y3, pre("❤️ ", "- ") + f"ПЗ: {hp_cur} / {hp_max}", font=font_body, color=COLOR_TEXT)
        y3 += line_step
        if hp_temp:
            txt(x3, y3, pre("💫 ", "- ") + f"Врем. ПЗ: {hp_temp}", font=font_body, color=COLOR_TEXT)
            y3 += line_step
        hd_curr = character.get('hit_dice_count', 0)
        hd_max = character.get('hit_dice_max', 0)
        txt(x3, y3, pre("🎲 ", "- ") + f"КЗ: {hd_curr} из {hd_max}", font=font_body, color=COLOR_TEXT)
        y3 += line_step
        init = character.get('initiative', 0)
        init_str = f"+{init}" if init >= 0 else str(init)
        txt(x3, y3, pre("⚡ ", "- ") + f"Инициатива: {init_str}", font=font_body, color=COLOR_TEXT)
        y3 += line_step
        txt(x3, y3, pre("👣 ", "- ") + f"Скорость: {character.get('speed', 30)} футов", font=font_body, color=COLOR_TEXT)
        y3 += line_step
        money = _money_sum(character.get('money', {}))
        money_text = pre("💰 ", "- ") + f"Монеты: {money:.1f} зм"
        txt(x3, y3, money_text, font=font_body, color=COLOR_TEXT)
        y3 += line_step + 20

        spell_stat = get_spell_stat(character)
        if spell_stat:
            hdr_spells = pre("📜 ", "") + "Заклинания"
            txt(col3_x1 + (w3 - _text_width(hdr_spells, font_section)) // 2, y3, hdr_spells, font=font_section, color=COLOR_TEXT)
            y3 += line_h + 16
            draw.line([(line_x3_0, y3), (line_x3_0 + line_w3, y3)], fill=COLOR_BORDER, width=1)
            y3 += 14
            txt(x3, y3, pre("✨ ", "* ") + f"Хар-ка: {spell_stat}", font=font_body, color=COLOR_TEXT)
            y3 += line_step
            stat_key = _ability_to_stat_key(spell_stat)
            attack = dnd5e_data.calc_mod(stats.get(stat_key, 10)) + character.get('proficiency_bonus', 0)
            dc = 8 + attack
            txt(x3, y3, pre("🎯 ", "* ") + f"Бонус атаки: +{attack}", font=font_body, color=COLOR_TEXT)
            y3 += line_step
            txt(x3, y3, pre("🔮 ", "* ") + f"СЛ испытаний: {dc}", font=font_body, color=COLOR_TEXT)
        t3d = time.perf_counter()
        print(f"  [текст] колонка 3 (бой, заклинания): {t3d - t3c:.3f} с")
    print(f"[лист] текст (баннер, опыт, 3 колонки): {time.perf_counter() - t3:.3f} с (медленно из‑за Pilmoji: каждый эмодзи = загрузка и вставка картинки)")

    t4 = time.perf_counter()
    if path is None:
        fd, path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
    img.save(path, 'PNG')
    print(f"[лист] сохранение PNG: {time.perf_counter() - t4:.3f} с")
    print(f"[лист] всего: {time.perf_counter() - t0:.3f} с")
    return path
