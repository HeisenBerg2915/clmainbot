import logging
import asyncio
import re
import os
import time
import random
import urllib.parse
from datetime import datetime
from typing import Union, List
import aiohttp
import httpx
from bs4 import BeautifulSoup
from pyrogram.errors import InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid
from pyrogram.types import Message, InlineKeyboardButton
from pyrogram import enums

# Database and Project Configurations
from database.users_chats_db import db
from database.postersave import get_cached_poster, save_poster_to_cache
from info import (
    REQ_CHANNEL1, REQ_CHANNEL2, ADMINS, 
    TMDB_API_KEYS, OMDB_API_KEYS, DEFAULT_POSTER, 
    LONG_IMDB_DESCRIPTION, MAX_LIST_ELM
)

# Safely import optional third-party modules
try:
    import imdbio as _imdbio
    from imdbio.exceptions import ImdbioError as _ImdbioError
    IMDBIO_AVAILABLE = True
except ImportError:
    IMDBIO_AVAILABLE = False

# Safely handle optional authorization channel config
try:
    from info import AUTH_CHANNEL
except ImportError:
    AUTH_CHANNEL = None

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BTN_URL_REGEX = re.compile(r"(\[([^\[]+?)\]\((buttonurl|buttonalert):(?:/{0,2})(.+?)(:same)?\))")
BANNED = {}
SMART_OPEN = '“'
SMART_CLOSE = '”'
START_CHAR = ('\'', '"', SMART_OPEN)
BAD_TMDB_KEYS = {}
BAD_OMDB_KEYS = {}

class temp(object):
    BANNED_USERS = []
    BANNED_CHATS = []
    ME = None
    CURRENT = int(os.environ.get("SKIP", 2))
    CANCEL = False
    MELCOW = {}
    U_NAME = None
    B_NAME = None
    SETTINGS = {}



def _parse_api_keys(keys_config):
    """Cleans and structures API keys from config variables."""
    if isinstance(keys_config, str):
        return [k.strip() for k in keys_config.split(",") if k.strip()]
    return keys_config or []




async def get_tmdb_poster(movie_name, tmdb_api_key):
    try:
        query = movie_name.strip()
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', query)
        year = year_match.group(1) if year_match else None
        title = re.sub(r'\s*\b(19\d{2}|20\d{2})\b\s*', ' ', query).strip()
        normalize = lambda s: re.sub(r'[^a-z0-9]', '', (s or '').lower())
        target = normalize(title)
        if not target: return None

        headers = {"Accept": "application/json"}
        timeout = aiohttp.ClientTimeout(total=5)

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            url = "https://api.themoviedb.org/3/search/multi"
            params = {"api_key": tmdb_api_key, "query": title, "include_adult": "false"}
            async with session.get(url, params=params) as response:
                if response.status != 200: return None
                data = await response.json()

            matches = []
            for item in data.get("results", []):
                kind = item.get("media_type")
                if kind not in ("movie", "tv"): continue
                names = [item.get("title"), item.get("original_title")] if kind == "movie" else [item.get("name"), item.get("original_name")]
                if not any(normalize(name) == target for name in names if name): continue
                date = item.get("release_date") or item.get("first_air_date") or ""
                if year and date[:4] != year: continue
                matches.append(item)

            if not matches: return None
            matches.sort(key=lambda x: (bool(x.get("poster_path")), float(x.get("vote_average") or 0), int(x.get("vote_count") or 0)), reverse=True)

            for movie in matches:
                path = movie.get("poster_path")
                if path: return f"https://image.tmdb.org/t/p/original{path}"

            for movie in matches:
                path = movie.get("backdrop_path")
                if path: return f"https://image.tmdb.org/t/p/original{path}"

                kind, media_id = movie.get("media_type"), movie.get("id")
                if kind and media_id:
                    endpoint = f"https://api.themoviedb.org/3/{kind}/{media_id}/images"
                    async with session.get(endpoint, params={"api_key": tmdb_api_key}) as response:
                        if response.status != 200: continue
                        images = await response.json()
                    backdrops = images.get("backdrops", [])
                    backdrops.sort(key=lambda x: float(x.get("vote_average") or 0), reverse=True)
                    if backdrops and backdrops[0].get("file_path"):
                        return f"https://image.tmdb.org/t/p/original{backdrops[0]['file_path']}"
            return None
    except asyncio.CancelledError:
        raise
    except Exception:
        return None


async def get_omdb_poster(movie_name, omdb_api_key):
    try:
        query = movie_name.strip()
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', query)
        year = year_match.group(1) if year_match else None
        title = re.sub(r'\s*\b(19\d{2}|20\d{2})\b\s*', ' ', query).strip()
        normalize = lambda s: re.sub(r'[^a-z0-9]', '', (s or '').lower())
        if not title:
            return None
        params = {"apikey": omdb_api_key, "t": title, "type": "movie"}
        if year:
            params["y"] = year
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get("https://www.omdbapi.com/", params=params) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                if data.get("Response") != "True":
                    return None
                if normalize(data.get("Title")) != normalize(title):
                    return None
                if year and str(data.get("Year", ""))[:4] != year:
                    return None
                poster = data.get("Poster")
                return poster if poster and poster != "N/A" else None
    except asyncio.CancelledError:
        raise
    except Exception:
        return None




async def get_any_movie_poster(movie_name):
    cached_poster = await get_cached_poster(movie_name)
    if cached_poster:
        return cached_poster

    tmdb_keys = _parse_api_keys(TMDB_API_KEYS)
    omdb_keys = _parse_api_keys(OMDB_API_KEYS)
    current_time = time.time()

    if tmdb_keys:
        valid_tmdb_keys = [k for k in tmdb_keys if k not in BAD_TMDB_KEYS or current_time - BAD_TMDB_KEYS[k] > 300]
        if valid_tmdb_keys:
            chosen_key = random.choice(valid_tmdb_keys)
            try:
                poster = await asyncio.wait_for(get_tmdb_poster(movie_name, chosen_key), timeout=3.0)
                if poster:
                    await save_poster_to_cache(movie_name, poster)
                    return poster
            except asyncio.CancelledError:
                raise
            except Exception:
                BAD_TMDB_KEYS[chosen_key] = current_time

    if omdb_keys:
        valid_omdb_keys = [k for k in omdb_keys if k not in BAD_OMDB_KEYS or current_time - BAD_OMDB_KEYS[k] > 300]
        if valid_omdb_keys:
            chosen_key = random.choice(valid_omdb_keys)
            try:
                poster = await asyncio.wait_for(get_omdb_poster(movie_name, chosen_key), timeout=3.0)
                if poster:
                    await save_poster_to_cache(movie_name, poster)
                    return poster
            except asyncio.CancelledError:
                raise
            except Exception:
                BAD_OMDB_KEYS[chosen_key] = current_time

    return None


async def check_loop_sub(client, message):
    count = 0
    while count < 15:
        check = await is_requested_one(client, message)
        check2 = await is_requested_two(client, message)
        count += 1
        if check and check2:
            return True
        await asyncio.sleep(1.5)
    return False

async def check_loop_sub1(client, message):
    count = 0
    while count < 15:
        if await is_requested_one(client, message):
            return True
        count += 1
        await asyncio.sleep(1)
    return False

async def check_loop_sub2(client, message):
    count = 0
    while count < 15:
        if await is_requested_two(client, message):
            return True
        count += 1
        await asyncio.sleep(1)
    return False

async def is_requested_one(self, message):
    user = await db.get_req_one(int(message.from_user.id))
    if user or message.from_user.id in ADMINS:
        return True
    try:
        user = await self.get_chat_member(int(REQ_CHANNEL1), message.from_user.id)
    except UserNotParticipant:
        pass
    except Exception as e:
        logger.exception(e)
    else:
        if user.status != enums.ChatMemberStatus.BANNED:
            return True
    return False
    
async def is_requested_two(self, message):
    user = await db.get_req_two(int(message.from_user.id))
    if user or message.from_user.id in ADMINS:
        return True
    try:
        user = await self.get_chat_member(int(REQ_CHANNEL2), message.from_user.id)
    except UserNotParticipant:
        pass
    except Exception as e:
        logger.exception(e)
    else:
        if user.status != enums.ChatMemberStatus.BANNED:
            return True
    return False
    
async def is_subscribed(bot, query):
    if not AUTH_CHANNEL:
        return True
    try:
        user = await bot.get_chat_member(AUTH_CHANNEL, query.from_user.id)
    except UserNotParticipant:
        pass
    except Exception as e:
        logger.exception(e)
    else:
        if user.status != enums.ChatMemberStatus.BANNED:
            return True
    return False

class _OmdbFakeMovie:
    def __init__(self, m):
        self._m = m
        self.movieID = f"omdb_{m.get('imdbID')}"
    def get(self, k, default=None):
        _map = {'title': 'Title', 'year': 'Year', 'kind': 'Type'}
        return self._m.get(_map.get(k, k), default)

class _ImdbioFakeMovie:
    def __init__(self, m):
        self._m = m
        self.movieID = f"imdbio_{m.imdb_id}"
    def get(self, k, default=None):
        if k == 'title': return self._m.title or default
        if k == 'year': return self._m.year or default
        if k == 'kind': return self._m.kind or default
        return default

def list_to_str(k, max_elm=None):
    if not k:
        return "N/A"
    limit = int(max_elm or MAX_LIST_ELM or 5)
    if len(k) > limit:
        k = k[:limit]
    return ', '.join(str(elem) for elem in k)

def _names(people):
    try:
        names = [p.name for p in people if getattr(p, "name", None)]
    except (TypeError, AttributeError):
        return "N/A"
    return list_to_str(names) if names else "N/A"

def _cat(m, key):
    try:
        return _names(m.categories.get(key, []))
    except (AttributeError, TypeError):
        return "N/A"

async def _imdbio_search(title, year=None, bulk=False):
    if not IMDBIO_AVAILABLE:
        return None
    try:
        result = await asyncio.to_thread(_imdbio.search_title, title, year=year)
    except Exception:
        return None
    if not result or not result.titles:
        return None
    if bulk:
        return [{"title": t.title, "year": str(t.year) if t.year else "N/A"} for t in result.titles[:6]]
    return await _imdbio_get_details(result.titles[0].imdb_id)

async def _imdbio_get_details(imdb_id):
    if not IMDBIO_AVAILABLE:
        return None
    if isinstance(imdb_id, str) and imdb_id.startswith("imdbio_"):
        imdb_id = imdb_id[len("imdbio_"):]
    try:
        m = await asyncio.to_thread(_imdbio.get_movie, imdb_id)
    except Exception:
        return None
    if not m:
        return None
    return {"title": m.title or "N/A", "year": str(m.year) if m.year else "N/A"}

def _hq_poster(url):
    if not url or url == "N/A":
        return None
    return re.sub(r'\._[A-Z0-9,]+_(?=\.\w+$)', '', url)

async def fetch_poster_bytes(url):
    if not url:
        return None
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.warning(f"poster download failed: {e}")
        return None

async def _omdb_search(title, year=None, bulk=False):
    omdb_keys = _parse_api_keys(OMDB_API_KEYS)
    if not omdb_keys:
        return None
    try:
        params = {"apikey": omdb_keys[0], "s": title}
        if year:
            params["y"] = year
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://omdbapi.com", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None
    if data.get("Response") != "True":
        return None
    results = data.get("Search", [])
    if not results:
        return None
    if bulk:
        return [{"title": r.get("Title"), "year": r.get("Year") or "N/A"} for r in results[:6]]
    return await _omdb_get_details(results[0]["imdbID"])

async def _omdb_get_details(imdb_id):
    omdb_keys = _parse_api_keys(OMDB_API_KEYS)
    if not omdb_keys:
        return None
    if isinstance(imdb_id, str) and imdb_id.startswith("omdb_"):
        imdb_id = imdb_id[len("omdb_"):]
    try:
        params = {"apikey": omdb_keys[0], "i": imdb_id, "plot": "short"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://omdbapi.com", params=params)
            resp.raise_for_status()
            m = resp.json()
    except Exception:
        return None
    if not m or m.get("Response") != "True":
        return None
    return {"title": m.get("Title", "N/A"), "year": m.get("Year", "N/A")}
    
async def get_poster(query, bulk=False, id=False, file=None):
    if id:
        result = await _imdbio_get_details(query)
        if result: return result
        return await _omdb_get_details(query)

    query = (query.strip()).lower()
    title = query
    year = re.findall(r'[1-2]\d{3}$', query, re.IGNORECASE)
    if year:
        year = list_to_str(year[:1])
        title = (query.replace(year, "")).strip()
    elif file is not None:
        year = re.findall(r'[1-2]\d{3}', file, re.IGNORECASE)
        if year:
            year = list_to_str(year[:1])
    else:
        year = None

    result = await _imdbio_search(title, year=year, bulk=bulk)
    if result: return result
    return await _omdb_search(title, year=year, bulk=bulk)


async def get_settings(group_id):
    settings = temp.SETTINGS.get(group_id)
    if not settings:
        settings = await db.get_settings(group_id)
        temp.SETTINGS[group_id] = settings
    return settings
    
async def save_group_settings(group_id, key, value):
    current = await get_settings(group_id)
    current[key] = value
    temp.SETTINGS[group_id] = current
    await db.update_settings(group_id, current)
    
def get_size(size):
    units = ["Bytes", "ᴷᴮ", "ᴹᴮ", "ᴳᴮ", "ᵀᴮ", "ᴾᴮ", "ᴱᴮ"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    raw_size_str = str(int(size))
    superscript_map = {
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
    }
    su_size_str = "".join(superscript_map.get(char, char) for char in raw_size_str)
    return f"{su_size_str}{units[i]}"

def get_file_id(msg: Message):
    if msg.media:
        for message_type in ("photo", "animation", "audio", "document", "video", "video_note", "voice", "sticker"):
            obj = getattr(msg, message_type)
            if obj:
                setattr(obj, "message_type", message_type)
                return obj

def extract_user(message: Message) -> Union[int, str]:
    user_id = None
    user_first_name = None
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_first_name = message.reply_to_message.from_user.first_name
    elif len(message.command) > 1:
        if len(message.entities) > 1 and message.entities[1].type == enums.MessageEntityType.TEXT_MENTION:
            required_entity = message.entities[1]
            user_id = required_entity.user.id
            user_first_name = required_entity.user.first_name
        else:
            user_id = message.command[1]
            user_first_name = user_id
        try:
            user_id = int(user_id)
        except ValueError:
            pass
    else:
        user_id = message.from_user.id
        user_first_name = message.from_user.first_name
    return (user_id, user_first_name)

def last_online(from_user):
    time_str = ""
    if from_user.is_bot:
        time_str += "🤖 Bot :("
    elif from_user.status == enums.UserStatus.RECENTLY:
        time_str += "Recently"
    elif from_user.status == enums.UserStatus.LAST_WEEK:
        time_str += "Within the last week"
    elif from_user.status == enums.UserStatus.LAST_MONTH:
        time_str += "Within the last month"
    elif from_user.status == enums.UserStatus.LONG_AGO:
        time_str += "A long time ago :("
    elif from_user.status == enums.UserStatus.ONLINE:
        time_str += "Currently Online"
    elif from_user.status == enums.UserStatus.OFFLINE:
        time_str += from_user.last_online_date.strftime("%a, %d %b %Y, %H:%M:%S")
    return time_str



def remove_escapes(text: str) -> str:
    res = ""
    is_escaped = False
    for counter in range(len(text)):
        if is_escaped:
            res += text[counter]
            is_escaped = False
        elif text[counter] == "\\":
            is_escaped = True
        else:
            res += text[counter]
    return res

def split_quotes(text: str) -> List:
    if not any(text.startswith(char) for char in START_CHAR):
        return text.split(None, 1)
    counter = 1
    while counter < len(text):
        if text[counter] == "\\":
            counter += 1
        elif text[counter] == text[0] or (text[0] == SMART_OPEN and text[counter] == SMART_CLOSE):
            break
        counter += 1
    else:
        return text.split(None, 1)
    key = remove_escapes(text[1:counter].strip())
    rest = text[counter + 1:].strip()
    if not key:
        key = text[0] + text[0]
    return list(filter(None, [key, rest]))

def gfilterparser(text, keyword):
    if "buttonalert" in text:
        text = (text.replace("\n", "\\n").replace("\t", "\\t"))
    buttons = []
    note_data = ""
    prev = 0
    i = 0
    alerts = []
    for match in BTN_URL_REGEX.finditer(text):
        n_escapes = 0
        to_check = match.start(1) - 1
        while to_check > 0 and text[to_check] == "\\":
            n_escapes += 1
            to_check -= 1
        if n_escapes % 2 == 0:
            note_data += text[prev:match.start(1)]
            prev = match.end(1)
            if match.group(3) == "buttonalert":
                if bool(match.group(5)) and buttons:
                    buttons[-1].append(InlineKeyboardButton(text=match.group(2), callback_data=f"gfilteralert:{i}:{keyword}"))
                else:
                    buttons.append([InlineKeyboardButton(text=match.group(2), callback_data=f"gfilteralert:{i}:{keyword}")])
                i += 1
                alerts.append(match.group(4))
            elif bool(match.group(5)) and buttons:
                buttons[-1].append(InlineKeyboardButton(text=match.group(2), url=match.group(4).replace(" ", "")))
            else:
                # Fixed: Corrected the final boundary from ))) to )]) to satisfy the syntax compiler
                buttons.append([InlineKeyboardButton(text=match.group(2), url=match.group(4).replace(" ", ""))])
        else:
            note_data += text[prev:to_check]
            prev = match.start(1) - 1
    note_data += text[prev:]
    return note_data, buttons, alerts if alerts else None

def parser(text, keyword):
    if "buttonalert" in text:
        text = (text.replace("\n", "\\n").replace("\t", "\\t"))
    buttons = []
    note_data = ""
    prev = 0
    i = 0
    alerts = []
    for match in BTN_URL_REGEX.finditer(text):
        n_escapes = 0
        to_check = match.start(1) - 1
        while to_check > 0 and text[to_check] == "\\":
            n_escapes += 1
            to_check -= 1
        if n_escapes % 2 == 0:
            note_data += text[prev:match.start(1)]
            prev = match.end(1)
            if match.group(3) == "buttonalert":
                if bool(match.group(5)) and buttons:
                    buttons[-1].append(InlineKeyboardButton(text=match.group(2), callback_data=f"alertmessage:{i}:{keyword}"))
                else:
                    buttons.append([InlineKeyboardButton(text=match.group(2), callback_data=f"alertmessage:{i}:{keyword}")])
                i += 1
                alerts.append(match.group(4))
            elif bool(match.group(5)) and buttons:
                buttons[-1].append(InlineKeyboardButton(text=match.group(2), url=match.group(4).replace(" ", "")))
            else:
                # Fixed: Corrected the mirrored bracket mapping layout typo here as well
                buttons.append([InlineKeyboardButton(text=match.group(2), url=match.group(4).replace(" ", ""))])
        else:
            note_data += text[prev:to_check]
            prev = match.start(1) - 1
    note_data += text[prev:]
    return note_data, buttons, alerts if alerts else None


def humanbytes(size):
    if not size: return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

def get_progress_bar(completed, total, length=10):
    progress = completed / total
    block = int(round(length * progress))
    text = "🟩" * block + "⬜" * (length - block)
    percentage = round(progress * 100, 1)
    return f"[{text}] {percentage}%"

async def broadcast_messages(user_id, message):
    try:
        await message.copy(chat_id=user_id)
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.x)
        return await broadcast_messages(user_id, message)
    except InputUserDeactivated:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id}-Removed from Database (deleted account).")
        return False, "Deleted"
    except UserIsBlocked:
        logging.info(f"{user_id}-Blocked the bot.")
        return False, "Blocked"
    except PeerIdInvalid:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id}-PeerIdInvalid error.")
        return False, "Error"
    except Exception:
        return False, "Error"

async def run_broadcast_in_background(client, message, status_msg):
    start_time = time.time()
    success, blocked, deleted, failed = 0, 0, 0, 0

    all_users_cursor = await db.get_all_users()
    total_users = await db.total_users_count()
    
    if total_users == 0:
        await status_msg.edit("❌ ഡാറ്റാബേസിൽ യൂസർമാർ ആരും തന്നെയില്ല!")
        return

    processed = 0
    async for user in all_users_cursor:
        user_id = user.get('id')
        if not user_id:
            continue
            
        is_sent, result = await broadcast_messages(int(user_id), message)
        
        if is_sent: success += 1
        elif result == "Blocked": blocked += 1
        elif result == "Deleted": deleted += 1
        else: failed += 1
            
        processed += 1
        
        if processed % 10 == 0 or processed == total_users:
            bar = get_progress_bar(processed, total_users)
            progress_text = (
                f"📢 **ബ്രോഡ്കാസ്റ്റിംഗ് പുരോഗമിക്കുന്നു...**\n\n"
                f"📊 Progress: {bar}\n"
                f"⏳ അയച്ചത്: {processed} / {total_users}\n\n"
                f"👍 വിജയിച്ചത്: {success}\n"
                f"🚫 ബ്ലോക്ക് ചെയ്തവർ: {blocked}\n"
                f"💀 ഡിലീറ്റ് ആയവർ: {deleted}"
            )
            try:
                await status_msg.edit(progress_text)
            except Exception:
                pass
        await asyncio.sleep(0.5)

    end_time = time.time()
    time_taken = round(end_time - start_time, 2)
    final_text = (
        f"✅ **ബ്രോഡ്കാസ്റ്റ് വിജയകരമായി പൂർത്തിയായി!**\n\n"
        f"⏱️ എടുത്ത സമയം: {time_taken} സെക്കന്റ്\n"
        f"👥 ആകെ യൂസർമാർ: {total_users}\n\n"
        f"👍 വിജയിച്ചത്: {success}\n"
        f"🚫 ബ്ലോക്ക് ചെയ്തവർ: {blocked}\n"
        f"💀 അക്കൗണ്ട് ഡിലീറ്റ് ആയവർ: {deleted}\n"
        f"❌ പരാജയപ്പെട്ടത്: {failed}"
    )
    try:
        await status_msg.edit(final_text)
    except Exception:
        pass
