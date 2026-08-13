# -*- coding: utf-8 -*-

# --- Azure OpenAI ---
# В СЕРВЕРНОМ режиме (USE_SERVER = True) ключ клиенту НЕ нужен — он лежит только
# на сервере (Render, переменная AZURE_API_KEY), и из раздаваемого .exe его не
# достать. Поэтому здесь пусто. Для локального режима сюда можно вернуть ключ.
AZURE_API_KEY   = ""
AZURE_ENDPOINT  = "https://sedogin-inc-sweden.openai.azure.com"   # <-- проверить/заполнить
AZURE_API_VERSION = "2025-01-01-preview"                  # версия API для vision-моделей

# Имя ДЕПЛОЙМЕНТА в вашем Azure-портале (не имя модели!).
# Создать деплоймент под самую качественную vision-модель (уровень GPT-5.x)
# можно в Azure AI Foundry за пару минут. Меняется одной строкой:
AZURE_DEPLOYMENT = "gpt-5.4"                          # <-- имя вашего деплоймента

# --- exiftool ---
# Внешний бесплатный бинарник (exiftool.org). Уже скачан в папке ./tools рядом
# с этим файлом — программа находит его автоматически. Если хотите указать свой,
# впишите полный путь к exe, например:  r"C:\Tools\exiftool\exiftool.exe".
# "exiftool" = взять из системного PATH.
EXIFTOOL_PATH = r"exiftool"

# --- Параметры модели gpt-5.x (reasoning-модель) ---
# gpt-5.x не принимает temperature и использует max_completion_tokens вместо
# max_tokens. reasoning_effort: minimal|low|medium|high (для кейвординга хватает
# low — быстрее и дешевле). Если деплоймент не поддерживает параметр —
# программа сама повторит запрос без него.
REASONING_EFFORT      = "low"
MAX_COMPLETION_TOKENS = 4000

# --- Обработка ---
MAX_WORKERS      = 3        # параллельных запросов к Azure (с оглядкой на rate limit)
MAX_IMAGE_SIDE   = 1536     # изображение ужимается до этой стороны перед отправкой в API
VIDEO_FRAMES     = 3        # кадры из видео: начало / середина / конец
KW_MIN, KW_MAX   = 48, 50   # ориентир по числу ключевых слов (в промпте)
KW_HARD_LIMIT    = 50       # жёсткий потолок: больше в файл не запишется
LOG_FILENAME     = "_stockkeyworder_log.json"

APP_VERSION = "1.0"   # показывается в заголовке; поднимай при выпуске обновлений
PREVIEW_PAGE_SIZE = 20   # сколько карточек рисуем за раз (CTk медленно создаёт виджеты)

# --- Режим работы ---
# USE_SERVER = False -> ПРОСТОЙ режим (как Sedvai): ключ Azure в программе, БЕЗ
#   входа/подписки, отец сразу работает. Для беты (защита — Budget-лимит в Azure).
# USE_SERVER = True  -> через сервер: он держит ключ, проверяет подписку/триал,
#   в приложении появляется вход/план. Включить, когда пойдёшь продавать чужим.
USE_SERVER = True

# --- Сервер (бэкенд-прокси SedStock) — используется только при USE_SERVER = True ---
# Боевой сервер на Render (держит ключ Azure, проверяет подписку/триал/лимиты).
SERVER_URL = "https://sedstock-server.onrender.com"

# Тайм-аут запросов к серверу (генерация может думать долго — даём с запасом)
SERVER_TIMEOUT = 200

# --- Оплата ---
# PAY_MODE = "paypal"      -> кнопка открывает PayPal.me с суммой; активируем вручную
#            "lemonsqueezy"-> авто-подписка через LemonSqueezy (когда настроишь)
PAY_MODE = "paypal"

# PayPal.me — БАЗОВАЯ ссылка (без суммы). К ней в коде добавляется /30USD и /4USD.
PAYPAL_ME = "https://www.paypal.me/TatsianaBartseneva"

# --- LemonSqueezy (для авто-режима, когда одобрят магазин) ---
# Checkout-ссылки создаются в кабинете LemonSqueezy под продукты (месяц/год).
CHECKOUT_URL_MONTHLY = "https://sedogin.lemonsqueezy.com/buy/REPLACE-MONTHLY"
CHECKOUT_URL_YEARLY  = "https://sedogin.lemonsqueezy.com/buy/REPLACE-YEARLY"
PRICE_MONTHLY = "$4 / месяц"
PRICE_YEARLY  = "$30 / год"

# Суммы для PayPal.me (в USD) по периодам
PAYPAL_AMOUNT = {"monthly": "4USD", "yearly": "30USD"}

# --- Лимиты в локальном режиме (USE_SERVER=False). На сервере лимиты свои. ---
LOCAL_TRIAL_DAY_LIMIT = 50   # триал: максимум фото в день

# Локальные файлы рядом с программой (создаются автоматически)
UPLOAD_SETTINGS_FILE  = "upload_settings.json"       # доступы FTP/SFTP (заморожено)
CUSTOM_INSTR_FILENAME = "ai_instructions.txt"        # свои инструкции для ИИ

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov"}

# ============================================================================
#  Импорты
# ============================================================================
import os
import io
import re
import sys
import json
import glob
import time
import uuid
import base64
import shutil
import hashlib
import webbrowser
import tempfile
import threading
import subprocess
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import winreg   # только Windows — для стабильного ID устройства
except Exception:
    winreg = None

try:
    import requests
except Exception:
    print("Не установлен requests:  pip install requests")
    raise

try:
    import customtkinter as ctk
    from tkinter import filedialog, BooleanVar
except Exception as e:  # pragma: no cover
    print("Не установлен customtkinter:  pip install customtkinter")
    raise

try:
    from PIL import Image
except Exception:
    print("Не установлен Pillow:  pip install pillow")
    raise

try:
    from openai import AzureOpenAI
except Exception:
    print("Не установлен openai SDK:  pip install openai")
    raise

# Ошибки, при которых обречён ВЕСЬ батч (неверный ключ/эндпоинт/деплоймент, нет
# сети) — на них обработку надо остановить, а не перебирать сотни файлов впустую.
try:
    from openai import (AuthenticationError, PermissionDeniedError,
                        NotFoundError, APIConnectionError)
    FATAL_EXC = (AuthenticationError, PermissionDeniedError,
                 NotFoundError, APIConnectionError)
except Exception:
    FATAL_EXC = ()

# moviepy импортируем лениво (нужен только при наличии видео)

# ============================================================================
#  Локализация (RU / EN). Язык выбирается при регистрации и в меню профиля,
#  хранится в ui_settings.json. tr(ru, en) отдаёт нужную строку по текущему LANG.
#  Для нового пользователя (реклама на Reddit и т.п.) по умолчанию — английский.
# ============================================================================
LANG = "en"   # "en" | "ru" — перезаписывается из настроек при старте


def tr(ru: str, en: str) -> str:
    return ru if LANG == "ru" else en


def set_lang(code: str) -> None:
    global LANG
    LANG = "ru" if code == "ru" else "en"


# ============================================================================
#  Каталоги программы — с учётом сборки в .exe (PyInstaller)
# ============================================================================
def _base_dir() -> Path:
    """Папка для ЗАПИСИ пользовательских данных (настройки, инструкции, логи).
    Должна быть постоянной И записываемой. В собранном виде пишем в
    %LOCALAPPDATA%\\SedStock — это работает и для обычного .exe, и ОБЯЗАТЕЛЬНО
    для Microsoft Store (MSIX), где папка установки доступна только для чтения.
    При обычном запуске скрипта — рядом со скриптом."""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") \
            or os.path.expanduser("~")
        try:
            d = Path(base) / "SedStock"
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            return Path(sys.executable).resolve().parent   # запасной путь
    return Path(__file__).resolve().parent


def _resource_dirs():
    """Где искать ресурсы (exiftool в ./tools): распаковка PyInstaller (_MEIPASS),
    папка рядом с .exe, папка скрипта, текущая директория."""
    dirs = []
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        dirs.append(Path(mei))
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent)
    dirs.append(Path(__file__).resolve().parent)
    dirs.append(Path.cwd())
    seen, out = set(), []
    for d in dirs:
        if str(d) not in seen:
            seen.add(str(d))
            out.append(d)
    return out


# ============================================================================
#  Поиск exiftool: явный путь -> ./tools (во всех каталогах) -> системный PATH
# ============================================================================
def resolve_exiftool() -> str:
    # 1) явно указанный существующий файл
    p = EXIFTOOL_PATH
    if p and p.lower() != "exiftool" and Path(p).is_file():
        return str(Path(p))
    # 2) ./tools в любом из каталогов программы (работает и в .exe)
    for base in _resource_dirs():
        for cand in glob.glob(str(base / "tools" / "**" / "exiftool.exe"), recursive=True):
            return cand
        for name in ("exiftool.exe", "exiftool"):
            cand = base / "tools" / name
            if cand.is_file():
                return str(cand)
    # 3) из системного PATH
    found = shutil.which(EXIFTOOL_PATH) or shutil.which("exiftool")
    if found:
        return found
    return EXIFTOOL_PATH  # последний шанс — пусть subprocess сам сообщит об ошибке


EXIFTOOL_BIN = resolve_exiftool()

# На macOS/Linux exiftool — perl-скрипт; после распаковки .app право на запуск
# может слететь. Ставим его принудительно (на Windows os.name=='nt' — пропускаем).
if os.name != "nt":
    try:
        if EXIFTOOL_BIN and Path(EXIFTOOL_BIN).is_file():
            os.chmod(EXIFTOOL_BIN, 0o755)
    except Exception:
        pass

# ============================================================================
#  Оформление — минималистичный «apple-style»: светлый фон, синий акцент,
#  много воздуха, системный шрифт. Меняется только вид, не механика.
# ============================================================================
COL_BG      = "#f5f5f7"   # светло-серый фон (как apple.com)
COL_PANEL   = "#ffffff"   # белые панели/карточки
COL_CARD    = "#ffffff"
COL_ACCENT  = "#0071e3"   # фирменный синий Apple
COL_ACCENT2 = "#0062c4"   # притемнённый синий для hover
COL_ONACC   = "#ffffff"   # текст на синей кнопке
COL_TEXT    = "#1d1d1f"   # почти чёрный — основной текст
COL_MUTED   = "#6e6e73"   # серый — второстепенный текст
COL_BORDER  = "#d2d2d7"   # тонкие разделители/рамки
COL_HOVER   = "#e8e8ed"   # светлый hover для вторичных кнопок
COL_TRACK   = "#e3e3e8"   # дорожка прогресс-бара
COL_OK      = "#248a3d"   # зелёный (читаемый на белом)
COL_ERR     = "#d70015"   # красный
COL_SKIP    = "#b25000"   # янтарный/коричневый
COL_EDIT    = "#ff9500"   # оранжевый Apple — метка EDITORIAL
FONT_UI     = "Segoe UI"  # чистый системный шрифт (замена SF Pro на Windows)


def _darken(hex_color: str, factor: float = 0.85) -> str:
    """Затемнить цвет (для эффекта «придавливания» кнопки при клике)."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{int(r*factor):02x}{int(g*factor):02x}{int(b*factor):02x}"
    except Exception:
        return hex_color


class Btn3D(ctk.CTkFrame):
    """Объёмная кнопка в стиле Duolingo: у цветных (accent/ok) снизу тёмное
    «ребро», на котором стоит кнопка; при нажатии она садится на ребро (эффект
    придавливания). Прозрачные ghost/muted остаются плоскими, только меняют цвет.

    Обёртка — фрейм, но проксирует configure(state=/text=/…) и cget внутрь на
    саму кнопку, поэтому её можно использовать как обычную кнопку:
    .pack(), .configure(state="disabled"), .configure(text="…") и т.д.
    """

    _PRESETS = {
        "accent": (COL_ACCENT, COL_ACCENT2, COL_ONACC, 0),
        "ok":     (COL_OK, "#1f7a34", COL_ONACC, 0),
        "ghost":  ("transparent", COL_HOVER, COL_ACCENT, 1),
        "muted":  (COL_HOVER, COL_BORDER, COL_TEXT, 0),
    }
    _RAISED = ("accent", "ok")  # у кого есть объёмное ребро

    def __init__(self, master, text, command=None, kind="accent",
                 width=140, height=38, font_size=13):
        fg, hover, txt, bw = self._PRESETS.get(kind, self._PRESETS["accent"])
        self._kind = kind
        self._fg = fg
        self._h = height
        self._drop = 5 if kind in self._RAISED else 0   # глубина ребра
        self._after = None

        edge = _darken(fg, 0.55) if kind in self._RAISED else "transparent"
        super().__init__(master, width=width, height=height + self._drop,
                         corner_radius=13, fg_color=edge, border_width=0)
        self.pack_propagate(False)
        self.grid_propagate(False)

        self._btn = ctk.CTkButton(
            self, text=text, height=height, corner_radius=11, fg_color=fg,
            hover_color=hover, text_color=txt, border_width=bw,
            border_color=COL_BORDER, font=(FONT_UI, font_size, "bold"))
        # в покое кнопка приподнята — снизу выглядывает тёмное ребро
        self._btn.place(x=0, y=0, relwidth=1.0)

        for a in ("_canvas", "_text_label", "_image_label"):
            w = getattr(self._btn, a, None)
            if w is not None:
                w.bind("<ButtonPress-1>", self._on_press, add="+")
        if command:
            self._btn.configure(command=command)

    # -- анимация нажатия ---------------------------------------------------
    def _on_press(self, _e=None):
        if str(self._btn.cget("state")) == "disabled":
            return
        try:
            if self._drop:
                # садится на ребро: кнопка вырастает на высоту ребра и закрывает его
                self._btn.configure(height=self._h + self._drop)
            else:
                self._btn.configure(
                    fg_color=(_darken(self._fg, 0.62)
                              if self._fg != "transparent" else "#d7d7de"))
        except Exception:
            return
        # форсируем немедленную перерисовку: команда кнопки может тут же открыть
        # модальный диалог (напр. «Выбрать папку») и заблокировать цикл событий —
        # без этого приседание рисуется с задержкой, уже после закрытия диалога
        try:
            self.update_idletasks()
        except Exception:
            pass
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except Exception:
                pass
        self._after = self.after(120, self._spring)

    def _spring(self):
        self._after = None
        try:
            if not self._btn.winfo_exists():
                return
            if self._drop:
                self._btn.configure(height=self._h)  # снова приподнята, ребро видно
            else:
                self._btn.configure(fg_color=self._fg)
        except Exception:
            pass

    # -- проксирование под обычную кнопку -----------------------------------
    # fg_color/hover_color сюда НЕ входят: они относятся к фрейму-ребру, плюс CTk
    # при создании дочерней кнопки спрашивает у мастера cget("fg_color").
    _BTN_KEYS = {"text", "command", "state", "text_color", "image", "font"}

    def configure(self, **kwargs):
        if not hasattr(self, "_btn"):          # ещё в процессе __init__
            return super().configure(**kwargs)
        btn_kw = {k: kwargs.pop(k) for k in list(kwargs) if k in self._BTN_KEYS}
        # неактивную кнопку показываем без объёмного ребра
        if "state" in btn_kw and self._drop:
            try:
                super().configure(
                    fg_color=(_darken(self._fg, 0.55)
                              if str(btn_kw["state"]) != "disabled"
                              else COL_BORDER))
            except Exception:
                pass
        if btn_kw:
            self._btn.configure(**btn_kw)
        if kwargs:
            super().configure(**kwargs)

    def cget(self, key):
        if key in self._BTN_KEYS and hasattr(self, "_btn"):
            return self._btn.cget(key)
        return super().cget(key)

# ============================================================================
#  Промпты для vision-модели
# ============================================================================
SYSTEM_PROMPT = (
    "Ты — эксперт по метаданным для микростоковых агентств "
    "(Shutterstock, Adobe Stock, iStock, Pond5). Твоя задача — по визуальному "
    "материалу составить продающие, релевантные метаданные для продажи на стоках. "
    "БАЗОВОЕ ПРАВИЛО (всегда): не выдумывай факты — если чего-то не видно на "
    "изображении или в кадре, не указывай это в title, description и keywords. "
    "Всегда отвечай ТОЛЬКО валидным JSON-объектом, без markdown-разметки, без ```-блоков, "
    "без каких-либо пояснений до или после JSON."
)

# Свои инструкции пользователя (из окна «Инструкции ИИ»). Пусто -> как обычно.
# Добавляются к системному промпту, но НЕ отменяют жёсткие правила формата.
CUSTOM_INSTRUCTIONS = ""

_JSON_SHAPE = (
    '{\n'
    '  "title": "продающий заголовок ровно из 10-12 слов",\n'
    '  "description": "РОВНО ОДНО предложение, описывающее содержание",\n'
    '  "keywords": ["слово", "слово", "..."],\n'
    '  "age": "возраст ЧИСЛОМ, например 35, либо пусто",\n'
    '  "is_editorial": true либо false\n'
    '}'
)

_DESC_RULE = "description: строго ОДНО предложение (не два и не больше), на английском."

_KW_RULE = (
    f"keywords: ОБЯЗАТЕЛЬНО не меньше {KW_MIN} и не больше {KW_MAX} штук, на английском, "
    "от общих понятий к частным деталям (объекты, действия, настроение/эмоция, концепция, "
    "цвета, композиция), без дубликатов. КРИТИЧЕСКИ ВАЖНО: КАЖДОЕ ключевое слово — это "
    "РОВНО ОДНО слово. НИКАКИХ словосочетаний из двух и более слов "
    "(например нельзя 'yellow flower' — только отдельно 'yellow' и 'flower')."
)

_AGE_RULE = (
    "age: если на изображении/в кадре ЕСТЬ человек — ОБЯЗАТЕЛЬНО оцени возраст "
    "главного человека и верни ТОЛЬКО ЧИСЛО (примерный возраст в годах), например "
    "\"35\" или \"7\". Без слов, без 'years', без 'лет' — только цифры. "
    "Если людей на изображении нет вообще — верни пустую строку \"\". "
    "Не дублируй возраст в массиве keywords — программа сама поставит его 5-м словом."
)

_TITLE_RULE = (
    "title: СТРОГО 10–12 слов, на английском, естественная осмысленная фраза "
    "(не набор тегов через запятую). Заголовок должен конкретно и точно описывать "
    "именно этот кадр."
)

_DISTINCT_RULE = (
    "УНИКАЛЬНОСТЬ (важно): удели особое внимание отличительным деталям именно этого "
    "кадра — выражение лица, эмоция, поза, жест, направление взгляда, ракурс, действие "
    "в моменте — и обязательно отрази их в title. Похожие кадры (тот же человек, то же "
    "место, но другое выражение лица/поза) ДОЛЖНЫ получать заметно разные заголовки; "
    "одинаковые или почти одинаковые title недопустимы."
)

_SPECIFIC_RULE = (
    "КОНКРЕТИКА (глубже анализируй): если объект/растение/животное/порода/сорт/блюдо/"
    "модель/достопримечательность ЧЁТКО узнаваемы — назови их КОНКРЕТНО в keywords "
    "(и по возможности в title). Например не просто 'flower', а 'tulip'/'rose'; "
    "не 'dog', а 'labrador'; не 'bird', а 'sparrow'. НО ОГРАНИЧЕНИЕ: если точно "
    "определить нельзя — НЕ ГАДАЙ, оставайся на общем уровне. Базовое правило "
    "«не выдумывай факты» важнее конкретики: лучше общее и верное, чем конкретное "
    "и ошибочное."
)

_EDITORIAL_RULE = (
    "Поле is_editorial: поставь true, если контент выглядит как РЕДАКЦИОННЫЙ "
    "(editorial) — публичное место, реальное событие, узнаваемые люди/лица, "
    "бренды, логотипы, товарные знаки, вывески, номера машин в кадре. "
    "Поставь false, если это обычный COMMERCIAL — постановочный или обезличенный "
    "кадр без узнаваемых людей и брендов. Если сомневаешься между ними — выбери true. "
    "Для description дай нейтральное фактическое описание того, что видно, без домыслов."
)

def build_image_instruction():
    return (
        "Проанализируй это изображение и верни ТОЛЬКО JSON строго такой формы:\n"
        f"{_JSON_SHAPE}\n\n"
        f"{_TITLE_RULE}\n"
        f"{_DESC_RULE}\n"
        f"{_AGE_RULE}\n"
        f"{_KW_RULE}\n"
        f"{_SPECIFIC_RULE}\n"
        f"{_DISTINCT_RULE}\n"
        f"{_EDITORIAL_RULE}"
    )

def build_video_instruction():
    return (
        f"На входе {VIDEO_FRAMES} последовательных кадра ОДНОГО видео "
        "(начало, середина, конец). Это НЕ три отдельных изображения — опиши "
        "видео целиком как единый ролик, учитывая развитие сцены во времени.\n"
        "Верни ТОЛЬКО JSON строго такой формы:\n"
        f"{_JSON_SHAPE}\n\n"
        f"{_TITLE_RULE}\n"
        f"{_DESC_RULE}\n"
        f"{_AGE_RULE}\n"
        f"{_KW_RULE}\n"
        f"{_SPECIFIC_RULE}\n"
        f"{_DISTINCT_RULE}\n"
        f"{_EDITORIAL_RULE}"
    )

# ============================================================================
#  Azure OpenAI клиент
# ============================================================================
def make_client():
    return AzureOpenAI(
        api_key=AZURE_API_KEY,
        azure_endpoint=AZURE_ENDPOINT,
        api_version=AZURE_API_VERSION,
    )


# ============================================================================
#  ==== АВТОРИЗАЦИЯ / СЕРВЕР ====
#  Приложение работает через сервер: он держит ключ Azure, проверяет подписку.
#  Здесь — ID устройства, хранение токена и вызовы серверных эндпоинтов.
# ============================================================================
AUTH_TOKEN = None       # текущий токен (после входа/регистрации)
AUTH_STATUS = None      # последний статус подписки (dict со сервера)


class AuthError(Exception):
    """Ошибка входа/регистрации — текст показываем пользователю."""


class SubscriptionRequired(Exception):
    """Нет активной подписки/триала (сервер вернул 402/401)."""


class QuotaExceeded(Exception):
    """Исчерпан лимит (429)."""


class ServerError(Exception):
    """Проблема связи с сервером или некорректный ответ."""


def _device_id() -> str:
    """Стабильный ID устройства: MachineGuid из реестра Windows, иначе — UUID,
    сохранённый локально. Нужен для привязки безлимита и защиты триала."""
    if winreg is not None:
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                               r"SOFTWARE\Microsoft\Cryptography")
            val, _ = winreg.QueryValueEx(k, "MachineGuid")
            winreg.CloseKey(k)
            if val:
                return "win-" + str(val)
        except Exception:
            pass
    try:
        p = _app_dir() / "device.id"
        if p.exists():
            v = p.read_text(encoding="utf-8").strip()
            if v:
                return v
        v = "uuid-" + uuid.uuid4().hex
        p.write_text(v, encoding="utf-8")
        return v
    except Exception:
        return "uuid-" + uuid.uuid4().hex


def _auth_file() -> Path:
    return _app_dir() / "auth.json"


def save_token(token: str):
    try:
        _auth_file().write_text(json.dumps({"token": token}), encoding="utf-8")
    except Exception:
        pass


def load_token():
    try:
        p = _auth_file()
        if p.exists():
            return (json.loads(p.read_text(encoding="utf-8")) or {}).get("token")
    except Exception:
        pass
    return None


def clear_token():
    global AUTH_TOKEN, AUTH_STATUS
    AUTH_TOKEN = None
    AUTH_STATUS = None
    try:
        f = _auth_file()
        if f.exists():
            f.unlink()
    except Exception:
        pass


def _use_token(tok: str):
    """Положить сохранённый токен в память (для автологина при старте)."""
    global AUTH_TOKEN
    AUTH_TOKEN = tok


def _post(path: str, payload: dict, timeout=15):
    url = SERVER_URL.rstrip("/") + path
    try:
        return requests.post(url, json=payload, timeout=timeout)
    except Exception as e:
        raise ServerError(tr(f"Нет связи с сервером. Проверьте интернет.\n({e})",
                             f"No connection to the server. Check your internet.\n({e})"))


# ----------------------------------------------------------------------------
#  ЛОКАЛЬНЫЙ бэкенд (USE_SERVER = False): те же вход/регистрация/триал, но данные
#  хранятся в JSON рядом с программой (как Sedvai), а ИИ вызывается напрямую.
#  Проверки локальные (их можно обойти) — для беты этого достаточно; настоящая
#  защита включится вместе с сервером (USE_SERVER = True).
# ----------------------------------------------------------------------------
LOCAL_FATHER_CODE = "father"   # локальный код безлимита
LOCAL_TRIAL_DAYS = 3


def _local_db_path() -> Path:
    return _app_dir() / "local_users.json"


def _local_load() -> dict:
    try:
        p = _local_db_path()
        if p.exists():
            db = json.loads(p.read_text(encoding="utf-8"))
            db.setdefault("users", {})
            db.setdefault("codes", {})
            db.setdefault("device_trials", {})
            db["codes"].setdefault(LOCAL_FATHER_CODE, {"plan": "unlimited", "used_by": None})
            return db
    except Exception:
        pass
    return {"users": {}, "device_trials": {},
            "codes": {LOCAL_FATHER_CODE: {"plan": "unlimited", "used_by": None}}}


def _local_save(db: dict):
    try:
        _local_db_path().write_text(json.dumps(db, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    except Exception:
        pass


def _hash_pw(pw: str, salt: str = None) -> str:
    salt = salt or uuid.uuid4().hex[:16]
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return f"{salt}${h}"


def _check_pw(pw: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
        return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"),
                                   salt.encode("utf-8"), 100_000).hex() == h
    except Exception:
        return False


def _local_day() -> str:
    import datetime as _dt
    return _dt.datetime.utcnow().strftime("%Y-%m-%d")


def _local_day_used(u: dict) -> int:
    return u.get("day_count", 0) if u.get("usage_day") == _local_day() else 0


def _local_status(u: dict) -> dict:
    now = int(time.time())
    plan = u.get("plan", "none")
    email = u.get("email", "")
    day_used = _local_day_used(u)
    if plan == "unlimited":
        return {"state": "unlimited", "active": True, "days_left": -1,
                "quota": -1, "used": day_used, "remaining": -1,
                "day_used": day_used, "day_limit": -1, "email": email}
    if plan == "paid" and u.get("paid_until", 0) > now:
        d = max(0, (u["paid_until"] - now) // 86400)
        return {"state": "paid", "active": True, "days_left": d,
                "quota": -1, "used": day_used, "remaining": -1,
                "day_used": day_used, "day_limit": -1, "email": email}
    if plan == "trial":
        end = u.get("trial_start", 0) + LOCAL_TRIAL_DAYS * 86400
        if now < end:
            d = max(0, (end - now + 86399) // 86400)
            rem = max(0, LOCAL_TRIAL_DAY_LIMIT - day_used)
            return {"state": "trial", "active": True, "days_left": d,
                    "quota": LOCAL_TRIAL_DAY_LIMIT, "used": day_used, "remaining": rem,
                    "day_used": day_used, "day_limit": LOCAL_TRIAL_DAY_LIMIT, "email": email}
        return {"state": "trial_expired", "active": False, "days_left": 0,
                "quota": 0, "used": 0, "remaining": 0,
                "day_used": day_used, "day_limit": 0, "email": email}
    return {"state": "none", "active": False, "days_left": 0,
            "quota": 0, "used": 0, "remaining": 0,
            "day_used": day_used, "day_limit": 0, "email": email}


def _local_check_limit():
    """Локальный дневной лимит триала. Кидает QuotaExceeded, если исчерпан."""
    if not AUTH_TOKEN:
        return
    u = _local_load()["users"].get(AUTH_TOKEN)
    if not u:
        return
    plan = u.get("plan", "none")
    if plan in ("unlimited", "paid"):
        return
    if plan == "trial" and _local_day_used(u) >= LOCAL_TRIAL_DAY_LIMIT:
        raise QuotaExceeded(tr(
            f"Дневной лимит {LOCAL_TRIAL_DAY_LIMIT} фото исчерпан. "
            f"Приходите завтра или оформите подписку.",
            f"Daily limit of {LOCAL_TRIAL_DAY_LIMIT} photos reached. "
            f"Come back tomorrow or get a subscription."))


def _local_bump_usage():
    """+1 к дневному расходу локального юзера (с обнулением при смене дня)."""
    if not AUTH_TOKEN:
        return
    db = _local_load()
    u = db["users"].get(AUTH_TOKEN)
    if not u:
        return
    day = _local_day()
    u["day_count"] = (u.get("day_count", 0) + 1) if u.get("usage_day") == day else 1
    u["usage_day"] = day
    _local_save(db)


def api_register(email: str, password: str, code: str = "") -> dict:
    global AUTH_TOKEN, AUTH_STATUS
    if USE_SERVER:
        r = _post("/register", {"email": email, "password": password,
                                "code": code, "device_id": _device_id()})
        data = r.json() if r.content else {}
        if r.status_code != 200:
            raise AuthError(data.get("error") or tr("Не удалось зарегистрироваться",
                                                    "Registration failed"))
        AUTH_TOKEN = data["token"]
        AUTH_STATUS = data.get("status")
        save_token(AUTH_TOKEN)
        return data
    # --- локально ---
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email:
        raise AuthError(tr("Некорректный email", "Invalid email"))
    if len(password) < 6:
        raise AuthError(tr("Пароль минимум 6 символов",
                           "Password must be at least 6 characters"))
    db = _local_load()
    if email in db["users"]:
        raise AuthError(tr("Такой email уже зарегистрирован",
                           "This email is already registered"))
    dev = _device_id()
    plan, device_locked = "none", 0
    code = (code or "").strip().lower()
    if code:
        c = db["codes"].get(code)
        if not c:
            raise AuthError(tr("Неверный код", "Invalid code"))
        if c.get("used_by"):
            raise AuthError(tr("Этот код уже был использован", "This code has already been used"))
        plan, device_locked = c["plan"], 1
        c["used_by"] = email
    db["users"][email] = {"email": email, "pw": _hash_pw(password), "plan": plan,
                          "trial_start": 0, "paid_until": 0,
                          "device_id": dev, "device_locked": device_locked}
    _local_save(db)
    AUTH_TOKEN = email
    save_token(email)
    AUTH_STATUS = _local_status(db["users"][email])
    return {"token": email, "status": AUTH_STATUS}


def api_login(email: str, password: str) -> dict:
    global AUTH_TOKEN, AUTH_STATUS
    if USE_SERVER:
        r = _post("/login", {"email": email, "password": password,
                             "device_id": _device_id()})
        data = r.json() if r.content else {}
        if r.status_code != 200:
            raise AuthError(data.get("message") or data.get("error")
                            or tr("Не удалось войти", "Sign-in failed"))
        AUTH_TOKEN = data["token"]
        AUTH_STATUS = data.get("status")
        save_token(AUTH_TOKEN)
        return data
    # --- локально ---
    email = (email or "").strip().lower()
    db = _local_load()
    u = db["users"].get(email)
    if not u or not _check_pw(password, u.get("pw", "")):
        raise AuthError(tr("Неверный email или пароль", "Wrong email or password"))
    if u.get("device_locked"):
        dev = _device_id()
        if u.get("device_id") and u["device_id"] != dev:
            raise AuthError(tr("Этот аккаунт привязан к другому компьютеру.",
                               "This account is locked to another computer."))
        if not u.get("device_id"):
            u["device_id"] = dev
            _local_save(db)
    AUTH_TOKEN = email
    save_token(email)
    AUTH_STATUS = _local_status(u)
    return {"token": email, "status": AUTH_STATUS}


def local_email_exists(email: str) -> bool:
    """Есть ли уже такой email в локальной базе (для подсказок на экране входа)."""
    if USE_SERVER:
        return False
    email = (email or "").strip().lower()
    return email in _local_load().get("users", {})


def api_status():
    """Возвращает статус подписки/триала (dict) или None."""
    global AUTH_STATUS
    if not AUTH_TOKEN:
        return None
    if USE_SERVER:
        try:
            r = _post("/status", {"token": AUTH_TOKEN})
        except ServerError:
            return None
        if r.status_code != 200:
            return None
        AUTH_STATUS = (r.json() or {}).get("status")
        return AUTH_STATUS
    # --- локально ---
    db = _local_load()
    u = db["users"].get(AUTH_TOKEN)
    if not u:
        return None
    AUTH_STATUS = _local_status(u)
    return AUTH_STATUS


def api_start_trial():
    global AUTH_STATUS
    if USE_SERVER:
        r = _post("/start_trial", {"token": AUTH_TOKEN})
        data = r.json() if r.content else {}
        if r.status_code != 200:
            raise AuthError(data.get("message") or data.get("error")
                            or tr("Не удалось начать пробный период",
                                  "Couldn't start the free trial"))
        AUTH_STATUS = data.get("status")
        return AUTH_STATUS
    # --- локально ---
    db = _local_load()
    u = db["users"].get(AUTH_TOKEN)
    if not u:
        raise AuthError(tr("Требуется вход", "Sign-in required"))
    st = _local_status(u)
    if st["active"]:
        AUTH_STATUS = st
        return st
    dev = u.get("device_id") or _device_id()
    if db["device_trials"].get(dev):
        raise AuthError(tr("На этом устройстве пробный период уже был использован.",
                           "The free trial has already been used on this device."))
    u["plan"] = "trial"
    u["trial_start"] = int(time.time())
    db["device_trials"][dev] = int(time.time())
    _local_save(db)
    AUTH_STATUS = _local_status(u)
    return AUTH_STATUS


def api_vision(body: dict) -> str:
    """Шлёт запрос модели на сервер, возвращает текст ответа. На 402/401/429
    кидает специфичные исключения, чтобы приложение показало окно плана."""
    if not AUTH_TOKEN:
        raise SubscriptionRequired(tr("Требуется вход", "Sign-in required"))
    r = _post("/vision", {"token": AUTH_TOKEN, "body": body}, timeout=SERVER_TIMEOUT)
    if r.status_code == 200:
        try:
            return r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, ValueError):
            raise ServerError(tr("Некорректный ответ сервера", "Invalid server response"))
    try:
        data = r.json()
    except Exception:
        data = {}
    msg = data.get("message") or data.get("error") or tr(f"Ошибка сервера ({r.status_code})",
                                                         f"Server error ({r.status_code})")
    if r.status_code in (401, 402):
        raise SubscriptionRequired(msg)
    if r.status_code == 429:
        raise QuotaExceeded(msg)
    raise ServerError(msg)


def _b64_data_url(jpeg_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


def _extract_json(text: str) -> dict:
    """Достаёт JSON-объект из ответа модели, даже если модель добавила обёртку."""
    text = text.strip()
    # снять возможные ```json ... ``` ограждения
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # взять от первой { до последней }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("Модель вернула не-JSON ответ: " + text[:200])


# Мусорные токены после дробления словосочетаний на слова
_KW_STOPWORDS = {
    "a", "an", "the", "of", "on", "in", "with", "and", "or", "to", "for", "at", "by",
    "is", "are", "as", "from", "into", "over", "under", "years", "year",
}


def _to_single_words(items) -> list:
    """Приводит ключевые слова к формату «одно слово = одно значение»: дробит
    словосочетания на отдельные слова, чистит пунктуацию, выкидывает служебные
    слова и дубли, сохраняя порядок."""
    if isinstance(items, str):
        items = re.split(r"[,;\n]", items)
    out, seen = [], set()
    for it in items:
        for w in re.split(r"\s+", str(it).strip()):
            w = w.strip().strip(".,;:!?\"'()[]{}").strip()
            wl = w.lower()
            if len(w) >= 2 and wl not in _KW_STOPWORDS and wl not in seen:
                seen.add(wl)
                out.append(w)
    return out


def _normalize_meta(raw: dict) -> dict:
    title = str(raw.get("title", "")).strip()
    description = str(raw.get("description", "")).strip()
    # keywords: только ОДИНОЧНЫЕ слова (словосочетания дробим), дедуп
    keywords = _to_single_words(raw.get("keywords", []))
    if not title:
        raise ValueError("В ответе модели пустой title")
    # возраст — ТОЛЬКО ЧИСЛО; ставим РОВНО 5-м (позиции 1–4 под основной сюжет).
    # На всякий случай вытаскиваем только цифры (если модель припишет слова).
    _am = re.search(r"\d{1,3}", str(raw.get("age", "")))
    age = _am.group(0) if _am else ""
    if age:
        keywords = [k for k in keywords if k != age]   # убрать дубль возраста
        keywords.insert(min(4, len(keywords)), age)    # индекс 4 = 5-е место
    keywords = keywords[:KW_HARD_LIMIT]   # жёсткий потолок ключевых слов
    ed = raw.get("is_editorial", False)
    if isinstance(ed, str):
        ed = ed.strip().lower() in ("true", "1", "yes", "да", "editorial")
    return {"title": title[:200], "description": description,
            "keywords": keywords, "is_editorial": bool(ed), "age": age}


def _create_completion(client, base_kwargs: dict, optional_kwargs: dict):
    """Вызывает модель; если деплоймент не поддерживает какой-то опциональный
    параметр (reasoning_effort / max_completion_tokens и т.п.) — убирает именно
    его из запроса и повторяет, не роняя обработку."""
    kwargs = dict(base_kwargs)
    kwargs.update(optional_kwargs)
    for _ in range(len(optional_kwargs) + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            msg = str(e).lower()
            removed = False
            for k in list(kwargs.keys()):
                if k not in base_kwargs and k.lower() in msg:
                    kwargs.pop(k, None)
                    removed = True
            if not removed:
                raise
    return client.chat.completions.create(**kwargs)


def call_vision(client, jpeg_images, instruction: str) -> dict:
    """jpeg_images — список bytes (1 для фото, 3 для видео)."""
    content = [{"type": "text", "text": instruction}]
    for img in jpeg_images:
        content.append({
            "type": "image_url",
            "image_url": {"url": _b64_data_url(img)},
        })
    system_text = SYSTEM_PROMPT
    if CUSTOM_INSTRUCTIONS.strip():
        system_text += (
            "\n\nДОПОЛНИТЕЛЬНЫЕ ПОЖЕЛАНИЯ ПОЛЬЗОВАТЕЛЯ по стилю и содержанию "
            "(учитывай их при подборе title/description/keywords, НО жёсткие правила "
            "формата и лимиты выше остаются в силе):\n" + CUSTOM_INSTRUCTIONS.strip())
    messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": content},
    ]
    if USE_SERVER:
        # запрос уходит на наш сервер (он держит ключ, проверяет подписку)
        body = {
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
        }
        if REASONING_EFFORT:
            body["reasoning_effort"] = REASONING_EFFORT
        text = api_vision(body)   # SubscriptionRequired/QuotaExceeded/ServerError
    else:
        # простой режим: напрямую в Azure через SDK (ключ в программе)
        _local_check_limit()   # дневной лимит триала (может кинуть QuotaExceeded)
        base_kwargs = {
            "model": AZURE_DEPLOYMENT,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        optional_kwargs = {"max_completion_tokens": MAX_COMPLETION_TOKENS}
        if REASONING_EFFORT:
            optional_kwargs["reasoning_effort"] = REASONING_EFFORT
        resp = _create_completion(client, base_kwargs, optional_kwargs)
        text = resp.choices[0].message.content or ""
        _local_bump_usage()    # успешный вызов -> +1 к дневному расходу

    if not text.strip():
        raise ValueError("Модель вернула пустой ответ "
                         "(возможно, не хватило max_completion_tokens)")
    return _normalize_meta(_extract_json(text))

# ============================================================================
#  Подготовка картинок
# ============================================================================
def _flatten_to_white(pil_img: Image.Image) -> Image.Image:
    """Убирает прозрачность, подкладывая БЕЛЫЙ фон. Без этого PIL при переводе
    RGBA->RGB делает прозрачные пиксели ЧЁРНЫМИ — и модель у PNG на прозрачном
    фоне видит «объект на чёрном фоне». Стоковые PNG подразумевают белый фон."""
    if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
        rgba = pil_img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])   # альфа как маска
        return bg
    return pil_img.convert("RGB")


def image_to_jpeg_bytes(pil_img: Image.Image, max_side=MAX_IMAGE_SIDE) -> bytes:
    img = _flatten_to_white(pil_img)
    w, h = img.size
    scale = max(w, h) / max_side
    if scale > 1:
        img = img.resize((int(w / scale), int(h / scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def make_thumbnail(pil_img: Image.Image, size=(260, 175)) -> Image.Image:
    im = _flatten_to_white(pil_img)
    im.thumbnail(size, Image.LANCZOS)
    return im


def load_photo_jpeg(path: Path) -> list:
    with Image.open(path) as im:
        return [image_to_jpeg_bytes(im)]


def prepare_photo(path: Path):
    """-> (список jpeg-bytes для модели, PIL-миниатюра для предпросмотра)."""
    with Image.open(path) as im:
        im.load()   # НЕ конвертируем в RGB тут — иначе потеряем альфу; flatten ниже
        return [image_to_jpeg_bytes(im)], make_thumbnail(im)


def extract_video_frames(path: Path) -> list:
    """3 кадра: начало / середина / конец. Возвращает список jpeg-bytes."""
    jpegs, _ = prepare_video(path)
    return jpegs


def prepare_video(path: Path):
    """-> (jpeg-bytes 3 кадров для модели, PIL-миниатюра из среднего кадра)."""
    from moviepy import VideoFileClip  # moviepy 2.x
    jpegs, pil_frames = [], []
    with VideoFileClip(str(path)) as clip:
        dur = clip.duration or 0.0
        if dur <= 0:
            times = [0.0]
        else:
            # чуть отступаем от самых краёв — там часто чёрные/служебные кадры
            times = [min(dur * f, max(dur - 0.05, 0.0)) for f in (0.02, 0.5, 0.98)]
        for t in times:
            pil = Image.fromarray(clip.get_frame(t))  # numpy HxWx3 uint8 -> PIL
            pil_frames.append(pil)
            jpegs.append(image_to_jpeg_bytes(pil))
    mid = pil_frames[len(pil_frames) // 2]
    return jpegs, make_thumbnail(mid)

# ============================================================================
#  Запись метаданных через exiftool
# ============================================================================
def _run_exiftool(args) -> None:
    # Аргументы (теги, значения, путь к файлу) пишем в UTF-8 argfile и передаём
    # через -@. На Windows argv кодируется в системную ANSI-кодовую страницу и
    # теряет не-ASCII символы (кириллицу, диакритику, эмодзи); argfile читается
    # exiftool как UTF-8 и сохраняет всё. Заодно это снимает лимит длины
    # командной строки при больших списках ключевых слов.
    fd, argfile = tempfile.mkstemp(suffix=".txt", prefix="sedstock_et_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            for a in args:
                f.write(a + "\n")
        cmd = [EXIFTOOL_BIN, "-charset", "filename=utf8", "-@", argfile]
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
        out = (proc.stdout or b"").decode("utf-8", "replace")
        err = (proc.stderr or b"").decode("utf-8", "replace")
        if proc.returncode != 0:
            raise RuntimeError("exiftool: " + (err.strip() or out.strip() or "неизвестная ошибка"))
    finally:
        try:
            os.unlink(argfile)
        except OSError:
            pass


def write_photo_metadata(path: Path, meta: dict) -> None:
    args = [
        "-overwrite_original",
        "-codedcharacterset=utf8",
        "-charset", "iptc=UTF8",
        f"-IPTC:ObjectName={meta['title']}",
        f"-XMP-dc:Title={meta['title']}",
        f"-IPTC:Caption-Abstract={meta['description']}",
        f"-XMP-dc:Description={meta['description']}",
        # keywords перезаписываем, а не дополняем
        "-IPTC:Keywords=",
        "-XMP-dc:Subject=",
    ]
    for k in meta["keywords"]:
        args.append(f"-IPTC:Keywords={k}")
        args.append(f"-XMP-dc:Subject={k}")
    args.append(str(path))
    _run_exiftool(args)


def write_video_metadata(path: Path, meta: dict) -> None:
    args = [
        "-overwrite_original",
        "-charset", "utf8",
        f"-Keys:Title={meta['title']}",
        f"-Keys:Description={meta['description']}",
        f"-XMP-dc:Title={meta['title']}",
        f"-XMP-dc:Description={meta['description']}",
        "-XMP-dc:Subject=",
        f"-Keys:Keywords={', '.join(meta['keywords'])}",
    ]
    for k in meta["keywords"]:
        args.append(f"-XMP-dc:Subject={k}")
    args.append(str(path))
    _run_exiftool(args)


def save_video_poster(video_path: Path, meta: dict) -> Path:
    """Как в StockSubmitter: берём кадр из середины видео, сохраняем JPEG рядом
    с видео и вписываем в него те же метаданные (title/description/keywords).
    Многие стоки читают метаданные ролика именно из такого сопроводительного
    JPEG-постера. -> путь к созданному JPEG."""
    from moviepy import VideoFileClip  # moviepy 2.x
    dest = video_path.with_name(video_path.stem + ".jpg")
    if dest.exists():                       # не затираем существующее фото
        dest = video_path.with_name(video_path.stem + "_poster.jpg")
    with VideoFileClip(str(video_path)) as clip:
        dur = clip.duration or 0.0
        pil = Image.fromarray(clip.get_frame(dur / 2.0 if dur > 0 else 0.0))
    img = pil.convert("RGB")
    w, h = img.size
    scale = max(w, h) / 1920.0              # крупный кадр под сток
    if scale > 1:
        img = img.resize((int(w / scale), int(h / scale)), Image.LANCZOS)
    img.save(dest, "JPEG", quality=92)
    write_photo_metadata(dest, meta)        # те же метаданные в постер
    return dest


def save_png_as_jpeg(png_path: Path, meta: dict) -> Path:
    """PNG-аналог постера видео. Стоки/StockSubmitter НЕ читают метаданные из PNG,
    поэтому рядом с PNG создаём полноразмерный JPG (прозрачность → белый фон) и
    вписываем метаданные уже в него — именно этот JPG идёт на сток. Исходный PNG
    не трогаем. -> путь к созданному JPG."""
    dest = png_path.with_name(png_path.stem + ".jpg")
    if dest.exists():                        # рядом уже есть .jpg — не затираем
        dest = png_path.with_name(png_path.stem + "_stock.jpg")
    with Image.open(png_path) as im:
        im.load()
        img = _flatten_to_white(im)          # RGBA/палитра с альфой → белый фон, RGB
    img.save(dest, "JPEG", quality=95)       # без уменьшения — сток любит крупные
    write_photo_metadata(dest, meta)
    return dest

# ============================================================================
#  Editorial: подпись по стандарту + чтение EXIF (город/дата)
# ============================================================================
_MONTHS_EN = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
              "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]


def _fmt_editorial_date(raw) -> str:
    """'2023:06:05 14:30:00' -> 'JUNE 05, 2023'. Иначе None."""
    if not raw:
        return None
    m = re.match(r"(\d{4}):(\d{2}):(\d{2})", str(raw))
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12):
        return None
    return f"{_MONTHS_EN[mo - 1]} {d:02d}, {y}"


def read_editorial_fields(path: Path) -> dict:
    """Достаёт из метаданных файла город/область/страну/дату (что есть)."""
    fields = {"date": None, "city": None, "region": None, "country": None}
    if not exiftool_available():
        return fields
    try:
        cmd = [EXIFTOOL_BIN, "-j", "-charset", "filename=utf8",
               "-DateTimeOriginal", "-CreateDate", "-MediaCreateDate",
               "-City", "-Province-State", "-State",
               "-Country-PrimaryLocationName", "-Country",
               str(path)]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=creationflags)
        data = json.loads(proc.stdout.decode("utf-8", "replace"))[0]
        fields["date"] = _fmt_editorial_date(
            data.get("DateTimeOriginal") or data.get("CreateDate") or data.get("MediaCreateDate"))
        fields["city"] = data.get("City")
        fields["region"] = data.get("Province-State") or data.get("State")
        fields["country"] = data.get("Country-PrimaryLocationName") or data.get("Country")
    except Exception:
        pass
    return fields


def build_final_description(meta: dict) -> str:
    """Итоговое описание для записи в файл.
    Commercial -> description как есть. Editorial -> собираем редакционную
    подпись «ГОРОД, МЕСТО, ДАТА: описание» из отдельных полей карточки;
    пустые поля заменяются плейсхолдерами в скобках для ручного заполнения.
    Разделитель — ЗАПЯТАЯ, а не тире: стоки режут editorial из-за спецсимвола
    тире (–), и подпись не проходит модерацию."""
    factual = meta.get("description", "")
    if not meta.get("is_editorial"):
        return factual
    city = (meta.get("ed_city") or "").strip() or "[ГОРОД]"
    place = (meta.get("ed_place") or "").strip() or "[МЕСТО СОБЫТИЯ]"
    date = (meta.get("ed_date") or "").strip() or "[ДАТА]"
    location = ", ".join(p for p in (city, place) if p)
    return f"{location.upper()}, {date}: {factual}"


def attach_release(media_path: Path, release_src) -> Path:
    """Копирует файл релиза рядом с медиа: {имя_медиа}_release.{расширение}."""
    src = Path(release_src)
    dest = media_path.with_name(f"{media_path.stem}_release{src.suffix.lower()}")
    shutil.copy2(src, dest)
    return dest


# ============================================================================
#  Общий каталог программы (для настроек/профилей рядом с .py)
# ============================================================================
def _app_dir() -> Path:
    return _base_dir()


# --- Общие настройки интерфейса (размер окна, язык) в ui_settings.json --------
def _settings_path() -> Path:
    return _app_dir() / "ui_settings.json"


def load_settings() -> dict:
    try:
        p = _settings_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def save_settings(patch: dict) -> None:
    """Read-modify-write: не затираем остальные ключи (например язык при
    сохранении размера окна)."""
    try:
        d = load_settings()
        d.update(patch)
        _settings_path().write_text(json.dumps(d, ensure_ascii=False),
                                    encoding="utf-8")
    except Exception:
        pass


# ============================================================================
#  ==== CUSTOM INSTRUCTIONS ==== свои инструкции пользователя для ИИ
# ============================================================================
def load_custom_instructions() -> str:
    p = _app_dir() / CUSTOM_INSTR_FILENAME
    if p.exists():
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


def save_custom_instructions(text: str) -> None:
    (_app_dir() / CUSTOM_INSTR_FILENAME).write_text(text or "", encoding="utf-8")


def set_custom_instructions(text: str) -> None:
    """Обновляет глобальные инструкции, используемые call_vision."""
    global CUSTOM_INSTRUCTIONS
    CUSTOM_INSTRUCTIONS = text or ""


def extract_text_from_file(path) -> str:
    """Извлекает текст из .txt/.md/.pdf для окна «Инструкции ИИ»."""
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception:
            raise RuntimeError("Для чтения PDF нужен пакет pypdf")
        reader = PdfReader(str(p))
        return "\n".join((pg.extract_text() or "") for pg in reader.pages).strip()
    return p.read_text(encoding="utf-8", errors="replace")


# ============================================================================
#  ==== UPLOAD (заморожено) ==== настройки доступов + отправка FTP/SFTP.
#  Функции сохранены, но из интерфейса убраны — фокус на разметке метаданных.
# ============================================================================
#  SFTP (Adobe Stock) + опциональный CSV для Adobe
# ============================================================================
DEFAULT_UPLOAD_SETTINGS = {
    "depositphotos": {"host": "ftp.depositphotos.com", "user": "", "password": ""},
    "adobe":         {"host": "sftp.contributor.adobestock.com", "port": "22",
                      "user": "", "password": ""},
}


def load_upload_settings() -> dict:
    p = _app_dir() / UPLOAD_SETTINGS_FILE
    data = json.loads(json.dumps(DEFAULT_UPLOAD_SETTINGS))  # глубокая копия
    if p.exists():
        try:
            saved = json.loads(p.read_text(encoding="utf-8"))
            for site in data:
                if isinstance(saved.get(site), dict):
                    data[site].update({k: str(v) for k, v in saved[site].items()})
        except Exception:
            pass
    return data


def save_upload_settings(settings: dict) -> None:
    # Пароли хранятся локально в открытом виде (как и API-ключ в этом проекте).
    (_app_dir() / UPLOAD_SETTINGS_FILE).write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def upload_ftp(host, user, password, filepath, timeout=60) -> None:
    """Depositphotos — обычный FTP. Бросает исключение при ошибке."""
    import ftplib
    host = (host or "").strip()
    if not host:
        raise RuntimeError("не указан FTP-сервер Depositphotos")
    ftp = ftplib.FTP()
    try:
        ftp.connect(host, 21, timeout=timeout)
        ftp.login(user or "", password or "")
        ftp.set_pasv(True)
        with open(filepath, "rb") as f:
            ftp.storbinary(f"STOR {Path(filepath).name}", f)
    finally:
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass


def upload_sftp(host, port, user, password, filepath) -> None:
    """Adobe Stock — SFTP через paramiko. Бросает исключение с понятной причиной."""
    try:
        import paramiko
    except Exception:
        raise RuntimeError("Не установлен paramiko:  pip install paramiko")
    host = (host or "").strip()
    if not host:
        raise RuntimeError("не указан SFTP-сервер Adobe")
    try:
        port = int(str(port).strip() or "22")
    except ValueError:
        port = 22

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        try:
            client.connect(hostname=host, port=port, username=(user or ""),
                           password=(password or ""), look_for_keys=False,
                           allow_agent=False, timeout=30)
        except paramiko.AuthenticationException:
            raise RuntimeError(
                "аутентификация не пройдена. Для Adobe нужны ОТДЕЛЬНЫЕ SFTP-логин и "
                "пароль из контрибьютор-портала (Account → раздел FTP/SFTP upload), "
                "а не e-mail/пароль от Adobe ID")
        except paramiko.SSHException as e:
            raise RuntimeError(f"SFTP-соединение отклонено: {e}")
        except Exception as e:
            raise RuntimeError(f"не удалось подключиться к {host}:{port} — {e}")
        try:
            sftp = client.open_sftp()
            sftp.put(str(filepath), Path(filepath).name)
            sftp.close()
        except Exception as e:
            raise RuntimeError(f"загрузка не удалась (проверьте права/каталог на сервере): {e}")
    finally:
        client.close()


def generate_adobe_csv(records, folder: Path) -> Path:
    """Сопроводительный CSV для Adobe (запасной путь): Filename, Title, Keywords,
    Category, Releases. records — список dict с полями path/meta/release_src."""
    import csv
    dest = Path(folder) / "adobe_stock.csv"
    with open(dest, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Filename", "Title", "Keywords", "Category", "Releases"])
        for r in records:
            meta = r["meta"]
            release_name = ""
            if r.get("release_src"):
                release_name = f"{Path(r['path']).stem}_release{Path(r['release_src']).suffix.lower()}"
            w.writerow([
                Path(r["path"]).name,
                meta.get("title", ""),
                ", ".join(meta.get("keywords", [])),
                "",  # Category — заполняется вручную в кабинете Adobe
                release_name,
            ])
    return dest


# ============================================================================
#  ==== BROWSER SUBMIT ==== доведение до кнопки «Отправить на модерацию»
#  Подход: постоянный профиль браузера (логин один раз руками) + пред-проверка
#  на капчу + vision-локатор кнопок (скриншот -> модель -> координаты клика).
#  Ни у Adobe, ни у Depositphotos нет API для сабмита — только веб-кабинет.
# ============================================================================
BROWSER_PROFILE_DIRNAME = "browser_profiles"   # ./browser_profiles/<platform>


def browser_profile_dir(platform: str) -> Path:
    d = _app_dir() / BROWSER_PROFILE_DIRNAME / platform
    d.mkdir(parents=True, exist_ok=True)
    return d


# Маркеры капчи/антибот-проверки — если найдены, действия останавливаем.
_CAPTCHA_MARKERS = [
    "recaptcha", "hcaptcha", "g-recaptcha", "cf-challenge", "turnstile",
    "i'm not a robot", "i am not a robot", "verify you are human",
    "подтвердите, что вы не робот", "unusual traffic", "являетесь роботом",
]


def detect_captcha(page):
    """Эвристика: есть ли на странице капча/проверка на робота. -> (bool, причина)."""
    try:
        # iframes типичных капч
        for fr in page.frames:
            u = (fr.url or "").lower()
            if any(m in u for m in ("recaptcha", "hcaptcha", "turnstile", "challenge")):
                return True, f"captcha iframe: {u[:80]}"
        html = (page.content() or "").lower()
        for m in _CAPTCHA_MARKERS:
            if m in html:
                return True, f"маркер на странице: «{m}»"
    except Exception as e:
        return False, f"(не удалось проверить: {e})"
    return False, ""


def vision_locate(client, png_bytes: bytes, description: str):
    """Просит модель найти элемент интерфейса на скриншоте и вернуть координаты
    центра в пикселях. -> dict {found: bool, x: int, y: int} либо {found: False}."""
    with Image.open(io.BytesIO(png_bytes)) as im:
        w, h = im.size
    instruction = (
        f"На изображении — скриншот веб-страницы размером {w}x{h} пикселей "
        "(0,0 — левый верхний угол). Найди элемент интерфейса, описанный ниже, "
        "и верни ТОЛЬКО JSON без пояснений:\n"
        '{"found": true, "x": <пиксель по горизонтали центра элемента>, '
        '"y": <пиксель по вертикали центра элемента>}\n'
        'Если элемента на экране нет — верни {"found": false}. '
        f"Искомый элемент: {description}"
    )
    content = [
        {"type": "text", "text": instruction},
        {"type": "image_url", "image_url": {"url": _b64_data_url(png_bytes)}},
    ]
    base_kwargs = {
        "model": AZURE_DEPLOYMENT,
        "messages": [
            {"role": "system", "content": "Ты помогаешь автоматизировать клики по "
             "интерфейсу. Отвечай только JSON с пиксельными координатами."},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }
    optional_kwargs = {"max_completion_tokens": MAX_COMPLETION_TOKENS}
    if REASONING_EFFORT:
        optional_kwargs["reasoning_effort"] = REASONING_EFFORT
    resp = _create_completion(client, base_kwargs, optional_kwargs)
    text = (resp.choices[0].message.content or "").strip()
    data = _extract_json(text)
    if not data.get("found"):
        return {"found": False}
    try:
        x, y = int(round(float(data["x"]))), int(round(float(data["y"])))
    except (KeyError, TypeError, ValueError):
        return {"found": False}
    x = max(0, min(w - 1, x))
    y = max(0, min(h - 1, y))
    return {"found": True, "x": x, "y": y, "img_w": w, "img_h": h}


_SNAP_JS = """([x,y]) => {
    function clickable(el){
        while(el){
            const t = el.tagName;
            if(t==='BUTTON'||t==='A'||t==='INPUT'||el.onclick||
               el.getAttribute('role')==='button'){ return el; }
            el = el.parentElement;
        }
        return null;
    }
    // ищем ближайший кликабельный элемент возле точки (vision мажет на десятки px)
    for(const dy of [0,-14,14,-28,28,-44,44,-60,60]){
        for(const dx of [0,-20,20,-45,45]){
            const el = document.elementFromPoint(x+dx, y+dy);
            const c = el && clickable(el);
            if(c){ c.scrollIntoView({block:'center'}); c.click(); return true; }
        }
    }
    return false;
}"""


def find_and_click(page, client, text_candidates, vision_description, timeout=4000):
    """Гибрид по ТЗ: сперва обычные селекторы (текст/роль кнопки) — надёжно и
    дёшево; при неудаче — vision по скриншоту, но кликаем НЕ по сырым
    координатам (модель мажет), а по ближайшему реальному кликабельному элементу
    возле найденной точки. -> (ok: bool, how: str)."""
    # 1) текст/роль (пробуем список кандидатов — реальный текст сайта заранее неизвестен)
    for t in (text_candidates or []):
        pat = re.compile(re.escape(t), re.I)
        for finder, tag in ((lambda: page.get_by_role("button", name=pat), "role"),
                            (lambda: page.get_by_text(pat), "text")):
            try:
                loc = finder()
                if loc.count() > 0:
                    loc.first.click(timeout=timeout)
                    return True, f"{tag}:{t}"
            except Exception:
                pass
    # 2) vision-фоллбэк со «снапом» к ближайшему кликабельному элементу
    png = page.screenshot()
    v = vision_locate(client, png, vision_description)
    if not v.get("found"):
        return False, "не найдено"
    x, y = v["x"], v["y"]
    try:
        if page.evaluate(_SNAP_JS, [x, y]):
            return True, f"vision-snap({x},{y})"
    except Exception:
        pass
    page.mouse.click(x, y)   # крайний случай — сырые координаты
    return True, f"vision-raw({x},{y})"


def launch_persistent_browser(platform: str, headless=False):
    """Постоянный профиль: логин один раз руками, сессия хранится в
    ./browser_profiles/<platform>.

    ВАЖНО: сперва пробуем УЖЕ УСТАНОВЛЕННЫЕ системные браузеры (Edge есть на
    любой Windows, Chrome обычно тоже). Тогда ничего не нужно скачивать и
    зашивать в .exe — это и чинит запуск на машине, где Playwright-Chromium
    не установлен. Свой Chromium — последним запасным вариантом.
    -> (pw, context, page, имя_браузера)."""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    profile = str(browser_profile_dir(platform))
    last_err = None
    for channel in ("msedge", "chrome", None):
        try:
            kwargs = dict(user_data_dir=profile, headless=headless,
                          viewport={"width": 1400, "height": 900})
            if channel:
                kwargs["channel"] = channel
            ctx = pw.chromium.launch_persistent_context(**kwargs)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            return pw, ctx, page, (channel or "chromium")
        except Exception as e:
            last_err = e
    try:
        pw.stop()
    except Exception:
        pass
    raise last_err


def browser_alive(ctx) -> bool:
    try:
        return len(ctx.pages) > 0
    except Exception:
        return False


# ============================================================================
#  ⏸️  FROZEN — АВТОСАБМИТ ЗАМОРОЖЕН до данных с машины отца (живой тест)
# ----------------------------------------------------------------------------
#  Механизм готов и протестирован (системный Edge/Chrome, select-all + submit,
#  стоп на капче). Чтобы разморозить и довести до боевого — впиши сюда РЕАЛЬНЫЕ
#  данные с сайтов (ищи по слову FROZEN):
#    1) *_SUBMIT_PAGE_URL  — точный URL страниц Unfinished Files (DP) / New (Adobe)
#    2) *_SELECT_ALL_TEXTS — как реально называется «выделить все» в интерфейсе
#    3) *_SUBMIT_TEXTS     — как реально называется кнопка отправки на модерацию
#  Ниже — заглушки/догадки. Остальной код (генерация/запись/загрузка) от этого
#  НЕ зависит и работает независимо.
# ============================================================================

# Описания элементов: текстовые кандидаты (основной путь) + описание для vision
DP_START_URL = "https://depositphotos.com/"
DP_SELECT_ALL_TEXTS = ["select all", "выделить все", "выбрать все", "select all files"]
DP_SELECT_ALL_DESC = ("чекбокс или ссылка «выделить все» (Select all) над списком "
                      "загруженных/незавершённых файлов")
DP_SUBMIT_TEXTS = ["send for review", "отправить на проверку", "отправить на модерацию",
                   "submit for review", "submit"]
DP_SUBMIT_DESC = ("кнопка отправки выбранных файлов на модерацию — «Send for review» "
                  "/ «Submit» / «Отправить на проверку»")

ADOBE_START_URL = "https://contributor.stock.adobe.com/uploads"
ADOBE_SELECT_ALL_TEXTS = ["select all", "выбрать все", "выделить все"]
ADOBE_SELECT_ALL_DESC = ("чекбокс/ссылка «Select all» над списком загруженных файлов "
                         "во вкладке New (Uploaded files)")
ADOBE_SUBMIT_TEXTS = ["submit for review", "submit", "отправить на проверку", "отправить"]
ADOBE_SUBMIT_DESC = ("кнопка отправки выбранных файлов на модерацию Adobe — "
                     "«Submit» / «Submit for review»")

# Прямые ссылки на страницы сабмита (для режима «открыть в обычном браузере»).
# Открываются в браузере пользователя, где он уже залогинен — остаётся выделить
# файлы и нажать Submit. Если у тебя точный URL другой — впиши его сюда.
DP_SUBMIT_PAGE_URL = "https://depositphotos.com/upload"
ADOBE_SUBMIT_PAGE_URL = "https://contributor.stock.adobe.com/uploads"


def run_submit_flow(platform, start_url, select_all_texts, select_all_desc,
                    submit_texts, submit_desc, semi_auto,
                    client, log_cb, wait_continue, stop_flag, on_actions_done=None,
                    fallback_url=None):
    """Универсальный флоу сабмита через браузер. Ничего не обходит: при капче —
    останавливается. По умолчанию semi-auto: доводит до кнопки сабмита и ждёт,
    что финальный клик сделает пользователь.
      log_cb(msg, color)         — вывод в лог приложения
      wait_continue() -> bool    — блокирует, пока пользователь не нажмёт «Продолжить»
                                   (False, если отменил)
      stop_flag                  — threading.Event для остановки
      on_actions_done(page)      — хук для тестов (вызывается после действий)"""
    pw = ctx = None
    try:
        log_cb("Запускаю браузер…", COL_ACCENT)
        try:
            pw, ctx, page, browser_name = launch_persistent_browser(platform)
            log_cb(f"Браузер запущен ({browser_name}).", COL_MUTED)
        except Exception as e:
            log_cb(f"✗ Не удалось запустить ни один браузер (Edge/Chrome/Chromium): "
                   f"{str(e)[:200]}", COL_ERR)
            if fallback_url:
                try:
                    webbrowser.open(fallback_url)
                    log_cb("→ Открыл страницу в обычном браузере — заверши вручную.",
                           COL_SKIP)
                except Exception:
                    pass
            return
        try:
            page.goto(start_url, timeout=60000)
        except Exception as e:
            log_cb(f"⚠ Не удалось открыть стартовую страницу: {e}", COL_SKIP)

        log_cb("Залогинься при необходимости и открой страницу с файлами на сабмит "
               "(Unfinished Files). Затем нажми «Продолжить».", COL_ACCENT)
        if not wait_continue():
            log_cb("Сабмит отменён.", COL_SKIP)
            return

        # пред-проверка на капчу/антибот — НЕ обходим
        is_c, why = detect_captcha(page)
        if is_c:
            log_cb(f"■ СТОП: похоже, капча/проверка на робота ({why}). Пройди её "
                   "вручную и запусти сабмит заново. Автоматически не обхожу.", COL_ERR)
            return

        # выделить все файлы
        log_cb("Ищу «выделить все»…", COL_MUTED)
        ok, how = find_and_click(page, client, select_all_texts, select_all_desc)
        log_cb(f"✓ выделил все ({how})" if ok
               else "⚠ не нашёл «выделить все» — выдели файлы вручную в браузере",
               COL_OK if ok else COL_SKIP)

        # кнопка сабмита
        if semi_auto:
            log_cb("✓ Готово. Проверь выделение и нажми кнопку отправки на модерацию "
                   "сам в браузере (semi-auto).", COL_ACCENT)
        else:
            log_cb("Ищу и жму кнопку отправки на модерацию…", COL_MUTED)
            ok2, how2 = find_and_click(page, client, submit_texts, submit_desc)
            log_cb(f"✓ Отправил на модерацию ({how2})" if ok2
                   else "⚠ Кнопку сабмита не нашёл — нажми её сам в браузере.",
                   COL_OK if ok2 else COL_SKIP)

        if on_actions_done:
            try:
                on_actions_done(page)
            except Exception:
                pass

        log_cb("Браузер оставляю открытым — заверши/проверь и просто закрой его.",
               COL_MUTED)
        while not stop_flag.is_set() and browser_alive(ctx):
            time.sleep(1)
    except Exception:
        log_cb("Ошибка браузерного сабмита:\n" + traceback.format_exc(), COL_ERR)
    finally:
        try:
            if ctx:
                ctx.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass


# ============================================================================
#  Лог уже обработанных файлов
# ============================================================================
def file_hash(path: Path, chunk=1 << 20) -> str:
    h = hashlib.sha1()
    h.update(str(path.stat().st_size).encode())
    with open(path, "rb") as f:
        h.update(f.read(chunk))          # первый мегабайт — достаточно как отпечаток
    return h.hexdigest()


class ProcessLog:
    def __init__(self, folder: Path):
        self.path = folder / LOG_FILENAME
        self.data = {}
        self._lock = threading.Lock()
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    def is_done(self, path: Path, digest: str) -> bool:
        rec = self.data.get(path.name)
        return bool(rec) and rec.get("hash") == digest and rec.get("status") == "ok"

    def mark(self, path: Path, digest: str, status: str, meta=None, error=None):
        with self._lock:
            self.data[path.name] = {
                "hash": digest,
                "status": status,
                "title": (meta or {}).get("title"),
                "keywords_count": len((meta or {}).get("keywords", []) or []),
                "error": error,
            }
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

# ============================================================================
#  Ядро: генерация (без записи) и запись метаданных — раздельно
# ============================================================================
def exiftool_available() -> bool:
    return Path(EXIFTOOL_BIN).is_file() or bool(shutil.which(EXIFTOOL_BIN))


def generate_for_file(client, path: Path, log: ProcessLog) -> dict:
    """ФАЗА 1 — только генерация метаданных, БЕЗ записи в файл.
    Возвращает запись-словарь с полями:
      path, name, kind, status, meta, thumb, digest, message
    status: 'ok' | 'skip' | 'error' | 'fatal'
    'fatal' — ошибка, обрекающая весь батч (ключ/эндпоинт/деплоймент/сеть)."""
    ext = path.suffix.lower()
    rec = {
        "path": path, "name": path.name,
        "kind": "photo" if ext in IMAGE_EXTS else "video",
        "status": None, "meta": None, "thumb": None,
        "digest": None, "message": "",
    }
    try:
        rec["digest"] = file_hash(path)
    except Exception as e:
        rec["status"] = "error"
        rec["message"] = tr(f"не удалось прочитать файл: {e}", f"couldn't read file: {e}")
        return rec

    if log.is_done(path, rec["digest"]):
        rec["status"] = "skip"
        rec["message"] = tr("уже обработан ранее", "already processed")
        return rec

    try:
        if ext in IMAGE_EXTS:
            images, thumb = prepare_photo(path)
            meta = call_vision(client, images, build_image_instruction())
        elif ext in VIDEO_EXTS:
            frames, thumb = prepare_video(path)
            meta = call_vision(client, frames, build_video_instruction())
        else:
            rec["status"] = "skip"
            rec["message"] = tr("неподдерживаемый формат", "unsupported format")
            return rec
        # editorial: город/место/дата храним отдельными редактируемыми полями,
        # description оставляем «фактическим». Финальная подпись собирается при записи.
        if meta.get("is_editorial"):
            f = read_editorial_fields(path)
            meta["ed_city"] = f["city"] or ""
            meta["ed_place"] = ", ".join(x for x in (f["region"], f["country"]) if x)
            meta["ed_date"] = f["date"] or ""
        rec["meta"] = meta
        rec["thumb"] = thumb
        rec["status"] = "ok"
        tag = "EDITORIAL · " if meta.get("is_editorial") else ""
        rec["message"] = tr(f"{tag}{len(meta['keywords'])} ключевых слов · {meta['title']}",
                            f"{tag}{len(meta['keywords'])} keywords · {meta['title']}")
    except SubscriptionRequired as e:
        # подписка/триал кончились — обрубаем батч и покажем экран плана
        rec["status"] = "access"
        rec["message"] = str(e)
    except QuotaExceeded as e:
        # исчерпан дневной/недельный лимит — обрубаем батч, но экран плана НЕ нужен
        # (план у юзера есть), покажем просто сообщение
        rec["status"] = "limit"
        rec["message"] = str(e)
    except FATAL_EXC as e:
        rec["status"] = "fatal"
        rec["message"] = str(e)
    except Exception as e:
        rec["status"] = "error"
        rec["message"] = str(e)
    return rec


def commit_for_file(path: Path, meta: dict, log: ProcessLog):
    """ФАЗА 2 — записать метаданные в файл. -> (status, message)."""
    ext = path.suffix.lower()
    # editorial-подпись собирается здесь, из (возможно отредактированных) полей
    meta = dict(meta)
    meta["description"] = build_final_description(meta)
    try:
        if ext == ".png":
            # PNG: стоки не читают метаданные из PNG. Как с видео — делаем JPG с
            # вшитыми метаданными (он и идёт на сток). В сам PNG пишем best-effort.
            save_png_as_jpeg(path, meta)
            try:
                write_photo_metadata(path, meta)
            except Exception as e:
                cprint(f"SedStock: метаданные в PNG {path.name} не записаны "
                       f"(JPG-версия создана и подписана): {e}")
        elif ext in IMAGE_EXTS:
            write_photo_metadata(path, meta)
        elif ext in VIDEO_EXTS:
            # ПРИОРИТЕТ — JPEG-скриншот (постер) с метаданными: надёжно и так же
            # работает StockSubmitter. Метаданные в сам ролик пишем best-effort:
            # если QuickTime-запись не удалась — не поднимаем «красную тревогу»,
            # скриншот уже готов и подписан.
            save_video_poster(path, meta)
            try:
                write_video_metadata(path, meta)
            except Exception as e:
                cprint(f"SedStock: метаданные в видео {path.name} не записаны "
                       f"(JPEG-скриншот создан и подписан): {e}")
        else:
            return "skip", tr("неподдерживаемый формат", "unsupported format")
    except Exception as e:
        log.mark(path, file_hash(path) if path.exists() else "", "error", error=str(e))
        return "error", str(e)

    # Запись изменила файл — фиксируем хэш УЖЕ обработанного файла, иначе при
    # повторном запуске он не совпадёт и файл обработается заново.
    try:
        digest = file_hash(path)
    except Exception:
        digest = None
    log.mark(path, digest, "ok", meta=meta)
    return "ok", f"{len(meta['keywords'])} ключевых слов · {meta['title']}"


def process_file(client, path: Path, log: ProcessLog):
    """Генерация + немедленная запись (режим «без предпросмотра»)."""
    rec = generate_for_file(client, path, log)
    if rec["status"] != "ok":
        return rec["status"], rec["message"]
    return commit_for_file(path, rec["meta"], log)


def scan_folder(folder: Path):
    """-> (поддерживаемые файлы, неподдерживаемые файлы)."""
    supported, unsupported = [], []
    for p in sorted(folder.iterdir()):
        if not p.is_file():
            continue
        if p.name == LOG_FILENAME:
            continue
        if p.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS):
            supported.append(p)
        else:
            unsupported.append(p)
    return supported, unsupported


def cprint(s: str) -> None:
    """Печать в командную строку, устойчивая к любой кодовой странице консоли."""
    try:
        print(s, flush=True)
    except Exception:
        try:
            print(s.encode("ascii", "replace").decode("ascii"), flush=True)
        except Exception:
            pass

# ============================================================================
#  Интерфейс
# ============================================================================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("light")
        # язык интерфейса — из сохранённых настроек (по умолчанию английский)
        set_lang(load_settings().get("lang", "en"))
        self.title(f"SedStock · StockKeyworder  v{APP_VERSION}")
        self.geometry("980x740")
        self.minsize(820, 580)
        self.configure(fg_color=COL_BG)
        # запоминаем размер окна: восстанавливаем сохранённый и сохраняем при
        # изменении/закрытии, чтобы приложение всегда открывалось как хочет юзер
        self._restore_geometry()
        self._geo_after = None
        self.bind("<Configure>", self._on_configure)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.folder = None
        self._worker = None
        self._stop_flag = threading.Event()
        self._pending = []          # ok-записи, ждущие подтверждения
        self._thumb_refs = []       # ссылки на CTkImage, чтобы их не собрал GC
        self.preview_records = []   # записи ленты (у каждой r["_var"] — чекбокс)
        self._multi_edit = False   # режим «Выбрать все» (релиз ко всем)
        self._rendered_upto = 0
        self._more_btn = None
        self.auto_write_var = None
        self._settings_win = None
        self._instr_win = None
        # заморожено (загрузка/сабмит на стоки) — виджеты не создаются, ссылки-заглушки
        self.continue_btn = None
        self.submit_stop_btn = None
        self._continue_evt = threading.Event()
        self._submit_stop = threading.Event()
        set_custom_instructions(load_custom_instructions())   # свои инструкции для ИИ

        # экраны: вход/план/работа живут в одном окне, сменяя друг друга
        self._view = None          # текущий экран-фрейм (auth/plan/loading)
        self._main_built = False   # рабочий интерфейс строим один раз, после входа
        self._auth_seg = "login"   # какой сегмент открыт в окне входа

        self._enable_clipboard_shortcuts()
        self._boot()   # вход/подписка (локально в JSON или через сервер), затем нужный экран

    # -- вставка/копирование при любой раскладке ---------------------------
    def _enable_clipboard_shortcuts(self):
        """При не-латинской раскладке (напр. русской) Ctrl+V/C/X/A дают
        нелатинские keysym'ы, и штатные бинды Tkinter (ждущие v/c/x/a) молчат.
        Ловим по физическому keycode; но если keysym — латинская буква, отдаём
        событие встроенному бинду (иначе была бы двойная вставка на EN-раскладке).
        Действует во всех окнах, включая настройки/инструкции."""
        LATIN = {86: "v", 67: "c", 88: "x", 65: "a"}          # физ. клавиши
        ACTION = {86: "<<Paste>>", 67: "<<Copy>>", 88: "<<Cut>>", 65: "SELECT_ALL"}

        def handler(event):
            action = ACTION.get(event.keycode)
            if action is None:
                return None
            if event.keysym.lower() == LATIN[event.keycode]:
                return None   # латиница — пусть сработает встроенный бинд
            w = event.widget
            try:
                if action == "SELECT_ALL":
                    try:
                        w.select_range(0, "end")            # Entry
                        w.icursor("end")
                    except Exception:
                        try:
                            w.tag_add("sel", "1.0", "end")   # Text/Textbox
                        except Exception:
                            pass
                else:
                    w.event_generate(action)
            except Exception:
                pass
            return "break"

        self.bind_all("<Control-KeyPress>", handler, add="+")

    # -- «сочные» объёмные кнопки (3D, стиль Duolingo) ----------------------
    def _btn(self, parent, text, command, kind="accent", width=140, height=38,
             font_size=13):
        """Объёмная кнопка Btn3D: у цветных (accent/ok) снизу тёмное ребро, при
        нажатии кнопка садится на него (придавливается); ghost/muted плоские и
        меняют цвет. kind: accent|ok|ghost|muted."""
        return Btn3D(parent, text, command=command, kind=kind,
                     width=width, height=height, font_size=font_size)

    # ======================================================================
    #  ЭКРАНЫ: загрузка -> вход/регистрация -> выбор плана -> рабочий
    #  Все живут в одном окне: экран-фрейм кладётся поверх на весь размер окна,
    #  при переходе — уничтожается (под ним оказывается рабочий интерфейс).
    # ======================================================================
    # -- запоминание размера окна ------------------------------------------
    def _restore_geometry(self):
        try:
            g = load_settings().get("size")
            if g and "x" in g:
                self.geometry(g)
        except Exception:
            pass

    def _save_geometry(self):
        try:
            # self.geometry() у CustomTkinter возвращает ЛОГИЧЕСКИЕ единицы (уже с
            # обратным DPI-масштабом), поэтому round-trip set/get не «раздувает»
            # окно на HiDPI. Берём только размер, без позиции.
            size = self.geometry().split("+")[0]
            if "x" not in size or size.startswith("1x1"):
                return
            w, h = (int(v) for v in size.split("x"))
            if w < 400 or h < 300:     # окно ещё не отрисовано — не сохраняем мусор
                return
            save_settings({"size": size})   # read-modify-write, не трёт язык
        except Exception:
            pass

    def _set_language(self, code: str, rerender=None):
        """Меняет язык, сохраняет выбор и перерисовывает текущий экран.
        Если рабочий интерфейс уже построен — пересобираем его целиком
        (он строится один раз и не проходит через _new_view)."""
        if (code == "ru") == (LANG == "ru"):
            return   # язык не изменился
        set_lang(code)
        save_settings({"lang": LANG})
        self.title(f"SedStock · StockKeyworder  v{APP_VERSION}")
        if getattr(self, "_main_built", False):
            try:
                self._main_frame.destroy()
            except Exception:
                pass
            self._main_built = False
            self._build_ui()
            self._main_built = True
            self._refresh_account_chip()
        if callable(rerender):
            rerender()

    def _on_configure(self, event):
        if event.widget is not self:   # реагируем только на само окно, не на детей
            return
        if self._geo_after is not None:
            try:
                self.after_cancel(self._geo_after)
            except Exception:
                pass
        self._geo_after = self.after(700, self._save_geometry)

    def _on_close(self):
        self._save_geometry()
        self.destroy()

    def _clear_view(self):
        if self._view is not None:
            try:
                self._view.destroy()
            except Exception:
                pass
            self._view = None

    def _new_view(self):
        """Создаёт пустой экран-фрейм на весь размер окна и делает его текущим."""
        self._clear_view()
        fr = ctk.CTkFrame(self, fg_color=COL_BG)
        fr.place(x=0, y=0, relwidth=1, relheight=1)
        self._view = fr
        return fr

    def _apple_entry(self, parent, placeholder, show=None):
        e = ctk.CTkEntry(parent, placeholder_text=placeholder, height=46,
                         corner_radius=12, fg_color="#ffffff",
                         border_color=COL_BORDER, border_width=1,
                         text_color=COL_TEXT, font=(FONT_UI, 15))
        if show:
            e.configure(show=show)
        return e

    # -- загрузка / автологин ----------------------------------------------
    def _lang_toggle(self, parent, rerender):
        """Маленький переключатель языка EN/RU. rerender() перерисует экран."""
        seg = ctk.CTkSegmentedButton(
            parent, values=["English", "Русский"],
            height=32, corner_radius=8, font=(FONT_UI, 12),
            fg_color="#e8e8ed", unselected_color="#e8e8ed",
            unselected_hover_color="#e0e0e6", selected_color="#ffffff",
            selected_hover_color="#ffffff", text_color=COL_TEXT)
        seg.set("Русский" if LANG == "ru" else "English")
        seg.configure(command=lambda v: self._set_language(
            "ru" if v == "Русский" else "en", rerender))
        return seg

    def _show_loading(self):
        fr = self._new_view()
        box = ctk.CTkFrame(fr, fg_color="transparent")
        box.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(box, text="SedStock", font=(FONT_UI, 40, "bold"),
                     text_color=COL_TEXT).pack()
        ctk.CTkLabel(box, text=tr("Загрузка…", "Loading…"), font=(FONT_UI, 15),
                     text_color=COL_MUTED).pack(pady=(8, 0))

    def _boot(self):
        """Старт: если есть сохранённый токен — тихо проверяем на сервере и решаем,
        какой экран показать. Сеть дёргаем в потоке, чтобы окно не подвисало."""
        self._show_loading()

        def work():
            tok = load_token()
            st = None
            if tok:
                _use_token(tok)
                st = api_status()
            self.after(0, lambda: self._route_after_boot(st))

        threading.Thread(target=work, daemon=True).start()

    def _route_after_boot(self, st):
        if st and st.get("active"):
            self._enter_main()
        elif st:                    # вошёл, но план не активен -> экран плана
            self._show_plan(st)
        else:                       # нет токена/сессии -> вход
            self._show_auth("login")

    # -- окно входа / регистрации (в стиле Apple) --------------------------
    def _show_auth(self, seg="login", prefill_email="", prefill_pw="", hint=""):
        self._auth_seg = seg
        fr = self._new_view()

        card = ctk.CTkFrame(fr, fg_color="#ffffff", corner_radius=22,
                            border_width=1, border_color=COL_BORDER)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.configure(width=440)

        pad = ctk.CTkFrame(card, fg_color="transparent")
        pad.pack(padx=40, pady=36, fill="both")

        ctk.CTkLabel(pad, text="SedStock", font=(FONT_UI, 34, "bold"),
                     text_color=COL_TEXT).pack()
        ctk.CTkLabel(pad, text=tr("ИИ-разметка для стоков",
                                  "AI keywording for microstock"),
                     font=(FONT_UI, 14), text_color=COL_MUTED).pack(pady=(2, 22))

        # iOS-сегмент-контрол
        self._SEG_LOGIN = tr("Вход", "Sign in")
        self._SEG_REG = tr("Регистрация", "Sign up")
        seg_ctrl = ctk.CTkSegmentedButton(
            pad, values=[self._SEG_LOGIN, self._SEG_REG],
            command=self._on_auth_seg,
            height=40, corner_radius=10, font=(FONT_UI, 14, "bold"),
            fg_color="#e8e8ed", unselected_color="#e8e8ed",
            unselected_hover_color="#e0e0e6", selected_color="#ffffff",
            selected_hover_color="#ffffff", text_color=COL_TEXT)
        seg_ctrl.set(self._SEG_LOGIN if seg == "login" else self._SEG_REG)
        seg_ctrl.pack(fill="x", pady=(0, 20))
        self._auth_segctrl = seg_ctrl

        self._e_email = self._apple_entry(pad, "Email")
        self._e_email.pack(fill="x", pady=(0, 12))
        self._e_pw = self._apple_entry(pad, tr("Пароль", "Password"), show="•")
        self._e_pw.pack(fill="x", pady=(0, 12))

        # поле кода — только в регистрации
        self._e_code = self._apple_entry(
            pad, tr("Код приглашения (если есть)", "Invite code (if any)"))
        if seg == "register":
            self._e_code.pack(fill="x", pady=(0, 12))

        # перенос введённого при переключении вкладок / после подсказки
        if prefill_email:
            self._e_email.insert(0, prefill_email)
        if prefill_pw:
            self._e_pw.insert(0, prefill_pw)

        # подсказка (например «этот email уже есть — войдите») — синим, не ошибка
        self._auth_err_lbl = ctk.CTkLabel(pad, text=hint, font=(FONT_UI, 12),
                                          text_color=(COL_ACCENT if hint else COL_ERR),
                                          wraplength=360, justify="left")
        self._auth_err_lbl.pack(fill="x", pady=(2, 4))

        title = tr("Войти", "Sign in") if seg == "login" else tr("Создать аккаунт", "Create account")
        self._auth_btn = self._btn(pad, title,
                                   self._do_login if seg == "login" else self._do_register,
                                   "accent", width=360, height=48, font_size=16)
        self._auth_btn.pack(fill="x", pady=(6, 0))

        if seg == "register":
            ctk.CTkLabel(pad, text=tr("🎁 После регистрации — 3 дня бесплатно",
                                      "🎁 3 days free after sign-up"),
                         font=(FONT_UI, 12), text_color=COL_MUTED).pack(pady=(12, 0))

        # переключатель языка внизу карточки
        self._lang_toggle(pad, rerender=lambda: self._reshow_auth()).pack(pady=(16, 0))

    def _reshow_auth(self):
        """Перерисовать экран входа, сохранив введённое (после смены языка)."""
        try:
            em = self._e_email.get().strip(); pw = self._e_pw.get()
        except Exception:
            em = pw = ""
        self._show_auth(self._auth_seg, prefill_email=em, prefill_pw=pw)

    def _on_auth_seg(self, value):
        seg = "login" if value == self._SEG_LOGIN else "register"
        if seg != self._auth_seg:
            # сохраняем введённое, чтобы человек не набирал заново
            try:
                em = self._e_email.get().strip()
                pw = self._e_pw.get()
            except Exception:
                em = pw = ""
            self._show_auth(seg, prefill_email=em, prefill_pw=pw)

    def _auth_error(self, text):
        try:
            self._auth_err_lbl.configure(text=text, text_color=COL_ERR)
        except Exception:
            pass

    def _auth_busy(self, busy):
        try:
            self._auth_btn.configure(state="disabled" if busy else "normal",
                                     text=(tr("Подождите…", "Please wait…") if busy else
                                           (tr("Войти", "Sign in") if self._auth_seg == "login"
                                            else tr("Создать аккаунт", "Create account"))))
        except Exception:
            pass

    def _do_login(self):
        email = self._e_email.get().strip()
        pw = self._e_pw.get()
        if not email or not pw:
            self._auth_error(tr("Введите email и пароль.",
                                "Enter your email and password.")); return
        self._auth_error(""); self._auth_busy(True)

        def work():
            try:
                data = api_login(email, pw)
                self.after(0, lambda: self._after_auth(data))
            except Exception as e:
                msg = str(e)
                # если аккаунта нет — предложим регистрацию с уже введёнными данными
                if not local_email_exists(email):
                    self.after(0, lambda: self._show_auth(
                        "register", prefill_email=email, prefill_pw=pw,
                        hint=tr("Аккаунта с таким email нет — создайте его ниже.",
                                "No account with this email — create one below.")))
                else:
                    self.after(0, lambda: (self._auth_busy(False), self._auth_error(msg)))

        threading.Thread(target=work, daemon=True).start()

    def _do_register(self):
        email = self._e_email.get().strip()
        pw = self._e_pw.get()
        code = self._e_code.get().strip()
        if not email or not pw:
            self._auth_error(tr("Введите email и пароль.",
                                "Enter your email and password.")); return
        if len(pw) < 6:
            self._auth_error(tr("Пароль минимум 6 символов.",
                                "Password must be at least 6 characters.")); return
        self._auth_error(""); self._auth_busy(True)

        def work():
            try:
                data = api_register(email, pw, code)
                self.after(0, lambda: self._after_auth(data))
            except Exception as e:
                msg = str(e)
                # email уже занят — это на самом деле вход: переносим на вкладку «Вход»
                # (проверяем по базе, а не по тексту — работает на любом языке)
                if local_email_exists(email):
                    self.after(0, lambda: self._show_auth(
                        "login", prefill_email=email, prefill_pw=pw,
                        hint=tr("Этот email уже зарегистрирован — просто войдите.",
                                "This email is already registered — just sign in.")))
                else:
                    self.after(0, lambda: (self._auth_busy(False), self._auth_error(msg)))

        threading.Thread(target=work, daemon=True).start()

    def _after_auth(self, data):
        st = (data or {}).get("status") or {}
        if st.get("active"):
            self._enter_main()      # безлимит/оплачено/уже активный триал
        else:
            self._show_plan(st)     # обычная регистрация -> выбор плана

    # -- экран выбора плана (paywall, как в мобильных приложениях) ----------
    def _show_plan(self, status=None):
        status = status or {}
        state = status.get("state", "none")
        trial_available = state in ("none",)   # триал ещё можно начать

        fr = self._new_view()
        card = ctk.CTkFrame(fr, fg_color="#ffffff", corner_radius=22,
                            border_width=1, border_color=COL_BORDER)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.configure(width=480)
        pad = ctk.CTkFrame(card, fg_color="transparent")
        pad.pack(padx=40, pady=36, fill="both")

        ctk.CTkLabel(pad, text=tr("Выберите план", "Choose your plan"),
                     font=(FONT_UI, 28, "bold"), text_color=COL_TEXT).pack()
        ctk.CTkLabel(pad, text=tr("Разметка фото и видео для микростоков",
                                  "Metadata for stock photos & videos"),
                     font=(FONT_UI, 14), text_color=COL_MUTED).pack(pady=(2, 22))

        # --- карточка подписки PRO ---
        sub = ctk.CTkFrame(pad, fg_color="#f5f8ff", corner_radius=16,
                           border_width=2, border_color=COL_ACCENT)
        sub.pack(fill="x", pady=(0, 14))
        subin = ctk.CTkFrame(sub, fg_color="transparent")
        subin.pack(padx=20, pady=18, fill="x")
        ctk.CTkLabel(subin, text="SedStock PRO", font=(FONT_UI, 18, "bold"),
                     text_color=COL_TEXT).pack(anchor="w")
        for line in (tr("• 100 фото в день, 500 в неделю",
                        "• 100 photos/day, 500/week"),
                     tr("• Фото и видео", "• Photos and videos"),
                     tr("• Приоритетная обработка", "• Priority processing")):
            ctk.CTkLabel(subin, text=line,
                         font=(FONT_UI, 13), text_color=COL_MUTED).pack(anchor="w")
        # две кнопки: месяц и год (год выгоднее)
        self._btn(subin, tr(f"Подписка — {PRICE_MONTHLY}", "Subscribe — $4 / month"),
                  lambda: self._do_subscribe("monthly"), "accent",
                  width=380, height=46, font_size=15).pack(fill="x", pady=(14, 0))
        self._btn(subin, tr(f"Год — {PRICE_YEARLY}  (выгоднее)",
                            "Yearly — $30 / year  (best value)"),
                  lambda: self._do_subscribe("yearly"), "ok",
                  width=380, height=44, font_size=14).pack(fill="x", pady=(8, 0))

        # --- пробный период ---
        if trial_available:
            self._btn(pad, tr("Начать 3 дня бесплатно", "Start 3-day free trial"),
                      self._do_start_trial, "ghost",
                      width=400, height=46, font_size=15).pack(fill="x")
        else:
            ctk.CTkLabel(pad, text=tr("Пробный период уже был использован.",
                                      "The free trial has already been used."),
                         font=(FONT_UI, 13), text_color=COL_MUTED).pack(pady=(2, 0))

        self._plan_err_lbl = ctk.CTkLabel(pad, text="", font=(FONT_UI, 12),
                                          text_color=COL_ERR, wraplength=400,
                                          justify="left")
        self._plan_err_lbl.pack(pady=(10, 0))

        # после оплаты в браузере — вернуться и проверить
        self._btn(pad, tr("Я оплатил — проверить", "I've paid — check now"),
                  self._recheck_subscription, "muted",
                  width=400, height=40, font_size=13).pack(fill="x", pady=(8, 0))

        # выход
        out = ctk.CTkLabel(pad, text=tr("Выйти из аккаунта", "Sign out"),
                           font=(FONT_UI, 12), text_color=COL_MUTED, cursor="hand2")
        out.pack(pady=(14, 0))
        out.bind("<Button-1>", lambda _e: self._logout())

        # переключатель языка
        self._lang_toggle(pad, rerender=lambda: self._show_plan(status)).pack(pady=(14, 0))

    def _plan_error(self, text):
        try:
            self._plan_err_lbl.configure(text=text)
        except Exception:
            pass

    def _do_start_trial(self):
        self._plan_error("")

        def work():
            try:
                api_start_trial()
                self.after(0, self._enter_main)
            except Exception as e:
                self.after(0, lambda: self._plan_error(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _show_awaiting_payment(self, period="monthly"):
        """Экран после нажатия оплаты: крутящееся кольцо + «Ожидайте подтверждения
        оплаты». В фоне каждые 6 сек опрашиваем сервер — как только продавец
        активирует доступ (/admin/grant), приложение само откроет рабочий экран."""
        import tkinter as tk
        self._awaiting_payment = True
        fr = self._new_view()
        card = ctk.CTkFrame(fr, fg_color="#ffffff", corner_radius=22,
                            border_width=1, border_color=COL_BORDER)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.configure(width=470)
        pad = ctk.CTkFrame(card, fg_color="transparent")
        pad.pack(padx=44, pady=40, fill="both")

        # крутящееся кольцо (бесконечное) на tkinter Canvas
        cv = tk.Canvas(pad, width=76, height=76, highlightthickness=0, bg="#ffffff", bd=0)
        cv.pack(pady=(4, 20))
        cv.create_oval(12, 12, 64, 64, outline=COL_BORDER, width=6)          # фон-кольцо
        arc = cv.create_arc(12, 12, 64, 64, start=90, extent=95, style="arc",
                            width=6, outline=COL_ACCENT)                      # бегущая дуга
        self._spin_angle = 90

        def spin():
            if not getattr(self, "_awaiting_payment", False):
                return
            try:
                self._spin_angle = (self._spin_angle - 14) % 360
                cv.itemconfig(arc, start=self._spin_angle)
            except Exception:
                return
            self.after(35, spin)
        spin()

        ctk.CTkLabel(pad, text=tr("Ожидайте подтверждения оплаты",
                                  "Awaiting payment confirmation"),
                     font=(FONT_UI, 19, "bold"), text_color=COL_TEXT).pack()
        ctk.CTkLabel(pad, text=tr(
            "Ваша заявка ждёт подтверждения. Это может занять немного времени.\n"
            "Окно можно не закрывать — доступ включится автоматически.",
            "Your request is awaiting confirmation. This may take a little while.\n"
            "You can keep this window open — access turns on automatically."),
            font=(FONT_UI, 12), text_color=COL_MUTED, wraplength=390,
            justify="center").pack(pady=(12, 20))

        self._btn(pad, tr("Отмена", "Cancel"), self._cancel_awaiting, "muted",
                  width=200, height=40, font_size=13).pack()

        def poll():
            while getattr(self, "_awaiting_payment", False):
                try:
                    st = api_status()
                except Exception:
                    st = None
                if st and st.get("active"):
                    self._awaiting_payment = False
                    self.after(0, self._enter_main)
                    return
                time.sleep(6)
        threading.Thread(target=poll, daemon=True).start()

    def _cancel_awaiting(self):
        self._awaiting_payment = False
        self._show_plan(AUTH_STATUS or {})

    def _do_subscribe(self, period="monthly"):
        """PAY_MODE='paypal' — открывает PayPal.me с суммой и показывает экран
        «ожидайте подтверждения» (крутящееся кольцо + авто-опрос сервера).
        PAY_MODE='lemonsqueezy' — авто-оплата через LemonSqueezy-checkout."""
        email = (AUTH_STATUS or {}).get("email", "")
        if PAY_MODE == "paypal":
            url = PAYPAL_ME.rstrip("/") + "/" + PAYPAL_AMOUNT.get(period, "4USD")
            try:
                webbrowser.open(url)
            except Exception as e:
                self._plan_error(tr(f"Не удалось открыть браузер: {e}",
                                    f"Couldn't open the browser: {e}"))
                return
            self._show_awaiting_payment(period)
            return
        # --- LemonSqueezy (авто) ---
        import urllib.parse
        base = CHECKOUT_URL_YEARLY if period == "yearly" else CHECKOUT_URL_MONTHLY
        params = {}
        if email:
            params["checkout[email]"] = email
            params["checkout[custom][user_email]"] = email
        url = base + (("?" + urllib.parse.urlencode(params)) if params else "")
        try:
            webbrowser.open(url)
            self._plan_error(tr("Открыл страницу оплаты в браузере. После оплаты "
                                "нажмите «Я оплатил — проверить».",
                                "Opened the payment page in your browser. After paying, "
                                "click “I've paid — check now”."))
        except Exception as e:
            self._plan_error(tr(f"Не удалось открыть браузер: {e}",
                                f"Couldn't open the browser: {e}"))

    def _recheck_subscription(self):
        """Перепроверяет статус на сервере (после оплаты в браузере)."""
        self._plan_error(tr("Проверяю оплату…", "Checking payment…"))

        def work():
            st = api_status()
            if st and st.get("active"):
                self.after(0, self._enter_main)
            else:
                self.after(0, lambda: self._plan_error(tr(
                    "Оплата пока не подтверждена. Подождите минуту после оплаты и "
                    "нажмите ещё раз.",
                    "Payment not confirmed yet. Wait a minute after paying and "
                    "try again.")))

        threading.Thread(target=work, daemon=True).start()

    def _logout(self):
        clear_token()
        self._show_auth("login")

    # -- вход в рабочий интерфейс ------------------------------------------
    def _enter_main(self):
        self._awaiting_payment = False   # остановить возможный опрос оплаты
        self._clear_view()
        if not self._main_built:
            self._build_ui()
            self._main_built = True
        self._refresh_account_chip()

    def _refresh_account_chip(self):
        lbl = getattr(self, "_account_label", None)
        if lbl is None:
            return
        st = AUTH_STATUS or {}
        state = st.get("state")
        if state == "unlimited":
            txt = tr("Безлимит", "Unlimited")
        elif state == "paid":
            d = st.get("days_left", 0)
            txt = tr(f"Подписка · {d} дн.", f"Subscription · {d}d")
        elif state == "trial":
            txt = tr(f"Пробный · {st.get('days_left', 0)} дн. · {st.get('used',0)}/{st.get('quota',0)}",
                     f"Trial · {st.get('days_left', 0)}d · {st.get('used',0)}/{st.get('quota',0)}")
        else:
            txt = tr("Нет плана", "No plan")
        try:
            lbl.configure(text=txt)
        except Exception:
            pass

    def _open_account_menu(self):
        """Небольшой экран аккаунта поверх рабочего: статус, подписка, выход."""
        st = AUTH_STATUS or {}
        state = st.get("state")
        fr = self._new_view()
        card = ctk.CTkFrame(fr, fg_color="#ffffff", corner_radius=22,
                            border_width=1, border_color=COL_BORDER)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.configure(width=420)
        pad = ctk.CTkFrame(card, fg_color="transparent")
        pad.pack(padx=40, pady=32, fill="both")

        ctk.CTkLabel(pad, text=tr("Аккаунт", "Account"), font=(FONT_UI, 26, "bold"),
                     text_color=COL_TEXT).pack()
        if st.get("email"):
            ctk.CTkLabel(pad, text=st["email"], font=(FONT_UI, 14),
                         text_color=COL_MUTED).pack(pady=(2, 6))

        plan_txt = {"unlimited": tr("Безлимитный доступ", "Unlimited access"),
                    "paid": tr(f"Подписка активна · {st.get('days_left',0)} дн.",
                               f"Subscription active · {st.get('days_left',0)}d"),
                    "trial": tr(f"Пробный период · {st.get('days_left',0)} дн.",
                                f"Free trial · {st.get('days_left',0)}d")}.get(
                        state, tr("План не выбран", "No plan selected"))
        ctk.CTkLabel(pad, text=plan_txt, font=(FONT_UI, 15, "bold"),
                     text_color=COL_ACCENT).pack(pady=(4, 18))

        self._btn(pad, tr("← Назад к работе", "← Back to work"),
                  lambda: self._enter_main(), "accent",
                  width=340, height=46, font_size=15).pack(fill="x", pady=(0, 10))
        if state not in ("unlimited", "paid"):
            self._btn(pad, tr("Оформить подписку", "Get subscription"),
                      lambda: self._show_plan(st),
                      "ghost", width=340, height=44, font_size=14).pack(fill="x", pady=(0, 10))
        self._btn(pad, tr("Выйти из аккаунта", "Sign out"), self._logout, "muted",
                  width=340, height=44, font_size=14).pack(fill="x")

        # язык
        ctk.CTkLabel(pad, text=tr("Язык", "Language"), font=(FONT_UI, 12),
                     text_color=COL_MUTED).pack(pady=(16, 4))
        self._lang_toggle(pad, rerender=self._open_account_menu).pack()

    # -- построение UI ------------------------------------------------------
    def _build_ui(self):
        # весь рабочий интерфейс — в одном контейнере, чтобы можно было
        # целиком пересобрать при смене языка
        root = self._main_frame = ctk.CTkFrame(self, fg_color=COL_BG)
        root.pack(fill="both", expand=True)

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.pack(fill="x", padx=32, pady=(16, 6))
        ctk.CTkLabel(
            header, text="SedStock", font=(FONT_UI, 34, "bold"),
            text_color=COL_TEXT,
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="StockKeyworder", font=(FONT_UI, 16),
            text_color=COL_MUTED,
        ).pack(side="left", padx=(12, 0), pady=(14, 0))
        # кнопка «Инструкции ИИ» справа
        self._btn(header, tr("Инструкции ИИ", "AI instructions"), self.open_instructions,
                  "ghost", width=160, height=36).pack(side="right", pady=(8, 0))
        # чип статуса аккаунта (план/дни/лимит) + меню аккаунта
        self._account_label = ctk.CTkLabel(
            header, text="", font=(FONT_UI, 13, "bold"), text_color=COL_MUTED,
            fg_color="#e8f0ff", corner_radius=10, padx=12, pady=6, cursor="hand2")
        self._account_label.pack(side="right", padx=(0, 12), pady=(10, 0))
        self._account_label.bind("<Button-1>", lambda _e: self._open_account_menu())

        # панель выбора папки
        pick = ctk.CTkFrame(root, fg_color=COL_PANEL, corner_radius=14,
                            border_width=1, border_color=COL_BORDER)
        pick.pack(fill="x", padx=32, pady=6)
        self._pick_panel = pick
        self.path_label = ctk.CTkLabel(
            pick, text=tr("Папка не выбрана", "No folder selected"), anchor="w",
            font=(FONT_UI, 15), text_color=COL_MUTED,
        )
        self.path_label.pack(side="left", fill="x", expand=True, padx=20, pady=16)
        self._btn(pick, tr("Выбрать папку", "Choose folder"), self.choose_folder,
                  "accent", width=160, height=38).pack(side="right", padx=14, pady=12)

        # опции — apple-style тумблер
        opts = ctk.CTkFrame(root, fg_color="transparent")
        opts.pack(fill="x", padx=32, pady=(6, 2))
        self._opts_panel = opts
        self.auto_write_var = BooleanVar(value=False)
        ctk.CTkSwitch(
            opts, text=tr("Записывать сразу, без предпросмотра",
                          "Write immediately, without preview"),
            variable=self.auto_write_var, font=(FONT_UI, 15),
            text_color=COL_TEXT, progress_color=COL_ACCENT,
            button_color="#ffffff", button_hover_color="#f2f2f5",
            fg_color=COL_TRACK, width=44,
        ).pack(side="left")

        # (Загрузка/сабмит на стоки заморожены и убраны из интерфейса — фокус на
        #  качественной разметке метаданных. Код функций сохранён ниже, но не вызывается.)

        # управление + прогресс
        ctrl = ctk.CTkFrame(root, fg_color="transparent")
        ctrl.pack(fill="x", padx=32, pady=(8, 6))
        self._ctrl_frame = ctrl
        self.start_btn = self._btn(ctrl, tr("Начать обработку", "Start processing"),
                                   self.start, "accent", width=220, height=44, font_size=15)
        self.start_btn.configure(state="disabled")
        self.start_btn.pack(side="left")
        self.stop_btn = self._btn(ctrl, tr("Стоп", "Stop"), self.stop, "muted",
                                  width=100, height=44)
        self.stop_btn.configure(state="disabled")
        self.stop_btn.pack(side="left", padx=12)
        self.counter_label = ctk.CTkLabel(
            ctrl, text="", font=(FONT_UI, 13, "bold"), text_color=COL_MUTED,
        )
        self.counter_label.pack(side="right")

        self.progress = ctk.CTkProgressBar(
            root, height=8, corner_radius=4,
            progress_color=COL_ACCENT, fg_color=COL_TRACK,
        )
        self.progress.pack(fill="x", padx=32, pady=(4, 8))
        self.progress.set(0)

        # --- область содержимого: лог ИЛИ лента предпросмотра ---
        self.content = ctk.CTkFrame(root, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=32, pady=(0, 14))

        self.logbox = ctk.CTkTextbox(
            self.content, fg_color=COL_PANEL, text_color=COL_TEXT,
            font=(FONT_UI, 12), corner_radius=12, wrap="word",
            border_width=1, border_color=COL_BORDER,
        )
        self.logbox.pack(fill="both", expand=True)
        self.logbox.configure(state="disabled")

        self._build_preview_container()   # создаём, но не показываем

        self._log(tr("SedStock готов. Выберите папку с фото/видео.",
                     "SedStock is ready. Choose a folder with photos/videos."), COL_MUTED)
        if AZURE_API_KEY.startswith("ВСТАВЬТЕ"):
            self._log(tr("⚠ Не заполнен AZURE_API_KEY в начале файла SedStock.py",
                         "⚠ AZURE_API_KEY is not set at the top of SedStock.py"), COL_SKIP)
        if exiftool_available():
            path = EXIFTOOL_BIN if Path(EXIFTOOL_BIN).is_file() else shutil.which(EXIFTOOL_BIN)
            self._log(tr(f"exiftool найден: {path}", f"exiftool found: {path}"), COL_OK)
        else:
            self._log(tr("■■■  ВНИМАНИЕ: exiftool НЕ найден — метаданные записать НЕ получится!  ■■■",
                         "■■■  WARNING: exiftool NOT found — metadata cannot be written!  ■■■"),
                      COL_ERR)
            self._log(tr(f"   Программа искала папку tools\\exiftool.exe в: {_base_dir()}",
                         f"   Looked for tools\\exiftool.exe in: {_base_dir()}"), COL_ERR)
            self._log(tr("   Нужно положить папку tools (с exiftool.exe и exiftool_files) "
                         "рядом с программой и перезапустить.",
                         "   Put the tools folder (with exiftool.exe and exiftool_files) "
                         "next to the app and restart."), COL_ERR)

    def _build_preview_container(self):
        """Контейнер ленты предпросмотра: верхняя панель + прокручиваемый список."""
        self.preview_container = ctk.CTkFrame(self.content, fg_color="transparent")

        bar = ctk.CTkFrame(self.preview_container, fg_color=COL_PANEL, corner_radius=12,
                           border_width=1, border_color=COL_BORDER)
        bar.pack(fill="x", pady=(0, 10))
        self.preview_title = ctk.CTkLabel(
            bar, text=tr("Предпросмотр", "Preview"), anchor="w",
            font=(FONT_UI, 15, "bold"), text_color=COL_TEXT,
        )
        self.preview_title.pack(side="left", padx=18, pady=12)
        self.confirm_btn = self._btn(bar, tr("Применить ко всем", "Apply to all"),
                                     self.confirm_write, "ok", width=190, height=38)
        self.confirm_btn.pack(side="right", padx=(8, 16), pady=10)
        self.cancel_btn = self._btn(bar, tr("Отмена", "Cancel"), self.cancel_preview,
                                    "muted", width=92, height=38)
        self.cancel_btn.pack(side="right", padx=6, pady=10)
        # режим-переключатель: горит синим, когда включён. Пока включён — эдиториал
        # (город/место/дата, вкл/выкл) и релиз ДУБЛИРУЮТСЯ на все ОТМЕЧЕННЫЕ галочкой
        # фото — какие отметишь, на те и применяется (см. _on_editorial_edit и др.).
        self._selall_btn = ctk.CTkButton(
            bar, text=tr("Дублировать на выбранные", "Duplicate to selected"),
            width=210, height=38, corner_radius=11,
            font=(FONT_UI, 13, "bold"), fg_color="transparent",
            hover_color=COL_HOVER, text_color=COL_ACCENT,
            border_width=1, border_color=COL_BORDER,
            command=self._toggle_multi_edit)
        self._selall_btn.pack(side="right", padx=6, pady=10)
        # простые помощники для галочек (не режим — просто отметить/снять все)
        self._btn(bar, tr("Снять все", "Uncheck all"), lambda: self._check_all(False),
                  "ghost", width=96, height=38).pack(side="right", padx=6, pady=10)
        self._btn(bar, tr("Отметить все", "Check all"), lambda: self._check_all(True),
                  "ghost", width=104, height=38).pack(side="right", padx=6, pady=10)

        self.cards = ctk.CTkScrollableFrame(
            self.preview_container, fg_color=COL_BG, corner_radius=12,
        )
        self.cards.pack(fill="both", expand=True)

    def _show_log(self):
        self.preview_container.pack_forget()
        self.logbox.pack(fill="both", expand=True)

    def _show_preview(self):
        self.logbox.pack_forget()
        self.preview_container.pack(fill="both", expand=True)

    # -- вспомогательные ----------------------------------------------------
    def _log(self, text, color=None):
        def do():
            self.logbox.configure(state="normal")
            tag = None
            if color:
                tag = f"c{color}"
                self.logbox.tag_config(tag, foreground=color)
            self.logbox.insert("end", text + "\n", tag)
            self.logbox.see("end")
            self.logbox.configure(state="disabled")
        self.after(0, do)

    def _set_progress(self, value, counter_text):
        def do():
            self.progress.set(value)
            self.counter_label.configure(text=counter_text)
        self.after(0, do)

    def _relayout(self, phase):
        """Больше места ленте/логу во время работы: панель выбора папки и опции
        нужны только в простое — прячем их при обработке; в предпросмотре прячем
        ещё и управление с прогрессом (остаётся шапка + лента на весь экран)."""
        for w in (self._pick_panel, self._opts_panel, self._ctrl_frame, self.progress):
            w.pack_forget()
        ref = self.content
        if phase == "idle":
            self._pick_panel.pack(fill="x", padx=32, pady=6, before=ref)
            self._opts_panel.pack(fill="x", padx=32, pady=(6, 2), before=ref)
            self._ctrl_frame.pack(fill="x", padx=32, pady=(8, 6), before=ref)
            self.progress.pack(fill="x", padx=32, pady=(4, 8), before=ref)
        elif phase in ("generating", "committing"):
            self._ctrl_frame.pack(fill="x", padx=32, pady=(8, 6), before=ref)
            self.progress.pack(fill="x", padx=32, pady=(4, 8), before=ref)
        # preview -> только шапка + лента (максимум места файлам)

    def _set_phase(self, phase):
        """idle | generating | preview | committing — управляет кнопками + layout."""
        self._phase = phase

        def do():
            if getattr(self, "_pick_panel", None) is not None:
                self._relayout(phase)
            if phase in ("generating", "committing"):
                self.start_btn.configure(state="disabled")
                self.stop_btn.configure(state="normal")
            elif phase == "preview":
                self.start_btn.configure(state="disabled")
                self.stop_btn.configure(state="disabled")
            else:  # idle
                self.start_btn.configure(state="normal" if self.folder else "disabled")
                self.stop_btn.configure(state="disabled")
        self.after(0, do)

    def _critical_stop(self, msg):
        """Критическая ошибка, способная навредить/обессмыслить батч — СТОП + чат."""
        self._show_log()
        self._log("", None)
        self._log(tr("■■■  СТОП: критическая ошибка  ■■■",
                     "■■■  STOP: critical error  ■■■"), COL_ERR)
        for line in str(msg).split("\n"):
            self._log("   " + line, COL_ERR)
        self._log(tr("   Файлы не изменены.", "   No files were changed."), COL_SKIP)
        cprint("SedStock CRITICAL: " + str(msg).replace("\n", " | "))

    # -- действия -----------------------------------------------------------
    def choose_folder(self):
        folder = filedialog.askdirectory(title=tr("Выберите папку с файлами",
                                                  "Choose a folder with files"))
        if not folder:
            return
        self.folder = Path(folder)
        self.path_label.configure(text=str(self.folder), text_color=COL_TEXT)
        supported, unsupported = scan_folder(self.folder)
        n_img = sum(1 for f in supported if f.suffix.lower() in IMAGE_EXTS)
        n_vid = sum(1 for f in supported if f.suffix.lower() in VIDEO_EXTS)
        self._show_log()
        self._log(tr(f"Папка выбрана: {len(supported)} файлов к обработке "
                     f"({n_img} фото, {n_vid} видео).",
                     f"Folder selected: {len(supported)} files to process "
                     f"({n_img} photos, {n_vid} videos)."), COL_ACCENT)
        if unsupported:
            self._log(tr(f"Будет пропущено {len(unsupported)} файлов "
                         f"неподдерживаемого типа.",
                         f"{len(unsupported)} files of unsupported type "
                         f"will be skipped."), COL_SKIP)
        self.start_btn.configure(state="normal" if supported else "disabled")

    def start(self):
        if self._worker and self._worker.is_alive():
            return
        if not self.folder:
            return
        if AZURE_API_KEY.startswith("ВСТАВЬТЕ"):
            self._log(tr("✗ Сначала заполните AZURE_API_KEY в начале файла.",
                         "✗ Set AZURE_API_KEY at the top of the file first."), COL_ERR)
            return
        self._stop_flag.clear()
        self._pending = []
        self._show_log()
        self._set_phase("generating")
        self._worker = threading.Thread(target=self._run_generate, daemon=True)
        self._worker.start()

    def stop(self):
        self._stop_flag.set()
        self._log(tr("⏸ Остановка после текущих файлов…",
                     "⏸ Stopping after current files…"), COL_SKIP)

    # -- ФАЗА 1: генерация (уходишь — работает само) ------------------------
    def _run_generate(self):
        try:
            supported, unsupported = scan_folder(self.folder)
            for u in unsupported:
                m = tr(f"↷ {u.name} — тип не поддерживается, пропущен",
                       f"↷ {u.name} — unsupported type, skipped")
                self._log(m, COL_SKIP)
                cprint("SedStock: " + u.name + " — unsupported type, skipped")

            total = len(supported)
            if not total:
                self._log(tr("В папке нет поддерживаемых файлов.",
                             "No supported files in the folder."), COL_SKIP)
                self._set_phase("idle")
                return

            if not exiftool_available():
                self._log(tr("⚠ exiftool не найден — записать метаданные не получится. "
                             "Скачайте exiftool в ./tools и перезапустите.",
                             "⚠ exiftool not found — metadata can't be written. "
                             "Put exiftool in ./tools and restart."), COL_ERR)

            log = ProcessLog(self.folder)
            if USE_SERVER:
                client = None   # генерация идёт через сервер
            else:
                try:
                    client = make_client()   # простой режим: прямой клиент Azure
                except Exception as e:
                    self._critical_stop(tr(f"Не удалось создать клиент Azure: {e}",
                                           f"Failed to create Azure client: {e}"))
                    self._set_phase("idle")
                    return

            self._log(tr(f"── Генерация метаданных: {total} файлов, {MAX_WORKERS} потоков ──",
                         f"── Generating metadata: {total} files, {MAX_WORKERS} threads ──"),
                      COL_ACCENT)
            self._set_progress(0, f"0/{total}")

            done = ok = skip = err = 0
            ok_records, fatal_msg, access_msg, limit_msg = [], None, None, None
            lock = threading.Lock()

            def worker(path):
                if self._stop_flag.is_set():
                    return {"path": path, "name": path.name, "status": "skip",
                            "message": tr("остановлено пользователем", "stopped by user"),
                            "meta": None, "thumb": None}
                return generate_for_file(client, path, log)

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                futures = {ex.submit(worker, p): p for p in supported}
                for fut in as_completed(futures):
                    path = futures[fut]
                    try:
                        rec = fut.result()
                    except Exception as e:
                        rec = {"path": path, "name": path.name, "status": "error",
                               "message": str(e), "meta": None, "thumb": None}
                    with lock:
                        done += 1
                        st = rec["status"]
                        if st == "ok":
                            ok += 1
                            ok_records.append(rec)
                            self._log(f"✓ [{done}/{total}] {rec['name']} — {rec['message']}", COL_OK)
                        elif st == "skip":
                            skip += 1
                            self._log(f"↷ [{done}/{total}] {rec['name']} — {rec['message']}", COL_SKIP)
                        elif st == "access":
                            err += 1
                            if access_msg is None:
                                access_msg = rec["message"]
                            self._stop_flag.set()   # подписка кончилась — обрубаем батч
                            self._log(f"✗ [{done}/{total}] {rec['name']} — {rec['message']}", COL_ERR)
                        elif st == "limit":
                            err += 1
                            if limit_msg is None:
                                limit_msg = rec["message"]
                            self._stop_flag.set()   # лимит исчерпан — дальше не гоним
                            self._log(f"⏸ [{done}/{total}] {rec['name']} — {rec['message']}", COL_SKIP)
                        elif st == "fatal":
                            err += 1
                            if fatal_msg is None:
                                fatal_msg = rec["message"]
                            self._stop_flag.set()   # обрубаем остальные — батч обречён
                            self._log(f"✗ [{done}/{total}] {rec['name']} — {rec['message']}", COL_ERR)
                        else:
                            err += 1
                            m = f"✗ [{done}/{total}] {rec['name']} — {rec['message']}"
                            self._log(m, COL_ERR)
                            cprint("SedStock ERROR: " + rec['name'] + " — " + str(rec['message']))
                        self._set_progress(done / total,
                                           f"{done}/{total}  ✓{ok} ↷{skip} ✗{err}")

            if access_msg is not None:
                # подписка/триал закончились во время работы — показываем экран плана
                self._log("⏸ " + access_msg, COL_ERR)
                self._set_phase("idle")
                self.after(0, lambda: self._show_plan(api_status()))
                return

            if fatal_msg is not None:
                self._critical_stop(tr(
                    "Azure отклонил запросы — обработка остановлена.\n" + fatal_msg +
                    "\nПроверьте AZURE_API_KEY, AZURE_ENDPOINT и имя AZURE_DEPLOYMENT.",
                    "Azure rejected the requests — processing stopped.\n" + fatal_msg +
                    "\nCheck AZURE_API_KEY, AZURE_ENDPOINT and the AZURE_DEPLOYMENT name."))
                self._set_phase("idle")
                return

            if limit_msg is not None:
                # лимит исчерпан — НЕ выходим: покажем то, что успели обработать
                self._log("⏸ " + limit_msg, COL_SKIP)

            self._log(tr(f"── Генерация завершена: готово {ok}, пропущено {skip}, ошибок {err}. ──",
                         f"── Generation done: {ok} ready, {skip} skipped, {err} errors. ──"),
                      COL_ACCENT)

            if not ok_records:
                self._log(tr("Нечего записывать.", "Nothing to write."), COL_SKIP)
                self._set_phase("idle")
                return

            if self.auto_write_var.get():
                self._log(tr("Режим без предпросмотра — записываю метаданные в файлы…",
                             "No-preview mode — writing metadata to files…"), COL_ACCENT)
                self._commit(ok_records)
            else:
                self._pending = ok_records
                self.after(0, lambda: self._open_preview(ok_records))
        except Exception:
            self._log(tr("Критическая ошибка генерации:\n", "Critical generation error:\n")
                      + traceback.format_exc(), COL_ERR)
            self._set_phase("idle")

    # -- ФАЗА 1.5: лента предпросмотра (со страничной подгрузкой) ------------
    def _open_preview(self, records):
        self._set_phase("preview")
        for w in self.cards.winfo_children():
            w.destroy()
        self._thumb_refs.clear()
        self.preview_records = records
        # чекбокс-переменная привязана к записи, а не к виджету — чтобы выбор жил
        # даже для ещё не отрисованных карточек (страничная подгрузка).
        for r in records:
            r["_var"] = BooleanVar(value=True)
            r["_editor_frame"] = None
        self._rendered_upto = 0
        self._more_btn = None
        self._multi_edit = False
        self._refresh_selall_btn()
        self.preview_title.configure(text=tr(f"Предпросмотр — {len(records)}",
                                             f"Preview — {len(records)}"))
        self._show_preview()
        self._render_next_page()

    def _render_next_page(self):
        """Рисует следующую страницу карточек. CustomTkinter медленно создаёт
        виджеты, поэтому показываем порциями — интерфейс не виснет даже на 300+."""
        if self._more_btn is not None:
            self._more_btn.destroy()
            self._more_btn = None
        end = min(self._rendered_upto + PREVIEW_PAGE_SIZE, len(self.preview_records))
        self._build_range(self._rendered_upto, end)

    def _build_range(self, i, end, chunk=6):
        stop = min(i + chunk, end)
        for r in self.preview_records[i:stop]:
            self._make_card(r)
        self._update_confirm_count()
        if stop < end:
            self.after(1, lambda: self._build_range(stop, end, chunk))
        else:
            self._rendered_upto = end
            remaining = len(self.preview_records) - end
            if remaining > 0:
                self._more_btn = self._btn(
                    self.cards, tr(f"Показать ещё ({remaining})", f"Show more ({remaining})"),
                    self._render_next_page, "muted", width=280, height=42)
                self._more_btn.pack(pady=14)

    def _make_card(self, r):
        r.setdefault("committed", False)
        meta = r["meta"]
        r["_editor_frame"] = None

        card = ctk.CTkFrame(self.cards, fg_color=COL_CARD, corner_radius=12,
                            border_width=1, border_color=COL_BORDER)
        card.pack(fill="x", padx=8, pady=5)
        r["_card"] = card

        # --- компактная шапка (всегда видна; полный редактор — по «Изменить») ---
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=10)

        thumb = r.get("thumb")
        if thumb is not None:
            img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=thumb.size)
            self._thumb_refs.append(img)
            ctk.CTkLabel(head, image=img, text="").pack(side="left", padx=(0, 12), anchor="n")

        mid = ctk.CTkFrame(head, fg_color="transparent")
        mid.pack(side="left", fill="both", expand=True)

        toprow = ctk.CTkFrame(mid, fg_color="transparent")
        toprow.pack(fill="x")
        var = r.get("_var") or BooleanVar(value=True)
        r["_var"] = var
        badge = "🎬" if r.get("kind") == "video" else "🖼"
        ctk.CTkCheckBox(
            toprow, text=f"{badge}  {r['name']}", variable=var,
            command=self._update_confirm_count, font=(FONT_UI, 13, "bold"),
            text_color=COL_TEXT, fg_color=COL_ACCENT, hover_color=COL_ACCENT2,
            checkmark_color=COL_ONACC, border_color=COL_BORDER,
            corner_radius=6, checkbox_width=22, checkbox_height=22, border_width=2,
        ).pack(side="left")
        # кликабельный переключатель EDITORIAL: серый = выкл, оранжевый = вкл
        r["_ed_badge"] = ctk.CTkLabel(
            toprow, text=" EDITORIAL ", font=(FONT_UI, 10, "bold"),
            corner_radius=6, cursor="hand2")
        r["_ed_badge"].pack(side="left", padx=10)
        r["_ed_badge"].bind("<Button-1>", lambda _e, rr=r: self._toggle_editorial(rr))
        self._refresh_editorial_badge(r)
        r["_status_label"] = ctk.CTkLabel(toprow, text="", font=(FONT_UI, 12, "bold"),
                                          text_color=COL_MUTED)
        r["_status_label"].pack(side="right")

        # превью заголовка и описания (обновляются после правок)
        r["_title_preview"] = ctk.CTkLabel(
            mid, text=meta.get("title", ""), anchor="w", justify="left",
            font=(FONT_UI, 16, "bold"), text_color=COL_TEXT, wraplength=600)
        r["_title_preview"].pack(fill="x", pady=(6, 0))
        r["_desc_preview"] = ctk.CTkLabel(
            mid, text=meta.get("description", ""), anchor="w", justify="left",
            font=(FONT_UI, 13), text_color=COL_MUTED, wraplength=600)
        r["_desc_preview"].pack(fill="x", pady=(2, 0))

        btns = ctk.CTkFrame(mid, fg_color="transparent")
        btns.pack(fill="x", pady=(10, 0))
        r["_edit_btn"] = self._btn(btns, tr("✎ Изменить", "✎ Edit"),
                                   lambda: self._toggle_editor(r), "ghost", width=120)
        r["_edit_btn"].pack(side="left")
        r["_write_btn"] = self._btn(btns, tr("Записать в файл", "Write to file"),
                                    lambda: self.write_one(r), "ok", width=160)
        r["_write_btn"].pack(side="left", padx=8)

        if r.get("committed"):
            self._on_card_committed(r)

    # -- переключатель EDITORIAL на карточке --------------------------------
    def _refresh_editorial_badge(self, r):
        b = r.get("_ed_badge")
        if not b:
            return
        if r["meta"].get("is_editorial"):
            b.configure(fg_color=COL_EDIT, text_color=COL_ONACC)
        else:
            b.configure(fg_color=COL_HOVER, text_color=COL_MUTED)

    def _rebuild_editor_if_open(self, r):
        """Пересобрать редактор карточки, чтобы показать/скрыть поля город/место/
        дата после смены editorial. Если был открыт — снова откроет."""
        fr = r.get("_editor_frame")
        if fr is None:
            return
        was_open = bool(fr.winfo_ismapped())
        fr.destroy()
        r["_editor_frame"] = None
        for wk in ("_w_city", "_w_place", "_w_date"):
            r.pop(wk, None)
        if was_open:
            self._toggle_editor(r)

    def _toggle_editorial(self, r):
        new_val = not r["meta"].get("is_editorial")
        # в режиме «Дублировать на выбранные» — вкл/выкл editorial у всех ОТМЕЧЕННЫХ
        if getattr(self, "_multi_edit", False):
            targets = [rr for rr in self.preview_records
                       if rr.get("_var") and rr["_var"].get() and not rr.get("committed")]
            if r not in targets:
                targets.append(r)
        else:
            targets = [r]
        for rr in targets:
            if rr.get("_editor_frame") is not None:
                self._harvest(rr)          # сохранить правки перед пересбором
            rr["meta"]["is_editorial"] = new_val
            self._refresh_editorial_badge(rr)
            self._rebuild_editor_if_open(rr)
        if len(targets) > 1:
            self._log(tr(f"EDITORIAL {'включён' if new_val else 'выключен'} для "
                         f"{len(targets)} отмеченных файлов.",
                         f"EDITORIAL {'ON' if new_val else 'OFF'} for "
                         f"{len(targets)} checked files."), COL_OK)

    def _on_editorial_edit(self, src_r, key, wk):
        """В режиме «Дублировать на выбранные» значение поля editorial (город/место/
        дата), которое печатают в одной карточке, тут же разносится во все
        ОТМЕЧЕННЫЕ галочкой editorial-файлы: в их meta и в открытые редакторы."""
        if not getattr(self, "_multi_edit", False):
            return
        w = src_r.get(wk)
        if w is None:
            return
        val = w.get().strip()
        src_r["meta"][key] = val
        for rr in self.preview_records:
            if rr is src_r or rr.get("committed"):
                continue
            if not (rr.get("_var") and rr["_var"].get()):
                continue
            if not rr["meta"].get("is_editorial"):
                continue
            rr["meta"][key] = val
            ww = rr.get(wk)          # обновляем поле, только если редактор открыт
            if ww is not None:
                try:
                    ww.delete(0, "end")
                    if val:
                        ww.insert(0, val)
                except Exception:
                    pass

    # -- разворачиваемый редактор карточки (строится по требованию) ----------
    def _toggle_editor(self, r):
        fr = r.get("_editor_frame")
        if fr is not None and fr.winfo_ismapped():
            fr.pack_forget()
            r["_edit_btn"].configure(text=tr("✎ Изменить", "✎ Edit"))
            return
        if fr is None:
            fr = self._build_editor(r)
            r["_editor_frame"] = fr
        fr.pack(fill="x", padx=14, pady=(0, 12))
        r["_edit_btn"].configure(text=tr("▲ Свернуть", "▲ Collapse"))

    def _build_editor(self, r):
        meta = r["meta"]
        fr = ctk.CTkFrame(r["_card"], fg_color="transparent")

        ctk.CTkLabel(fr, text=tr("Заголовок", "Title"), anchor="w", font=(FONT_UI, 12),
                     text_color=COL_MUTED).pack(fill="x")
        r["_w_title"] = ctk.CTkEntry(fr, font=(FONT_UI, 14), fg_color=COL_BG,
            text_color=COL_TEXT, border_color=COL_BORDER, border_width=1, corner_radius=8)
        r["_w_title"].insert(0, meta.get("title", ""))
        r["_w_title"].pack(fill="x", pady=(2, 0))

        ctk.CTkLabel(fr, text=tr("Описание", "Description"), anchor="w", font=(FONT_UI, 12),
                     text_color=COL_MUTED).pack(fill="x", pady=(8, 0))
        r["_w_desc"] = ctk.CTkTextbox(fr, height=56, font=(FONT_UI, 13), fg_color=COL_BG,
            text_color=COL_TEXT, border_color=COL_BORDER, border_width=1,
            corner_radius=8, wrap="word")
        r["_w_desc"].insert("1.0", meta.get("description", ""))
        r["_w_desc"].pack(fill="x", pady=(2, 0))

        if meta.get("is_editorial"):
            ed = ctk.CTkFrame(fr, fg_color="transparent")
            ed.pack(fill="x", pady=(8, 0))
            for i, (lbl, key, wk) in enumerate([
                (tr("Город", "City"), "ed_city", "_w_city"),
                (tr("Место события", "Event place"), "ed_place", "_w_place"),
                (tr("Дата", "Date"), "ed_date", "_w_date"),
            ]):
                cell = ctk.CTkFrame(ed, fg_color="transparent")
                cell.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
                ed.grid_columnconfigure(i, weight=1)
                ctk.CTkLabel(cell, text=lbl, anchor="w", font=(FONT_UI, 10),
                             text_color=COL_MUTED).pack(fill="x")
                e = ctk.CTkEntry(cell, font=(FONT_UI, 12), fg_color=COL_BG,
                                 text_color=COL_TEXT, border_color=COL_BORDER,
                                 border_width=1, corner_radius=8,
                                 placeholder_text=tr("не определено", "not detected"))
                if meta.get(key):
                    e.insert(0, meta[key])
                e.pack(fill="x")
                r[wk] = e
                # в режиме «Дублировать на выбранные» — то, что печатаешь в
                # город/место/дату, тут же заносится во все ОТМЕЧЕННЫЕ editorial-файлы
                e.bind("<KeyRelease>",
                       lambda _ev, rr=r, kk=key, wk_=wk: self._on_editorial_edit(rr, kk, wk_))
            # подсказка, чтобы отец понимал поведение
            if getattr(self, "_multi_edit", False):
                ctk.CTkLabel(fr, text=tr(
                    "Режим «Дублировать на выбранные»: город/место/дата применяются "
                    "ко всем отмеченным галочкой фото.",
                    "“Duplicate to selected” is on: city/place/date apply to every "
                    "checked photo."),
                    anchor="w", font=(FONT_UI, 10), text_color=COL_ACCENT).pack(fill="x", pady=(4, 0))

        # ключевые слова — компактным полем через запятую (без сотен чипов = быстро)
        ctk.CTkLabel(fr, text=tr(f"Ключевые слова через запятую ({len(meta['keywords'])})",
                                 f"Keywords, comma-separated ({len(meta['keywords'])})"),
                     anchor="w", font=(FONT_UI, 12), text_color=COL_MUTED).pack(fill="x", pady=(8, 0))
        r["_w_kw"] = ctk.CTkTextbox(fr, height=76, font=(FONT_UI, 13), fg_color=COL_BG,
            text_color=COL_TEXT, border_color=COL_BORDER, border_width=1,
            corner_radius=8, wrap="word")
        r["_w_kw"].insert("1.0", ", ".join(meta.get("keywords", [])))
        r["_w_kw"].pack(fill="x", pady=(2, 0))

        rel = ctk.CTkFrame(fr, fg_color="transparent")
        rel.pack(fill="x", pady=(10, 0))
        rel_label = ctk.CTkLabel(rel, text=tr("Релиз не прикреплён", "No release attached"),
                                 anchor="w", font=(FONT_UI, 11), text_color=COL_MUTED)
        rel_label.pack(side="left", padx=(0, 10))
        r["_rel_label"] = rel_label   # чтобы обновлять подпись при релизе-ко-всем
        if r.get("release_src"):
            rel_label.configure(text="📎 " + Path(r["release_src"]).name, text_color=COL_ACCENT)
        self._btn(rel, tr("📎 Прикрепить релиз", "📎 Attach release"),
                  lambda: self._attach_release_dialog(r, rel_label), "ghost",
                  width=176).pack(side="left")
        self._btn(rel, "✕", lambda: self._clear_release(r, rel_label), "ghost",
                  width=34).pack(side="left", padx=6)
        return fr

    # -- сбор правок из виджетов редактора обратно в meta -------------------
    def _harvest(self, r):
        w = r.get("_w_title")
        if w is not None:
            t = w.get().strip()
            if t:
                r["meta"]["title"] = t
        w = r.get("_w_desc")
        if w is not None:
            r["meta"]["description"] = w.get("1.0", "end").strip()
        w = r.get("_w_kw")
        if w is not None:
            kws = _to_single_words(w.get("1.0", "end"))
            if kws:
                r["meta"]["keywords"] = kws[:KW_HARD_LIMIT]
        for key, wk in (("ed_city", "_w_city"), ("ed_place", "_w_place"),
                        ("ed_date", "_w_date")):
            w = r.get(wk)
            if w is not None:
                r["meta"][key] = w.get().strip()
        if r.get("_title_preview"):
            r["_title_preview"].configure(text=r["meta"].get("title", ""))
        if r.get("_desc_preview"):
            r["_desc_preview"].configure(text=r["meta"].get("description", ""))

    def _attach_release_dialog(self, r, label_widget):
        f = filedialog.askopenfilename(
            title=tr(f"Файл релиза для {r['name']}", f"Release file for {r['name']}"),
            filetypes=[(tr("Релиз (PDF/изображение)", "Release (PDF/image)"),
                        "*.pdf *.jpg *.jpeg *.png *.tif *.tiff"),
                       (tr("Все файлы", "All files"), "*.*")])
        if not f:
            return
        name = Path(f).name
        if getattr(self, "_multi_edit", False):
            # режим «Дублировать на выбранные» → релиз применяем ко всем ОТМЕЧЕННЫМ
            applied = 0
            for rr in self.preview_records:
                if rr.get("_var") and rr["_var"].get() and not rr.get("committed"):
                    rr["release_src"] = f
                    applied += 1
                    lw = rr.get("_rel_label")
                    if lw is not None:
                        try:
                            lw.configure(text="📎 " + name, text_color=COL_ACCENT)
                        except Exception:
                            pass
            self._log(tr(f"📎 Релиз «{name}» применён к {applied} отмеченным файлам.",
                         f"📎 Release “{name}” applied to {applied} checked files."),
                      COL_OK)
        else:
            r["release_src"] = f
            label_widget.configure(text="📎 " + name, text_color=COL_ACCENT)

    def _clear_release(self, r, label_widget):
        r.pop("release_src", None)
        label_widget.configure(text=tr("Релиз не прикреплён", "No release attached"),
                               text_color=COL_MUTED)

    def _check_all(self, value):
        """Просто отметить/снять галочки на всех карточках (НЕ режим)."""
        for r in self.preview_records:
            if r.get("_var"):
                r["_var"].set(value)
        self._update_confirm_count()

    def _toggle_multi_edit(self):
        """Вкл/выкл режим «Дублировать на выбранные». Галочки НЕ трогает.
        При ВКЛючении СРАЗУ дублирует уже введённый эдиториал на отмеченные."""
        self._multi_edit = not getattr(self, "_multi_edit", False)
        self._refresh_selall_btn()
        if self._multi_edit:
            self._apply_editorial_to_selected()

    def _apply_editorial_to_selected(self):
        """Берёт заполненный editorial (город/место/дата) у отмеченной галочкой
        фотки и дублирует на ВСЕ остальные отмеченные: включает у них EDITORIAL и
        копирует значения. Вызывается по кнопке «Дублировать на выбранные»."""
        # сначала соберём то, что уже напечатано в открытых редакторах, в meta
        for r in self.preview_records:
            if r.get("_editor_frame") is not None:
                self._harvest(r)
        checked = [r for r in self.preview_records
                   if r.get("_var") and r["_var"].get() and not r.get("committed")]
        # источник — отмеченный editorial-файл, где заполнено хотя бы одно поле
        keys = ("ed_city", "ed_place", "ed_date")
        src = None
        for r in checked:
            if r["meta"].get("is_editorial") and any((r["meta"].get(k) or "").strip() for k in keys):
                src = r
                break
        if src is None:
            self._log(tr("Нечего дублировать: заполни город/место/дату в одном "
                         "editorial-фото и отметь галочками нужные.",
                         "Nothing to duplicate: fill city/place/date in one editorial "
                         "photo and check the ones you want."), COL_SKIP)
            return
        vals = {k: src["meta"].get(k, "") for k in keys}
        n = 0
        for r in checked:
            if r is src:
                continue
            r["meta"]["is_editorial"] = True          # включаем EDITORIAL у цели
            for k in keys:
                r["meta"][k] = vals[k]
            self._refresh_editorial_badge(r)
            self._rebuild_editor_if_open(r)           # открытый редактор покажет новые поля
            n += 1
        if n:
            self._log(tr(f"Эдиториал продублирован на {n} отмеченных фото.",
                         f"Editorial duplicated to {n} checked photos."), COL_OK)

    def _refresh_selall_btn(self):
        b = getattr(self, "_selall_btn", None)
        if b is None:
            return
        if self._multi_edit:
            b.configure(fg_color=COL_ACCENT, text_color=COL_ONACC,
                        text=tr("Дублировать на выбранные ✓", "Duplicate to selected ✓"))
        else:
            b.configure(fg_color="transparent", text_color=COL_ACCENT,
                        text=tr("Дублировать на выбранные", "Duplicate to selected"))

    def _update_confirm_count(self):
        n = sum(1 for r in self.preview_records
                if r.get("_var") and r["_var"].get() and not r.get("committed"))
        self.confirm_btn.configure(
            text=tr(f"Применить ко всем ({n})", f"Apply to all ({n})"),
            state="normal" if n else "disabled")

    # -- статус карточки ----------------------------------------------------
    def _set_card_status(self, r, text, color):
        lbl = r.get("_status_label")
        if lbl is not None:
            lbl.configure(text=text, text_color=color)

    def _on_card_committed(self, r):
        self._set_card_status(r, tr("Записано ✓", "Written ✓"), COL_OK)
        if r.get("_write_btn"):
            r["_write_btn"].configure(text=tr("Записано ✓", "Written ✓"), state="disabled")
        self._update_confirm_count()

    def _busy(self):
        return bool(self._worker and self._worker.is_alive())

    def _run_bg(self, fn, arg):
        if self._busy():
            return
        def wrap():
            try:
                fn(arg)
            except Exception:
                self._log(tr("Ошибка операции:\n", "Operation error:\n")
                          + traceback.format_exc(), COL_ERR)
        self._worker = threading.Thread(target=wrap, daemon=True)
        self._worker.start()

    # -- запись метаданных из карточек (остаёмся в ленте) -------------------
    def confirm_write(self):
        selected = [r for r in self.preview_records
                    if r.get("_var") and r["_var"].get() and not r.get("committed")]
        if not selected or self._busy():
            return
        for r in selected:
            self._harvest(r)
        self._run_bg(self._commit_cards_worker, selected)

    def write_one(self, r):
        if self._busy() or r.get("committed"):
            return
        self._harvest(r)
        self._run_bg(self._commit_cards_worker, [r])

    def _commit_cards_worker(self, records):
        if not exiftool_available():
            self._log(tr("✗ exiftool не найден — запись невозможна.",
                         "✗ exiftool not found — cannot write."), COL_ERR)
            return
        log = ProcessLog(self.folder)
        total = len(records)
        done = ok = err = 0
        self._set_progress(0, f"0/{total}")
        for r in records:
            self.after(0, lambda rr=r: self._set_card_status(rr, tr("запись…", "writing…"), COL_MUTED))
            status, msg = commit_for_file(r["path"], r["meta"], log)
            done += 1
            if status == "ok":
                ok += 1
                r["committed"] = True
                self._log(tr(f"✓ {r['name']} — метаданные записаны",
                             f"✓ {r['name']} — metadata written"), COL_OK)
                if r.get("release_src"):
                    try:
                        dest = attach_release(r["path"], r["release_src"])
                        self._log(tr(f"   📎 релиз → {dest.name}", f"   📎 release → {dest.name}"),
                                  COL_MUTED)
                    except Exception as e:
                        self._log(tr(f"   ⚠ релиз не скопирован: {e}",
                                     f"   ⚠ release not copied: {e}"), COL_ERR)
                self.after(0, lambda rr=r: self._on_card_committed(rr))
            else:
                err += 1
                self._log(f"✗ {r['name']} — {msg}", COL_ERR)
                self.after(0, lambda rr=r, mm=msg: self._set_card_status(
                    rr, tr("ошибка записи", "write error"), COL_ERR))
            self._set_progress(done / total, f"{done}/{total}  ✓{ok} ✗{err}")

    # -- отправка на площадки (FTP/SFTP) ------------------------------------
    def _configured_platforms(self):
        s = load_upload_settings()
        plats = []
        dp = s["depositphotos"]
        if dp["host"].strip() and dp["user"].strip():
            plats.append(("Depositphotos", "ftp", dp))
        ad = s["adobe"]
        if ad["host"].strip() and ad["user"].strip():
            plats.append(("Adobe Stock", "sftp", ad))
        return plats

    def send_all_committed(self):   # заморожено (загрузка на стоки убрана из UI)
        recs = [r for r in self.preview_records if r.get("committed")]
        if not recs or self._busy():
            if not recs:
                self._log("Нет подтверждённых файлов. Сначала «Записать».", COL_SKIP)
            return
        self._run_bg(self._send_worker, recs)

    def send_one(self, r):
        if self._busy():
            return
        if not r.get("committed"):
            self._set_card_status(r, "сначала «Записать»", COL_SKIP)
            return
        self._run_bg(self._send_worker, [r])

    def _send_worker(self, records):
        plats = self._configured_platforms()
        if not plats:
            self._log("✗ Не заданы доступы. Откройте «Настройки отправки».", COL_ERR)
            for r in records:
                self.after(0, lambda rr=r: self._set_card_status(rr, "нет доступов", COL_ERR))
            return
        names = ", ".join(p[0] for p in plats)
        self._log(f"── Отправка: {len(records)} файлов → {names} ──", COL_ACCENT)
        total = len(records)
        done = 0
        adobe_used = any(p[1] == "sftp" for p in plats)
        for r in records:
            self.after(0, lambda rr=r: self._set_card_status(rr, "отправка…", COL_MUTED))
            for pname, proto, cfg in plats:
                if r["uploads"].get(pname) == "ok":
                    continue  # повторно шлём только неудачные
                try:
                    if proto == "ftp":
                        upload_ftp(cfg["host"], cfg["user"], cfg["password"], str(r["path"]))
                    else:
                        upload_sftp(cfg["host"], cfg["port"], cfg["user"],
                                    cfg["password"], str(r["path"]))
                    r["uploads"][pname] = "ok"
                    r.setdefault("_upload_errors", {}).pop(pname, None)
                    self._log(f"✓ {r['name']} → {pname}", COL_OK)
                except Exception as e:
                    r["uploads"][pname] = "err"
                    r.setdefault("_upload_errors", {})[pname] = str(e)
                    self._log(f"✗ {r['name']} → {pname}: {e}", COL_ERR)
            done += 1
            self.after(0, lambda rr=r: self._refresh_send_status(rr))
            self._set_progress(done / total, f"{done}/{total}")
        if adobe_used:
            self._log("ℹ Файлы загружены на сервер Adobe. Возможно, потребуется зайти в "
                      "контрибьютор-портал Adobe и нажать «Отправить на модерацию» "
                      "(проверьте при первой реальной отправке).", COL_SKIP)
        self._log("── Отправка завершена. Неудачные можно отправить повторно. ──", COL_ACCENT)

    def _refresh_send_status(self, r):
        ups = r.get("uploads", {})
        if not ups:
            self._set_card_status(r, "Записано ✓", COL_OK)
            return
        errs = r.get("_upload_errors", {})
        ok_parts = [f"{p} ✓" for p, st in ups.items() if st == "ok"]
        err_parts = [f"{p} ✗" for p, st in ups.items() if st != "ok"]
        text = "→ " + " · ".join(ok_parts + err_parts)
        if err_parts:
            # показываем причину первой ошибки прямо на карточке
            first_err = next(iter(errs.values()), "")
            if first_err:
                text += ": " + first_err
            if len(text) > 120:
                text = text[:118] + "…"
            self._set_card_status(r, text, COL_ERR)
        else:
            self._set_card_status(r, text, COL_OK)

    def cancel_preview(self):
        self._pending = []
        for w in self.cards.winfo_children():
            w.destroy()
        self._thumb_refs.clear()
        self.preview_records = []
        self._show_log()
        self._log(tr("Лента закрыта.", "Preview closed."), COL_MUTED)
        self._set_phase("idle")

    # ======================================================================
    #  ==== ОКНО «ИНСТРУКЦИИ ИИ» ====
    # ======================================================================
    def _instr_help(self):
        return tr(
            "Здесь можно задать свои пожелания к ИИ — они добавляются к запросу при "
            "КАЖДОЙ генерации (и для фото, и для видео).\n\n"
            "ЧТО РЕАЛЬНО ВЛИЯЕТ (пишите такое):\n"
            "• Тематика и приоритеты: «делай упор на бизнес, деньги, финансы».\n"
            "• Любимые/частые ключевые слова: «по возможности добавляй: success, teamwork, "
            "modern».\n"
            "• Стиль описаний: «описания делай энергичными и продающими».\n"
            "• Что игнорировать: «не добавляй слова про религию».\n"
            "• Уточнения по объектам: «если это цветок — указывай его вид».\n\n"
            "ЧТО НЕ СРАБОТАЕТ (это жёстко задано программой):\n"
            "• Изменить число ключевых слов (всегда 48–50), формат возраста (число), "
            "длину title (10–12 слов) или описания (1 предложение).\n"
            "• Заставить писать неправду о том, чего нет на фото.\n\n"
            "Пусто — ИИ работает по умолчанию. Сохраняется автоматически при закрытии окна.",

            "Here you can add your own guidance for the AI — it's added to the request on "
            "EVERY generation (both photos and videos).\n\n"
            "WHAT ACTUALLY WORKS (write things like this):\n"
            "• Themes and priorities: “focus on business, money, finance”.\n"
            "• Preferred/frequent keywords: “when possible add: success, teamwork, modern”.\n"
            "• Description style: “make descriptions energetic and sales-oriented”.\n"
            "• What to ignore: “don't add religion-related words”.\n"
            "• Object details: “if it's a flower — name its species”.\n\n"
            "WHAT WON'T WORK (these are fixed by the app):\n"
            "• Changing the number of keywords (always 48–50), age format (a number), "
            "title length (10–12 words) or description (1 sentence).\n"
            "• Making it write things that aren't in the photo.\n\n"
            "Empty — the AI uses its defaults. Saved automatically when the window closes.")

    def open_instructions(self):
        if self._instr_win is not None and self._instr_win.winfo_exists():
            self._instr_win.focus()
            return
        win = ctk.CTkToplevel(self)
        self._instr_win = win
        win.title(tr("Инструкции ИИ", "AI instructions"))
        win.geometry("720x600")
        win.configure(fg_color=COL_BG)
        win.transient(self)

        ctk.CTkLabel(win, text=tr("Инструкции для ИИ", "Instructions for the AI"),
                     font=(FONT_UI, 22, "bold"),
                     text_color=COL_TEXT).pack(anchor="w", padx=24, pady=(22, 8))

        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        box = ctk.CTkTextbox(body, font=(FONT_UI, 15), fg_color=COL_PANEL,
                             text_color=COL_TEXT, border_color=COL_BORDER,
                             border_width=1, corner_radius=10, wrap="word")
        box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        box.insert("1.0", CUSTOM_INSTRUCTIONS)

        help_box = ctk.CTkTextbox(body, font=(FONT_UI, 13), fg_color=COL_BG,
                                  text_color=COL_TEXT, border_color=COL_BORDER,
                                  border_width=1, corner_radius=10, wrap="word")
        help_box.grid(row=0, column=1, sticky="nsew")
        help_box.insert("1.0", self._instr_help())
        help_box.configure(state="disabled")

        status = ctk.CTkLabel(win, text="", font=(FONT_UI, 11), text_color=COL_MUTED)
        status.pack(anchor="w", padx=24)

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=(6, 20))

        def do_load():
            f = filedialog.askopenfilename(
                title=tr("Файл с инструкциями", "Instructions file"),
                filetypes=[(tr("Текст/PDF/Markdown", "Text/PDF/Markdown"), "*.txt *.md *.pdf"),
                           (tr("Все файлы", "All files"), "*.*")])
            if not f:
                return
            try:
                box.delete("1.0", "end")
                box.insert("1.0", extract_text_from_file(f))
                status.configure(text=tr(f"Загружено из {Path(f).name}",
                                         f"Loaded from {Path(f).name}"), text_color=COL_OK)
            except Exception as e:
                status.configure(text=tr(f"Ошибка чтения: {e}", f"Read error: {e}"),
                                 text_color=COL_ERR)

        def do_save():
            text = box.get("1.0", "end").strip()
            try:
                save_custom_instructions(text)
                set_custom_instructions(text)
                status.configure(text=tr("Сохранено — применяется к следующим генерациям.",
                                         "Saved — applies to the next generations."),
                                 text_color=COL_OK)
            except Exception as e:
                status.configure(text=tr(f"Ошибка сохранения: {e}", f"Save error: {e}"),
                                 text_color=COL_ERR)

        def do_clear():
            box.delete("1.0", "end")
            status.configure(text=tr("Очищено. Сохранится при закрытии окна.",
                                     "Cleared. Will save when the window closes."),
                             text_color=COL_MUTED)

        ctk.CTkButton(bar, text=tr("Загрузить файл", "Load file"), width=140, height=36,
                      corner_radius=10,
                      command=do_load, fg_color="transparent", hover_color=COL_HOVER,
                      text_color=COL_ACCENT, font=(FONT_UI, 12, "bold"),
                      border_width=1, border_color=COL_BORDER).pack(side="left")
        ctk.CTkButton(bar, text=tr("Очистить", "Clear"), width=100, height=36, corner_radius=10,
                      command=do_clear, fg_color=COL_HOVER, hover_color=COL_BORDER,
                      text_color=COL_TEXT, font=(FONT_UI, 12)).pack(side="left", padx=10)
        ctk.CTkButton(bar, text=tr("Сохранить", "Save"), width=140, height=36, corner_radius=10,
                      command=do_save, fg_color=COL_ACCENT, hover_color=COL_ACCENT2,
                      text_color=COL_ONACC, font=(FONT_UI, 12, "bold")).pack(side="right")

        def on_close():
            do_save()
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

    # ======================================================================
    #  ==== ОКНО «НАСТРОЙКИ ОТПРАВКИ» (FTP/SFTP) — заморожено ====
    # ======================================================================
    def open_settings(self):
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.focus()
            return
        win = ctk.CTkToplevel(self)
        self._settings_win = win
        win.title("Настройки отправки")
        win.geometry("560x560")
        win.configure(fg_color=COL_BG)
        win.transient(self)

        s = load_upload_settings()
        entries = {}

        ctk.CTkLabel(win, text="Настройки отправки", font=(FONT_UI, 22, "bold"),
                     text_color=COL_TEXT).pack(anchor="w", padx=24, pady=(22, 2))
        ctk.CTkLabel(win, text="Доступы вводятся один раз и хранятся локально рядом с "
                     "программой. Отправка запускается вручную кнопками в ленте.",
                     font=(FONT_UI, 11), text_color=COL_MUTED, justify="left",
                     wraplength=500).pack(anchor="w", padx=24, pady=(0, 8))

        # Кнопка «Сохранить» и статус — закреплены внизу (всегда видны)
        bottom = ctk.CTkFrame(win, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=24, pady=(6, 16))
        status = ctk.CTkLabel(bottom, text="", font=(FONT_UI, 11), text_color=COL_MUTED)
        status.pack(side="left")

        # Прокручиваемая область с полями (листается колёсиком мыши)
        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        def field(parent, label, value, show=None, placeholder=None):
            ctk.CTkLabel(parent, text=label, anchor="w", font=(FONT_UI, 11),
                         text_color=COL_MUTED).pack(fill="x", pady=(6, 0))
            e = ctk.CTkEntry(parent, font=(FONT_UI, 13), fg_color=COL_BG,
                             text_color=COL_TEXT, border_color=COL_BORDER,
                             border_width=1, corner_radius=8,
                             placeholder_text=(placeholder or ""),
                             show=("•" if show else None))
            if value:
                e.insert(0, value)
            e.pack(fill="x")
            return e

        def card(title, subtitle):
            c = ctk.CTkFrame(scroll, fg_color=COL_PANEL, corner_radius=12,
                             border_width=1, border_color=COL_BORDER)
            c.pack(fill="x", padx=16, pady=8)
            inner = ctk.CTkFrame(c, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=12)
            ctk.CTkLabel(inner, text=title, anchor="w", font=(FONT_UI, 14, "bold"),
                         text_color=COL_TEXT).pack(fill="x")
            ctk.CTkLabel(inner, text=subtitle, anchor="w", font=(FONT_UI, 10),
                         text_color=COL_MUTED, justify="left", wraplength=470).pack(fill="x", pady=(0, 4))
            return inner

        dp = card("Depositphotos", "FTP — загрузка файлов со встроенными метаданными. "
                                   "Сервер обычно ftp.depositphotos.com; логин/пароль — из "
                                   "личного кабинета контрибьютора (раздел FTP-загрузки).")
        entries["dp_host"] = field(dp, "FTP-сервер", s["depositphotos"]["host"],
                                   placeholder="ftp.depositphotos.com")
        entries["dp_user"] = field(dp, "Логин", s["depositphotos"]["user"])
        entries["dp_pass"] = field(dp, "Пароль", s["depositphotos"]["password"], show=True)

        ad = card("Adobe Stock", "SFTP — загрузка файлов; отправку на модерацию, возможно, "
                                 "нужно подтвердить в кабинете Adobe")
        entries["ad_host"] = field(ad, "SFTP-сервер", s["adobe"]["host"],
                                   placeholder="sftp.contributor.adobestock.com")
        entries["ad_port"] = field(ad, "Порт", s["adobe"]["port"], placeholder="22")
        entries["ad_user"] = field(ad, "Логин", s["adobe"]["user"])
        entries["ad_pass"] = field(ad, "Пароль", s["adobe"]["password"], show=True)

        def do_save():
            new = {
                "depositphotos": {
                    "host": entries["dp_host"].get().strip(),
                    "user": entries["dp_user"].get().strip(),
                    "password": entries["dp_pass"].get(),
                },
                "adobe": {
                    "host": entries["ad_host"].get().strip(),
                    "port": entries["ad_port"].get().strip() or "22",
                    "user": entries["ad_user"].get().strip(),
                    "password": entries["ad_pass"].get(),
                },
            }
            try:
                save_upload_settings(new)
                status.configure(text="Сохранено.", text_color=COL_OK)
            except Exception as e:
                status.configure(text=f"Ошибка сохранения: {e}", text_color=COL_ERR)

        ctk.CTkButton(bottom, text="Сохранить", width=150, height=38, corner_radius=10,
                      command=do_save, fg_color=COL_ACCENT, hover_color=COL_ACCENT2,
                      text_color=COL_ONACC, font=(FONT_UI, 13, "bold")).pack(side="right")

        # автосохранение при закрытии окна — доступы не теряются
        def on_close():
            do_save()
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

    # ======================================================================
    #  ==== БРАУЗЕРНЫЙ САБМИТ НА МОДЕРАЦИЮ ====
    # ======================================================================
    def _show_continue_controls(self):
        self.continue_btn.pack(side="left", padx=(16, 4))
        self.submit_stop_btn.pack(side="left", padx=4)

    def _hide_continue_controls(self):
        self.continue_btn.pack_forget()
        self.submit_stop_btn.pack_forget()

    def _submit_continue(self):
        self._continue_evt.set()

    def _submit_stop_click(self):
        self._submit_stop.set()
        self._continue_evt.set()   # разблокировать ожидание
        self._log("⏸ Останавливаю браузерный сабмит…", COL_SKIP)

    # Конфиги площадок в одном месте
    _SUBMIT_CFG = {
        "depositphotos": dict(
            name="Depositphotos", page_url=DP_SUBMIT_PAGE_URL, start_url=DP_START_URL,
            sel_texts=DP_SELECT_ALL_TEXTS, sel_desc=DP_SELECT_ALL_DESC,
            sub_texts=DP_SUBMIT_TEXTS, sub_desc=DP_SUBMIT_DESC,
            hint="Открой Seller's Menu → Unfinished Files, выдели файлы и нажми "
                 "«Send for review»."),
        "adobe": dict(
            name="Adobe Stock", page_url=ADOBE_SUBMIT_PAGE_URL, start_url=ADOBE_START_URL,
            sel_texts=ADOBE_SELECT_ALL_TEXTS, sel_desc=ADOBE_SELECT_ALL_DESC,
            sub_texts=ADOBE_SUBMIT_TEXTS, sub_desc=ADOBE_SUBMIT_DESC,
            hint="Открой вкладку New (Uploaded files), выдели файлы и нажми «Submit»."),
    }

    def submit_platform(self, platform):
        """Автоматический сабмит через системный браузер (Edge/Chrome).
        Если ни один браузер не запустился — автоматически откроет страницу
        в обычном браузере, чтобы можно было завершить вручную."""
        cfg = self._SUBMIT_CFG[platform]
        self._start_submit(platform, cfg["name"], cfg["page_url"],
                           cfg["sel_texts"], cfg["sel_desc"],
                           cfg["sub_texts"], cfg["sub_desc"])

    def _open_submit_page(self, name, url, hint):
        self._show_log()
        try:
            webbrowser.open(url)
            self._log(f"Открыл в браузере страницу сабмита {name}.", COL_ACCENT)
            self._log(f"→ {hint}", COL_MUTED)
            self._log("(Ты уже залогинен в своём браузере — осталось выделить файлы "
                      "и нажать кнопку отправки.)", COL_MUTED)
        except Exception as e:
            self._log(f"Не удалось открыть браузер: {e}", COL_ERR)

    def _start_submit(self, platform, nice_name, start_url,
                      sel_texts, sel_desc, sub_texts, sub_desc):
        if self._busy():
            self._log("Дождись окончания текущей операции.", COL_SKIP)
            return
        self._show_log()
        self._continue_evt.clear()
        self._submit_stop.clear()
        semi_auto = False   # автоматически жмём кнопку отправки
        self._log(f"── Сабмит {nice_name} (автоматически) ──", COL_ACCENT)

        def wait_continue():
            self.after(0, self._show_continue_controls)
            while not self._continue_evt.is_set():
                if self._submit_stop.is_set():
                    self.after(0, self._hide_continue_controls)
                    return False
                time.sleep(0.15)
            self.after(0, self._hide_continue_controls)
            return not self._submit_stop.is_set()

        def worker():
            try:
                client = make_client()
                run_submit_flow(
                    platform, start_url, sel_texts, sel_desc, sub_texts, sub_desc,
                    semi_auto, client, self._log, wait_continue, self._submit_stop,
                    fallback_url=start_url)
            except Exception:
                self._log("Ошибка сабмита:\n" + traceback.format_exc(), COL_ERR)
            finally:
                self.after(0, self._hide_continue_controls)
                self._log("── Сабмит завершён. ──", COL_ACCENT)

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    # -- ФАЗА 2 (авто-режим): запись метаданных в файлы ---------------------
    def _commit(self, records):
        try:
            if not exiftool_available():
                self._critical_stop(tr(
                    "exiftool не найден — запись невозможна.\n"
                    "Скачайте exiftool в папку ./tools и перезапустите.",
                    "exiftool not found — cannot write.\n"
                    "Put exiftool in the ./tools folder and restart."))
                self._set_phase("idle")
                return

            log = ProcessLog(self.folder)
            total = len(records)
            self._log(tr(f"── Запись метаданных: {total} файлов ──",
                         f"── Writing metadata: {total} files ──"), COL_ACCENT)
            self._set_progress(0, f"0/{total}")

            done = ok = err = 0
            for r in records:
                if self._stop_flag.is_set():
                    self._log(tr("⏸ Запись остановлена пользователем.",
                                 "⏸ Writing stopped by user."), COL_SKIP)
                    break
                status, msg = commit_for_file(r["path"], r["meta"], log)
                done += 1
                if status == "ok":
                    ok += 1
                    self._log(tr(f"✓ [{done}/{total}] {r['name']} — записано",
                                 f"✓ [{done}/{total}] {r['name']} — written"), COL_OK)
                    # если к файлу прикреплён релиз — кладём его рядом
                    if r.get("release_src"):
                        try:
                            dest = attach_release(r["path"], r["release_src"])
                            self._log(tr(f"   📎 релиз → {dest.name}",
                                         f"   📎 release → {dest.name}"), COL_MUTED)
                        except Exception as e:
                            self._log(tr(f"   ⚠ релиз не скопирован: {e}",
                                         f"   ⚠ release not copied: {e}"), COL_ERR)
                            cprint("SedStock RELEASE ERROR: " + r['name'] + " — " + str(e))
                else:
                    err += 1
                    m = f"✗ [{done}/{total}] {r['name']} — {msg}"
                    self._log(m, COL_ERR)
                    cprint("SedStock WRITE ERROR: " + r['name'] + " — " + str(msg))
                self._set_progress(done / total, f"{done}/{total}  ✓{ok} ✗{err}")

            self._log(tr(f"── Готово. Записано {ok}, ошибок {err}. "
                         f"Файлы готовы для StockSubmitter. ──",
                         f"── Done. Written {ok}, errors {err}. "
                         f"Files are ready for StockSubmitter. ──"), COL_ACCENT)
        except Exception:
            self._log(tr("Критическая ошибка записи:\n", "Critical write error:\n")
                      + traceback.format_exc(), COL_ERR)
        finally:
            self._pending = []
            self._set_phase("idle")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        app = App()
        app.mainloop()
    except Exception:
        # В сборке --noconsole тихое падение при старте не видно вообще. Пишем
        # лог рядом с программой и, по возможности, показываем окно с текстом —
        # чтобы у пользователя (и у нас) была причина, а не «просто не работает».
        tb = traceback.format_exc()
        logpath = None
        try:
            logpath = _base_dir() / "SedStock_crash.log"
            logpath.write_text(tb, encoding="utf-8")
        except Exception:
            pass
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror(
                tr("SedStock — ошибка запуска", "SedStock — startup error"),
                tr("Программа не смогла запуститься.\n\n", "The app failed to start.\n\n")
                + tb[-1500:] +
                (tr(f"\n\nПодробности: {logpath}", f"\n\nDetails: {logpath}") if logpath else ""))
            r.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
