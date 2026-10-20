import asyncio
lock = asyncio.Lock()
import re
import ast
import random
import math
import ast  # eval-ന് പകരം സുരക്ഷിതമായി സ്ട്രിങ് ലിസ്റ്റ് ആക്കാൻ
import emoji  # ഇമോജികൾ നീക്കം ചെയ്യാൻ
from pyrogram.errors.exceptions.bad_request_400 import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty
from pyrogram.errors import FloodWait, UserIsBlocked, MessageNotModified, PeerIdInvalid, QueryIdInvalid, MessageIdInvalid
from Script import script
import pyrogram
from database.connections_mdb import active_connection, all_connections, delete_connection, if_active, make_active, \
    make_inactive

from database.filters_mdb import (
    del_all,
    find_filter,
    get_filters,
)
from database.filters_mdb import del_all

# 🚀 സ്റ്റാറ്റ്സ് പാനലിൽ പേര് കൃത്യമായി വരാൻ DATABASE_NAME കൂടി ഇമ്പോർട്ട് ചെയ്യുന്നു ✨
from info import ADMINS, REQ_CHANNEL1, REQ_CHANNEL2, AUTH_USERS, CUSTOM_FILE_CAPTION, AUTH_GROUPS, P_TTI_SHOW_OFF, SINGLE_BUTTON, SPELL_CHECK_REPLY, LOG_CHANNEL, SPELL_IMG, DATABASE_NAME, YEAR_IMG
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram import Client, filters, enums
from utils import get_size, is_subscribed, temp, get_settings, save_group_settings, is_requested_one, is_requested_two, get_any_movie_poster, get_poster
from database.users_chats_db import db
# Mediaa, clientDB3 എന്നിവ ഒഴിവാക്കി
# 🚀 ia_filterdb-ൽ നിന്ന് db1 (clientDB2) ഒഴിവാക്കി മെയിൻ db (clientDB) മാത്രം ഇമ്പോർട്ട് ചെയ്യുന്നു ✨
from database.ia_filterdb import Media, get_bad_files, get_file_details, get_search_results, db as clientDB
from database.filters_mdb import (
    del_all,
    find_filter,
    get_filters,
)
from database.gfilters_mdb import find_gfilter, get_gfilters
import logging
from database.requests_db import save_missing_movie, get_all_missing_movies
import io
from urllib.parse import quote_plus
import time
from info import IMG
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


def _trim_dict(d: dict, max_size: int = 100):
    """5 മിനിറ്റിൽ കൂടുതൽ പഴക്കമുള്ളതോ അല്ലെങ്കിൽ ലിസ്റ്റ് ഫുൾ ആകുമ്പോഴോ ഉള്ള ഡാറ്റ നീക്കം ചെയ്യും"""
    current_time = time.time()
    
    # 1. ആദ്യം 5 മിനിറ്റിൽ (300 സെക്കൻഡ്) കൂടുതൽ പഴക്കമുള്ള എല്ലാ കീകളും ഡിലീറ്റ് ചെയ്യും
    expired_keys = [k for k, v in d.items() if (current_time - v.get('time', 0)) > 240]
    for k in expired_keys:
        d.pop(k, None)
        
    # 2. എന്നിട്ടും ലിസ്റ്റ് 100-ൽ കൂടുതൽ ആണെങ്കിൽ പഴയ 20% ഡാറ്റ കളയും
    if len(d) > max_size:
        keys_to_remove = list(d.keys())[:len(d) // 5]
        for k in keys_to_remove:
            d.pop(k, None)

            

BUTTONS = {}


# ഗ്രൂപ്പുകളിൽ ബോട്ട് അഡ്മിൻ അല്ലെങ്കിലും വരുന്ന ടെക്സ്റ്റ് മെസ്സേജുകൾ എടുക്കാൻ filters.group കൂടി ചേർക്കുന്നു
@Client.on_message(filters.group & filters.text & filters.incoming)
async def give_filters(client, message):
    k = await global_filters(client, message)    
    if k == False:
        await auto_filter(client, message)



# 2. "📢 Coming Soon" ബട്ടൺ ക്ലിക്ക് ചെയ്യുമ്പോൾ ഉള്ള അലേർട്ട്
@Client.on_callback_query(filters.regex("^alert_channel$"))
async def channel_alert_handler(bot, query):
    await query.answer("OTT FILE NOT AVAILABLE", show_alert=True)

# 3. "🫴 OTT വന്നിട്ടില്ല" ബട്ടൺ ക്ലിക്ക് ചെയ്യുമ്പോൾ ഉള്ള അലേർട്ട്
@Client.on_callback_query(filters.regex("^alert_google$"))
async def google_alert_handler(bot, query):
    await query.answer("OTT ഇറങ്ങുന്നേ വരെ ക്ഷമിക്ക് അളിയാ", show_alert=True)



@Client.on_message(filters.private & (filters.text | filters.photo | filters.video | filters.sticker) & filters.incoming)
async def pm_text(bot: Client, message):
    user_id = message.from_user.id
    user = message.from_user.first_name or "User"

    if message.text and (message.text.startswith("/") or message.text.startswith("#")): return
    if user_id in ADMINS: return

    # 1. ടെക്സ്റ്റ് മെസ്സേജ് ഉണ്ടോ എന്ന് ഉറപ്പുവരുത്തുന്നു
    if not message.text:
        return

    text_to_check = message.text.strip()

    # 2. ⚡ [ആദ്യ ഘട്ടം] ഫോർമാറ്റ് പരിശോധന (Format Validation)
    # മെസ്സേജിന്റെ അവസാനം വർഷം (eg: 2024) ഇല്ലെങ്കിൽ ഡാറ്റാബേസ് സെർച്ച് ചെയ്യാതെ നേരിട്ട് Wrong Format മെസ്സേജ് അയക്കും
    if not re.search(r'\b(19\d{2}|20[0-2]\d)\b$', text_to_check):
        user_data = await db.col.find_one({'id': int(user_id)}) if hasattr(db, "col") else None
        is_muted = user_data.get('is_muted', False) if user_data else False
        warning_sent = user_data.get('warning_sent', False) if user_data else False

        if is_muted:
            if not warning_sent:
                await db.col.update_one({'id': user_id}, {'$set': {'warning_sent': True}})
                await bot.send_chat_action(chat_id=message.chat.id, action=enums.ChatAction.TYPING)
                await message.reply_text(
                    text=f"<b>⚠️ ശ്രദ്ധിക്കുക / WARNING!\n\nനിങ്ങൾ ബോട്ടിന്റെ നിയമങ്ങൾ (Rules) ലംഘിച്ചതിനാൽ അഡ്മിൻ നിങ്ങളെ മ്യൂട്ട് ചെയ്തിരിക്കുകയാണ്.\n\നിയമങ്ങൾ വ്യക്തമായി വായിക്കാൻ താഴെയുള്ള rules ബട്ടൺ ക്ലിക്ക് ചെയ്യുക.Mute ഒഴിവാക്കാൻ അഡ്മിനെ സമീപിക്കുക @Chithralokham",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚸 READ RULES 🚸", url="https://t.me/Chithralokham/7")]])
                )
            return
            
        await bot.send_chat_action(chat_id=message.chat.id, action=enums.ChatAction.TYPING)
        await asyncio.sleep(0.5)
        await message.reply_text(
            text=f"<b>❌ Wrong Format / തെറ്റായ ഫോർമാറ്റ്!\n\nPlease send your request in this format:\n<code>Movie Name + Year</code>\n\nExample:\n<code>Kuruthi 2021</code>\n\n💡 സിനിമയുടെ പേരിനൊപ്പം വർഷം കൂടി ടൈപ്പ് ചെയ്ത് അയക്കുക.</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚸 MUST READ 🚸", url="https://t.me/Chithralokham/7")]])
        )
        return

    # 3. ⚡ [രണ്ടാം ഘട്ടം] മ്യൂട്ട് പരിശോധന
    user_data = await db.col.find_one({'id': int(user_id)}) if hasattr(db, "col") else None
    is_muted = user_data.get('is_muted', False) if user_data else False
    warning_sent = user_data.get('warning_sent', False) if user_data else False

    # 4. ⚡ [മൂന്നാം ഘട്ടം] ഡാറ്റാബേസ് സെർച്ചിംഗ് (ശരിയായ ഫോർമാറ്റിൽ ഉള്ളവ മാത്രം ഇവിടെ എത്തും)
    files_found = False
    files = []
    search_query = text_to_check
    files, offset, total_results = await get_search_results(search_query.lower(), offset=0, filter=True)

    # 5. ഫയൽ കണ്ടെത്തിയാൽ ബട്ടണുകൾ നൽകുന്നു
    if files:
        files_found = True
        await bot.send_chat_action(chat_id=message.chat.id, action=enums.ChatAction.TYPING)
                
        key = f"{message.chat.id}-{message.id}"
        _trim_dict(BUTTONS) 
        BUTTONS[key] = {"query": search_query, "total": total_results, "time": time.time()}
        
        btn = []
        for file in files[:10]:
            btn.append([InlineKeyboardButton(text=f"{get_size(file.file_size)}➪{file.file_name}", url=f"https://t.me/{temp.U_NAME}?start={pre}_{file.file_id}")])

        if total_results > 10:
            btn.append([InlineKeyboardButton(text=f"   𝟷 / {math.ceil(int(total_results) / 10)}", callback_data="pages"), InlineKeyboardButton(text="ɴᴇxᴛ", callback_data=f"next_{user_id}_{key}_10")])

        year_match = re.findall(r'\b(19\d{2}|20[0-2]\d)\b', search_query)
        combined_file_names = ""
        print_check_text = ""
        languages_found = []

        lang_map = {
            'malayalam': 'Malayalam', 'mal': 'Malayalam', 'tamil': 'Tamil', 'tam': 'Tamil',
            'telugu': 'Telugu', 'tel': 'Telugu', 'hindi': 'Hindi', 'hin': 'Hindi',
            'english': 'English', 'eng': 'English', 'kannada': 'Kannada', 'kan': 'Kannada',
            'marathi': 'Marathi', 'mar': 'Marathi', 'bengali': 'Bengali', 'ben': 'Bengali',
            'odia': 'Odia', 'ori': 'Odia', 'multi': 'Multi_Audio', 'audio': 'Multi_Audio', 'dual': 'Multi_Audio'
        }
        
        if files and isinstance(files, list):
            for index, file in enumerate(files[:5]):
                if hasattr(file, 'file_name') and file.file_name:
                    f_name_lower = file.file_name.lower()
                    combined_file_names += " " + f_name_lower
                    file_words = set(re.findall(r'\b\w+\b', f_name_lower))
                    for word in file_words:
                        if word in lang_map and lang_map[word] not in languages_found:
                            languages_found.append(lang_map[word])
                            
            if hasattr(files[0], 'file_name') and files[0].file_name:
                print_check_text = files[0].file_name.lower()

        search_words = set(re.findall(r'\b\w+\b', search_query.lower()))
        for word in search_words:
            if word in lang_map and lang_map[word] not in languages_found:
                languages_found.append(lang_map[word])

        if not year_match and files and hasattr(files[0], 'file_name') and files[0].file_name:
            found_years = re.findall(r'\b(19\d{2}|20[0-2]\d)\b', files[0].file_name)
            if found_years:
                year_match = [found_years[0]]
        
        detected_year = year_match[0] if year_match else ""
        movie_year = f" ({detected_year})" if detected_year else ""
        
        detected_print = "HD_Original" 
        if print_check_text:
            if re.search(r'\b(predvd|pre-dvd|dvdscr|hallprint|camrip|cam|hdcam|hall-print|s-print|HDTC)\b', print_check_text):
                detected_print = "Theater_Print_⚠️"

        detected_lang = ", ".join(languages_found) if languages_found else "#Unknown"
        files_count = total_results
        clean_title = re.sub(r'\b(19\d{2}|20[0-2]\d)\b', '', search_query).strip().upper()

        pm_cap = (
            f"<b><i>🎬ᴍᴏᴠɪᴇs ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n\n"
            f"➤ꜰɪʟᴍ : {clean_title}{movie_year}\n"
            f"➤ʟᴀɴɢᴜᴀɢＥ : {detected_lang}\n"
            f"➤ᴘʀɪɴᴛ ᴛʏᴘＥ : {detected_print}\n"
            f"➤ᴛᴏᴛᴀʟ ꜰɪʟＥs : {files_count}\n\n"
            f"© can_Urvashi Theaters™️</i></b>"
        )

        import random
        poster_url = random.choice(IMG) if ( 'IMG' in globals() and IMG ) else None

        try:
            if poster_url:
                await message.reply_photo(photo=poster_url, caption=pm_cap, reply_markup=InlineKeyboardMarkup(btn))
            else:
                await message.reply_text(text=pm_cap, reply_markup=InlineKeyboardMarkup(btn))
        except Exception:
            try:
                await message.reply_text(text=pm_cap, reply_markup=InlineKeyboardMarkup(btn))
            except Exception:
                pass
        return

    # 6. ⚡ [നാലാം ഘട്ടം] ഫോർമാറ്റ് കറക്റ്റാണ് പക്ഷെ ഫയൽ ഇല്ലെങ്കിൽ (റിക്വസ്റ്റ് സബ്മിറ്റ് ചെയ്യുന്നു)
    if not files_found:
        if is_muted:
            if not warning_sent:
                await db.col.update_one({'id': user_id}, {'$set': {'warning_sent': True}})
                await bot.send_chat_action(chat_id=message.chat.id, action=enums.ChatAction.TYPING)
                await message.reply_text(
                    text=f"<b>⚠️ റിക്വസ്റ്റ് നിരസിച്ചു!\n\nനിങ്ങളെ അഡ്മിൻ മ്യൂട്ട് ചെയ്തിരിക്കുന്നതിനാൽ പുതിയ റിക്വസ്റ്റുകൾ സബ്മിറ്റ് ചെയ്യാൻ സാധിക്കില്ല. Mute ഒഴിവാക്കാൻ അഡ്മിനെ സമീപിക്കുക @Chithralokham/3"
                )
            return
            
        await bot.send_chat_action(chat_id=message.chat.id, action=enums.ChatAction.TYPING)
        await asyncio.sleep(0.5)

        await message.reply_text(
            text="<b>Your Request Has Been Submitted✅\n\nOTT Available Add Files With In 24Hrs.. Please Wait\n\nനിങ്ങളുടെ request അഡ്മിൻ അയച്ചിട്ടുണ്ട് ഫയൽസ് ഉണ്ടെങ്കിൽ 24മണിക്കൂറിനുള്ളിൽ ആഡ് ചെയ്യുന്നതാണ്</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 ANY ERROR REPORT 🚫 ", url="https://t.me/Chithralokham/3")],
                [InlineKeyboardButton("🚸 MUST READ 🚸", url="http://telegra.ph/Request-%E0%B4%85%E0%B4%AF%E0%B4%95%E0%B4%95-%E0%B4%AE%E0%B4%A8%E0%B4%A8-%E0%B4%B5%E0%B4%AF%E0%B4%95%E0%B4%95%E0%B4%A3%E0%B4%9F%E0%B4%A8%E0%B4%A8%E0%B4%A4-08-19")]
            ])
        )

        log_reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 MESSAGE USER (DIRECT)", url=f"tg://user?id={user_id}")],
            [InlineKeyboardButton("🔇 MUTE USER", callback_data=f"dbmute_{user_id}")]
        ])
        log_text = f"<b>#PM_MSG\n\nNᴀᴍE : <a href='tg://user?id={user_id}'>{user}</a>\n\nID : <code>{user_id}</code>\n\nMᴇssᴀɢE :</b> <code>{text_to_check}</code>\n\n#id{user_id}"

        try:
            await bot.send_chat_action(chat_id=LOG_CHANNEL, action=enums.ChatAction.TYPING)
            await bot.send_message(chat_id=LOG_CHANNEL, text=log_text, reply_markup=log_reply_markup, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Error sending log to LOG_CHANNEL: {e}")

           


@Client.on_callback_query(filters.regex(r"^dbmute_") | filters.regex(r"^dbunmute_"))
async def db_mute_unmute_handler(bot, query):
    if query.from_user.id not in ADMINS:
        return await query.answer("❌ അഡ്മിന്മാർക്ക് മാത്രമേ ഈ ബട്ടൺ ഉപയോഗിക്കാൻ കഴിയൂ!", show_alert=True)
        
    action, user_id_str = query.data.split("_", 1)
    target_user_id = int(user_id_str)
    
    current_markup = query.message.reply_markup
    new_buttons = []
    
    if action == "dbmute":
        if hasattr(db, "col"):
            await db.col.update_one({'id': target_user_id}, {'$set': {'is_muted': True, 'warning_sent': False}}, upsert=True)
        
        await query.answer("🔇 യൂസറെ ഡാറ്റാബേസിൽ മ്യൂട്ട് ചെയ്തു!", show_alert=True)
        
        for row in current_markup.inline_keyboard:
            new_row = []
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("dbmute_"):
                    new_row.append(InlineKeyboardButton("🔊 UNMUTE USER", callback_data=f"dbunmute_{target_user_id}"))
                else:
                    new_row.append(btn)
            new_buttons.append(new_row)
            
    elif action == "dbunmute":
        if hasattr(db, "col"):
            # അൺമ്യൂട്ട് ചെയ്യുമ്പോൾ രണ്ട് ഫീൽഡുകളും false ആക്കുന്നു
            await db.col.update_one({'id': target_user_id}, {'$set': {'is_muted': False, 'warning_sent': False}}, upsert=True)
            
        await query.answer("🔊 യൂസറെ അൺമ്യൂട്ട് ചെയ്തു!", show_alert=True)
        
        for row in current_markup.inline_keyboard:
            new_row = []
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("dbunmute_"):
                    new_row.append(InlineKeyboardButton("🔇 MUTE USER", callback_data=f"dbmute_{target_user_id}"))
                else:
                    new_row.append(btn)
            new_buttons.append(new_row)
            
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_buttons))
    except Exception as e:
        logger.error(f"Error updating database mute markup: {e}")



@Client.on_message(filters.chat(LOG_CHANNEL) & filters.reply)
async def admin_reply_to_user(bot: Client, message):
    parent_message = message.reply_to_message
    parent_text = parent_message.text or parent_message.caption
    if not parent_text: return

    match = re.search(r"#id(\d+)", parent_text)
    if match:
        user_id = int(match.group(1))
        reply_caption = f"<b>{message.caption}</b>" if message.caption else ""

        try:
            if message.photo:
                await bot.send_chat_action(chat_id=user_id, action=enums.ChatAction.UPLOAD_PHOTO)
                await bot.send_photo(chat_id=user_id, photo=message.photo.file_id, caption=reply_caption)
            elif message.video:
                await bot.send_chat_action(chat_id=user_id, action=enums.ChatAction.UPLOAD_VIDEO)
                await bot.send_video(chat_id=user_id, video=message.video.file_id, caption=reply_caption)
            elif message.sticker:
                await bot.send_sticker(chat_id=user_id, sticker=message.sticker.file_id)
            elif message.text:
                await bot.send_chat_action(chat_id=user_id, action=enums.ChatAction.TYPING)
                await bot.send_message(chat_id=user_id, text=f"<b>💬 Message From Admin:\n\n{message.text}</b>")
            else:
                return

            await message.reply_text("<b>✅ മറുപടി യൂസർക്ക് വിജയകരമായി അയച്ചു!</b>")

        except UserIsBlocked:
            await message.reply_text("<b>❌ മറുപടി അയക്കാൻ കഴിഞ്ഞില്ല! ഈ യൂസർ ബോട്ടിനെ ബ്ലോക്ക് ചെയ്തിരിക്കുകയാണ്.</b>")
        except PeerIdInvalid:
            await message.reply_text("<b>❌ ഈ യൂസറുമായി ബോട്ട് ഇതുവരെ ചാറ്റ് തുടങ്ങിയിട്ടില്ല (Peer ID Invalid).</b>")
        except Exception as e:
            logger.error(f"Admin reply forward error: {e}")
            await message.reply_text(f"<b>❌ മെസ്സേജ് അയക്കാൻ കഴിഞ്ഞില്ല!\nError: {e}</b>")



@Client.on_callback_query(filters.regex(r"^next"))
async def next_page(bot, query):
    try:
        ident, req, key, offset = query.data.split("_", 3)
    except ValueError:
        return await query.answer("❌ Navigation error. Please search again.", show_alert=True)

    if int(req) not in [query.from_user.id, 0]:
        return await query.answer("Search for Yourself", show_alert=True)

    try:
        offset = int(offset)
    except ValueError:
        offset = 0

    button_data = BUTTONS.get(key)
    if not button_data or not isinstance(button_data, dict):
        return await query.answer("Expired. Please search again 🚫", show_alert=True)

    search = button_data.get("query")
    if not search:
        return await query.answer("Please search again.", show_alert=True)

    db_search = search
    if " [" in search:
        base = search.split(" [")[0]
        tags = search.split(" [")[1].replace("]", "").split(" + ")
        db_search = f"{base} {' '.join(tags)}"

    cached_total = button_data.get("total")
    files, n_offset, total = await get_search_results(
        db_search.lower(), offset=offset, filter=True, total_results=cached_total
    )

    if not files:
        return await query.answer("No files", show_alert=True)

    settings = await get_settings(query.message.chat.id)
    pre = "filep" if settings.get("file_secure", False) else "file"
    btn = []

    for file in files:
        url = f"https://t.me/{temp.U_NAME}?start={pre}_{file.file_id}"
        if settings.get("button", False):
            btn.append([InlineKeyboardButton(
                text=f"{get_size(file.file_size)}➪{file.file_name}", url=url
            )])
        else:
            btn.append([
                InlineKeyboardButton(text=file.file_name, url=url),
                InlineKeyboardButton(text=get_size(file.file_size), url=url)
            ])

    if 0 < offset < 10:
        off_set = 0
    elif offset == 0:
        off_set = None
    else:
        off_set = offset - 10

    page = math.ceil(offset / 10) + 1
    total_pages = math.ceil(total / 10)

    if n_offset == "":
        btn.append([
            InlineKeyboardButton("Back", callback_data=f"next_{req}_{key}_{off_set}"),
            InlineKeyboardButton(f"{page} / {total_pages}", callback_data="pages")
        ])
    elif off_set is None:
        btn.append([
            InlineKeyboardButton(f"{page} / {total_pages}", callback_data="pages"),
            InlineKeyboardButton("Next", callback_data=f"next_{req}_{key}_{n_offset}")
        ])
    else:
        btn.append([
            InlineKeyboardButton("Back", callback_data=f"next_{req}_{key}_{off_set}"),
            InlineKeyboardButton(f"{page} / {total_pages}", callback_data="pages"),
            InlineKeyboardButton("Next", callback_data=f"next_{req}_{key}_{n_offset}")
        ])    

    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
        await query.answer()
    except MessageNotModified:
        await query.answer()
    except MessageIdInvalid:
        await query.answer("Expired 🚫 Search Again", show_alert=True)
    except FloodWait as e:
        await query.answer(f"Please wait {e.value} seconds.", show_alert=True)


@Client.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    if query.data == "close_data":
        await query.message.delete()                
    
    elif query.data == "delallconfirm":
        userid = query.from_user.id
        
        # 🔐 അഡ്മിൻ സുരക്ഷാ ചെക്ക്
        if userid not in ADMINS:
            return await query.answer("You need to be a Bot Admin to do that!", show_alert=True)

        await query.answer("Deleting all filters...", show_alert=False)
        
        # 🟢 🛠️ തിരുത്തിയ ഭാഗം: ഗ്രൂപ്പ് ഐഡിക്ക് പകരം 'universal_manual_filters' നൽകി ഫിൽട്ടറുകൾ കളയുന്നു
        success = await del_all('universal_manual_filters')
        
        if success:
            await query.message.edit_text("🗑 **ബോട്ടിലെ മുഴുവൻ Universal ഫിൽട്ടറുകളും വിജയകരമായി ഡിലീറ്റ് ചെയ്തു!**")
        else:
            await query.message.edit_text("❌ **ഡാറ്റാബേസിൽ ഡിലീറ്റ് ചെയ്യാൻ ഫിൽട്ടറുകൾ ഒന്നും തന്നെയില്ല!**")       
            
    elif query.data == "delallcancel":
        userid = query.from_user.id
        chat_type = query.message.chat.type

        if chat_type == enums.ChatType.PRIVATE:
            await query.message.reply_to_message.delete()
            await query.message.delete()

        elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
            grp_id = query.message.chat.id
            st = await client.get_chat_member(grp_id, userid)
            if (st.status == enums.ChatMemberStatus.OWNER) or (str(userid) in ADMINS):
                await query.message.delete()
                try:
                    await query.message.reply_to_message.delete()
                except:
                    pass
            else:
                await query.answer("That's not for you!!", show_alert=True)
                
    elif "groupcb" in query.data:
        await query.answer()

        group_id = query.data.split(":")[1]

        act = query.data.split(":")[2]
        hr = await client.get_chat(int(group_id))
        title = hr.title
        user_id = query.from_user.id

        if act == "":
            stat = "CONNECT"
            cb = "connectcb"
        else:
            stat = "DISCONNECT"
            cb = "disconnect"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{stat}", callback_data=f"{cb}:{group_id}"),
             InlineKeyboardButton("DELETE", callback_data=f"deletecb:{group_id}")],
            [InlineKeyboardButton("BACK", callback_data="backcb")]
        ])

        await query.message.edit_text(
            f"Group Name : **{title}**\nGroup ID : `{group_id}`",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return await query.answer('Piracy Is Crime')
        
    elif "connectcb" in query.data:
        await query.answer()

        group_id = query.data.split(":")[1]

        hr = await client.get_chat(int(group_id))

        title = hr.title

        user_id = query.from_user.id

        mkact = await make_active(str(user_id), str(group_id))

        if mkact:
            await query.message.edit_text(
                f"Connected to **{title}**",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        else:
            await query.message.edit_text('Some error occurred!!', parse_mode=enums.ParseMode.MARKDOWN)
        return await query.answer('Piracy Is Crime')
        
    elif "disconnect" in query.data:
        await query.answer()

        group_id = query.data.split(":")[1]

        hr = await client.get_chat(int(group_id))

        title = hr.title
        user_id = query.from_user.id

        mkinact = await make_inactive(str(user_id))

        if mkinact:
            await query.message.edit_text(
                f"Disconnected from **{title}**",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        else:
            await query.message.edit_text(
                f"Some error occurred!!",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        return await query.answer('Piracy Is Crime')
        
    elif "deletecb" in query.data:
        await query.answer()

        user_id = query.from_user.id
        group_id = query.data.split(":")[1]

        delcon = await delete_connection(str(user_id), str(group_id))

        if delcon:
            await query.message.edit_text(
                "Successfully deleted connection"
            )
        else:
            await query.message.edit_text(
                f"Some error occurred!!",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        return await query.answer('Piracy Is Crime')
        
    elif query.data == "backcb":
        await query.answer()

        userid = query.from_user.id

        groupids = await all_connections(str(userid))
        if groupids is None:
            await query.message.edit_text(
                "There are no active connections!! Connect to some groups first.",
            )
            return await query.answer('Piracy Is Crime')
        buttons = []
        for groupid in groupids:
            try:
                ttl = await client.get_chat(int(groupid))
                title = ttl.title
                active = await if_active(str(userid), str(groupid))
                act = " - ACTIVE" if active else ""
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=f"{title}{act}", callback_data=f"groupcb:{groupid}:{act}"
                        )
                    ]
                )
            except:
                pass
        if buttons:
            await query.message.edit_text(
                "Your connected group details ;\n\n",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
    elif "alertmessage" in query.data:
        grp_id = query.message.chat.id
        i = query.data.split(":")[1]
        keyword = query.data.split(":")[2]
        reply_text, btn, alerts, fileid = await find_filter(grp_id, keyword)
        if alerts is not None:
            alerts = ast.literal_eval(alerts)
            alert = alerts[int(i)]
            alert = alert.replace("\\n", "\n").replace("\\t", "\t")
            await query.answer(alert, show_alert=True)        
        
            
    if query.data.startswith("file"):
        ident, file_id = query.data.split("#")
        files_ = await get_file_details(file_id)
        if not files_:
            return await query.answer('No such file exist.')
        files = files_[0]
        title = files.file_name
        size = get_size(files.file_size)
        f_caption = files.file_name
        
        # ⬇️ എറർ വരാതിരിക്കാൻ ഈ 2 വരികൾ പകരം ചേർക്കുക ⬇️
        chat_id = query.message.chat.id if (query.message and query.message.chat) else query.from_user.id
        settings = await get_settings(chat_id)
        if CUSTOM_FILE_CAPTION:
            try:
                f_caption=CUSTOM_FILE_CAPTION.format(file_name= '' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption, mention=query.from_user.mention)
            except Exception as e:
                logger.exception(e)
            f_caption = f_caption
        if f_caption is None:
            f_caption = f"{title}"
            
        # ബട്ടണുകൾ ഉണ്ടായിരുന്ന ഭാഗം ഒഴിവാക്കി നേരിട്ട് PM-ലേക്ക് റീഡയറക്ട് ചെയ്യുന്നു
        try:
            if settings['botpm']:
                await query.answer(url=f"https://t.me/{temp.U_NAME}?start={ident}_{file_id}")
                return
            else:
                await query.answer(url=f"https://t.me/{temp.U_NAME}?start={ident}_{file_id}")
                return
        except QueryIdInvalid:
            await query.answer("This query is no longer valid.", show_alert=True)
        except UserIsBlocked:
            await query.answer('Unblock the bot mahn !', show_alert=True)
        except PeerIdInvalid:
            await query.answer(url=f"https://t.me/{temp.U_NAME}?start={ident}_{file_id}")
        except Exception as e:
            await query.answer(url=f"https://t.me/{temp.U_NAME}?start={ident}_{file_id}")
            
    
            
                    
    elif query.data == "pages":
        await query.answer()

    
    elif query.data == "bot_commands":
        # 🔐 അഡ്മിൻ സുരക്ഷാ ചെക്ക് (അഡ്മിന്മാർക്ക് മാത്രമേ കാണാൻ സാധിക്കൂ)
        if query.from_user.id not in ADMINS:
            return await query.answer("❌ This feature is restricted to Bot Admins only!", show_alert=True)
            
        buttons = [[
            InlineKeyboardButton('ʙᴀᴄᴋ', callback_data='start') # തിരികെ മെയിൻ മെനുവിലേക്ക് പോകാൻ 🔙          
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        
        try:
            await query.message.edit_text(
                text=script.COMMANDS_TXT, 
                reply_markup=reply_markup, 
                parse_mode=enums.ParseMode.HTML
            )
        except Exception:
            await query.message.edit_caption(
                caption=script.COMMANDS_TXT, 
                reply_markup=reply_markup, 
                parse_mode=enums.ParseMode.HTML
            )

    elif query.data == "start":
        buttons = [
            [InlineKeyboardButton("👥 Jᴏɪɴ Oᴜʀ Gʀᴏᴜᴘ 👥", url="https://t.me/+eb__Eg3RS2IyZWQ1")]
        ]
       
        # 🔐 അഡ്മിൻമാർക്ക് മാത്രം കാണിക്കുന്ന പ്രത്യേക ബട്ടണുകൾ
        if query.from_user.id in ADMINS:
            buttons.append([
                InlineKeyboardButton("🛠️ Commands", callback_data="bot_commands"), 
                InlineKeyboardButton("📊 Stats", callback_data="stats")
            ])
            buttons.append([
                InlineKeyboardButton("🖥️ Server", callback_data="koyeb_stats"),
                InlineKeyboardButton("✖️ Cʟᴏsᴇ ✖️", callback_data="close_data")
            ])
        else:
            # 👥 സാധാരണ ഉപയോക്താക്കൾക്ക് ബോട്ട് ഗ്രൂപ്പിലേക്ക് ആഡ് ചെയ്യാനുള്ള ബട്ടണും ക്ലോസ് ബട്ടണും
            buttons.append([InlineKeyboardButton("➕ Aᴅᴅ Mᴇ Tᴏ Yᴏᴜʀ Gʀᴏᴜᴘ ➕", url=f"https://t.me/{temp.U_NAME}?startgroup=true")])
            buttons.append([InlineKeyboardButton("✖️ Cʟᴏsᴇ ✖️", callback_data="close_data")])
       
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
            text=script.START_TXT.format(query.from_user.mention, temp.U_NAME, temp.B_NAME),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )    
    


    elif query.data == "koyeb_stats":
        # 🔐 അഡ്മിൻ സുരക്ഷാ ചെക്ക് (അഡ്മിന്മാർക്ക് മാത്രമേ സെർവർ പോപ്പ്-അപ്പ് കാണാൻ സാധിക്കൂ)
        if query.from_user.id not in ADMINS:
            return await query.answer("❌ This feature is restricted to Bot Admins only!", show_alert=True)
            
        # 🖥️ Koyeb VPS സെർവറിന്റെ തത്സമയ വിവരങ്ങൾ ശേഖരിക്കുന്നു
        import psutil
        import shutil
        
        cpu_usage = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        ram_usage = ram.percent
        ram_used_mb = round(ram.used / (1024 * 1024), 2)
        ram_total_mb = round(ram.total / (1024 * 1024), 2)
        
        total_d, used_d, free_d = shutil.disk_usage("/")
        disk_usage = round((used_d / total_d) * 100, 2)
        
        # 💬 പോപ്പ്-അപ്പിൽ കാണിക്കേണ്ട മെസ്സേജ് തയാറാക്കുന്നു (ശ്രദ്ധിക്കുക: പോപ്പ്-അപ്പിൽ HTML ടാഗുകൾ സപ്പോർട്ട് ചെയ്യില്ല)
        koyeb_popup_text = (
            "🖥️ KOYEB SERVER HARDWARE STATUS 🖥️\n\n"
            f"⚙️ CPU Usage: {cpu_usage}%\n"
            f"🧠 RAM Usage: {ram_usage}% ({ram_used_mb}MB / {ram_total_mb}MB)\n"
            f"💽 Disk Space: {disk_usage}%\n\n"
            "⚡ Server performance is stable and running active!"
        )
        
        # 🚀 show_alert=True നൽകി മനോഹരമായ ഒരു Pop-up Alert ആയി വിവരങ്ങൾ കാണിക്കുന്നു ✨
        return await query.answer(koyeb_popup_text, show_alert=True)

    elif query.data == "stats":
        # 🔐 അഡ്മിൻ സുരക്ഷാ ചെക്ക് (അഡ്മിന്മാർക്ക് മാത്രമേ കാണാൻ സാധിക്കൂ)
        if query.from_user.id not in ADMINS:
            return await query.answer("❌ This feature is restricted to Bot Admins only!", show_alert=True)
            
        buttons = [[
            InlineKeyboardButton('ʙᴀᴄᴋ', callback_data='start')           
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)        
        
        # 1. ഒരൊറ്റ മെയിൻ ഡാറ്റാബേസിൽ നിന്ന് എല്ലാ ഫയൽ കൗണ്ടുകളും എടുക്കുന്നു ⚡
        total_connections = await clientDB['connections'].count_documents({})
        total_filters = await clientDB['filters'].count_documents({})
        total_gfilters = await clientDB['gfilters'].count_documents({})
        total_locks = await clientDB['locks'].count_documents({})
        total_poster = await clientDB['poster'].count_documents({})
        total_moviereq = await clientDB['moviereq'].count_documents({})
        
        # 🎬 സിനിമകളുടെ എണ്ണവും യൂസർ/ഗ്രൂപ്പ് കൗണ്ടുകളും
        total_media = await clientDB['mcu_files'].count_documents({}) 
        total_users = await clientDB['users'].count_documents({})
        total_chats = await clientDB['group'].count_documents({})
        
        # 📢 🚀 Fsub 1, Fsub 2 ജോയിൻ റിക്വസ്റ്റുകളുടെ ലൈവ് എണ്ണം എടുക്കുന്നു ✨
        total_req_one = await clientDB['reqone'].count_documents({})
        total_req_two = await clientDB['reqtwo'].count_documents({})
        
        # 2. മംഗോഡിബിയിൽ നിലവിലുള്ള മുഴുവൻ കളക്ഷൻ ഫോൾഡറുകളുടെ പേരുകൾ എടുക്കുന്നു
        collections = await clientDB.list_collection_names()
        
        # 3. ആകെ ഡോക്യുമെന്റുകളുടെ വിവരങ്ങൾ കൂട്ടിയെടുക്കുന്നു
        total_all_documents = (
            total_connections + total_filters + total_gfilters + total_locks + 
            total_poster + total_moviereq + total_media + total_users + total_chats +
            total_req_one + total_req_two
        )
        
        # 4. ഡാറ്റാബേസ് യഥാർത്ഥ സ്റ്റോറേജ് സൈസ് (Used & Free) കണക്കാക്കുന്നു
        try:
            stats = await clientDB.command('dbStats')
            used_dbSize = (stats.get('dataSize', 0) / (1024 * 1024)) + (stats.get('indexSize', 0) / (1024 * 1024))        
            free_dbSize = 512.0 - used_dbSize
            if free_dbSize < 0: 
                free_dbSize = 0.0
            storage_text = f"💾 <b>Storage Used:</b> <code>{round(used_dbSize, 2)} MB</code> / <b>Free:</b> <code>{round(free_dbSize, 2)} MB</code>\n"
        except Exception:
            storage_text = "💾 <b>Storage Space:</b> <code>Statistics Unavailable</code>\n"
        
        # 5. റിസൾട്ട് ഒരൊറ്റ മെസ്സേജിൽ പുതിയ പേരുകൾ വെച്ച് കൃത്യമായി ഫോർമാറ്റ് ചെയ്യുന്നു ⚡
        stats_text = f"📊 <b>★ BOT & DATABASE FULL REPORT ★</b>\n"
        stats_text += f"🗄️ <b>DB Name:</b> <code>{DATABASE_NAME}</code>\n"
        stats_text += f"{storage_text}\n"
        
        stats_text += "📈 <b>Core Bot Growth Status:</b>\n"
        stats_text += f" ├ 🔗 <code>connections</code> → <b>{total_connections}</b> Linked Users\n"
        stats_text += f" ├ 📁 <code>mcu_files</code> → <b>{total_media}</b> Indexed Movies 🎬\n"
        stats_text += f" ├ 👥 <code>users</code> → <b>{total_users}</b> Total Bot Users\n"
        stats_text += f" └ 👥 <code>group</code> → <b>{total_chats}</b> Total Bot Chats\n\n"
        
        # 📢 Fsub റിക്വസ്റ്റുകളുടെ കണക്ക് ഇവിടെ മനോഹരമായി കാണിക്കുന്നു ✨
        stats_text += "📢 <b>Fsub Join Requests:</b>\n"
        stats_text += f" ├ 🟢 <code>Fsub 1 Req</code> → <b>{total_req_one}</b> Pending Requests\n"
        stats_text += f" └ 🟢 <code>Fsub 2 Req</code> → <b>{total_req_two}</b> Pending Requests\n\n"
        
        stats_text += "📂 <b>Database Collections List:</b>\n"
        for col_name in sorted(collections):
            col_count = await clientDB[col_name].count_documents({})
            if col_name in ["filters", "connections", "locks", "poster", "moviereq"]:
                stats_text += f" ├ <code>{col_name}</code> → <b>{col_count}</b> ✨\n"
            else:
                stats_text += f" ├ <code>{col_name}</code> → <b>{col_count}</b>\n"
                
        stats_text += f" └ <b>Total Active Collections:</b> {len(collections)}\n\n"
        stats_text += f"🗂️ <b>Total Overall Documents in DB:</b> <code>{total_all_documents}</code>\n\n"
        stats_text += f"💡 <i>Note: ✨ എന്ന് അടയാളപ്പെടുത്തിയത് നമ്മൾ ഒപ്റ്റിമൈസ് ചെയ്ത സിംഗിൾ കളക്ഷനുകളാണ്.</i>"

        try:
            await query.message.edit_caption(caption=stats_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
        except Exception:
            await query.message.edit_text(text=stats_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)




async def auto_filter(client, msg, spoll=False):
    if not spoll:
        message = msg
        if not message.text or message.text.startswith("/"): return
        if re.findall(r"((^/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text): return
        if not 0 < len(message.text) < 100: return

        raw_search_query = message.text.strip()
        search = re.sub(r'[\u200b\u200c\u200d\ufeff\u200e\u200f]', '', raw_search_query)
        search = re.sub(r'[\s\u00a0\u2000-\u200a\u202f\u205f\u3000]+', ' ', search)
        search = re.sub(r"['‘’]", "", search)
        search = re.sub(r"""[-–—\\_,#&?/( )\[\]":\.¡%“”]""", " ", search)
        search = re.sub(r"\b(hd|full|print|file)\b", "", search, flags=re.IGNORECASE)

        removes = {"pls","plz","plzz","please","send","snd","snt","gib","veno","venam","venum","undo","ayakkumo","und","move","multi","dubb","dub","bro","bruh","broh","dubbed","link","lnk","iruka","pannunga","pannungga","anuppunga","anupunga","anuppungga","anupungga","subtile","kitti","kitty","tharu","kittumo","kittum","da","mwonse","bhai","share","malayalm","malylm","subtitle"}
        search = " ".join(w for w in search.lower().split() if w not in removes).strip()
        if not search: return

        files, offset, total_results = await get_search_results(search, offset=0, filter=True)
        if not files:
            try: await advantage_spell_chok(client, msg)
            except Exception: pass
            return

        key = f"{message.chat.id}-{message.id}"
        _trim_dict(BUTTONS)
        BUTTONS[key] = {"query": search, "total": total_results, "time": time.time()}
    else:
        message = msg.message.reply_to_message if hasattr(msg, "message") and msg.message else msg
        search, files, offset, total_results = spoll

        key = f"{message.chat.id}-{message.id}"
        _trim_dict(BUTTONS)
        BUTTONS[key] = {"query": search, "total": total_results, "time": time.time()}

    year_match = re.findall(r'\b(19\d{2}|20[0-2]\d)\b', search)
    print_check_text, languages_found = "", []
    lang_map = {
        'malayalam':'Malayalam','mal':'Malayalam','tamil':'Tamil','tam':'Tamil',
        'telugu':'Telugu','tel':'Telugu','hindi':'Hindi','hin':'Hindi',
        'english':'English','eng':'English','kannada':'Kannada','kan':'Kannada',
        'marathi':'Marathi','mar':'Marathi','bengali':'Bengali','ben':'Bengali',
        'odia':'Odia','ori':'Odia','multi':'Multi_Audio','audio':'Multi_Audio','dual':'Multi_Audio'
    }

    if files and isinstance(files, list):
        for file in files[:5]:
            if getattr(file, "file_name", None):
                fname = file.file_name.lower()
                for word in set(re.findall(r'\b\w+\b', fname)):
                    lang = lang_map.get(word)
                    if lang and lang not in languages_found: languages_found.append(lang)
        if getattr(files[0], "file_name", None): print_check_text = files[0].file_name.lower()

    for word in set(re.findall(r'\b\w+\b', search.lower())):
        lang = lang_map.get(word)
        if lang and lang not in languages_found: languages_found.append(lang)

    if not year_match and files and getattr(files[0], "file_name", None):
        found_years = re.findall(r'\b(19\d{2}|20[0-2]\d)\b', files[0].file_name)
        if found_years: year_match = [found_years[0]]

    detected_year = year_match[0] if year_match else ""
    movie_year = f" ({detected_year})" if detected_year else ""
    detected_print = "HD_Original"

    if print_check_text and re.search(r'\b(predvd|pre-dvd|dvdscr|hallprint|camrip|cam|hdcam|hall-print|s-print|HDTC)\b', print_check_text, re.I):
        detected_print = "Theater_Print ⚠️"

    detected_lang = ", ".join(languages_found) if languages_found else "#Unknown"
    files_count = total_results if total_results is not None else len(files)
    clean_title = re.sub(r'\b(19\d{2}|20[0-2]\d)\b', '', search).strip().upper()

    cap = (
        f"➤ꜰɪʟᴍ : {clean_title}{movie_year}\n"
        f"➤ʟᴀɴɢᴜᴀɢᴇ : {detected_lang}\n"
        f"➤ᴘʀɪɴᴛ ᴛʏᴘᴇ : {detected_print}\n"
        f"➤ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : {files_count}\n\n"
        f"© ᴛᴇᴀᴍ ᴜʀᴠᴀꜱʜɪ ᴛʜᴇᴀᴛᴇʀꜱ™"
    )

    settings = await get_settings(message.chat.id)
    btn, pre = [], 'filep' if settings.get('file_secure', False) else 'file'

    for file in files:
        url = f"https://t.me/{temp.U_NAME}?start={pre}_{file.file_id}"
        if settings.get("button", False):
            btn.append([InlineKeyboardButton(text=f"{get_size(file.file_size)}➪{file.file_name}", url=url)])
        else:
            btn.append([
                InlineKeyboardButton(text=file.file_name, url=url),
                InlineKeyboardButton(text=get_size(file.file_size), url=url)
            ])

    offset = int(offset) if offset != "" and str(offset).isdigit() else 0
    if offset > 0:
        btn.append([
            InlineKeyboardButton(text=f"1/{math.ceil(int(total_results) / 10)}", callback_data="pages"),
            InlineKeyboardButton(text="Nᴇxᴛ", callback_data=f"next_{message.from_user.id}_{key}_{offset}")
        ])

    reply_markup = InlineKeyboardMarkup(btn)

    try:
        poster = await asyncio.wait_for(get_poster(search), timeout=7)
    except Exception:
        poster = None

    try:
        if poster:
            await message.reply_photo(photo=poster, caption=cap, reply_markup=reply_markup)
        else:
            await message.reply_text(text=cap, reply_markup=reply_markup, disable_web_page_preview=True)
    except Exception:
        pass


async def advantage_spell_chok(client, msg):
    mv_id, mv_rqst = msg.id, msg.text
    reqstr1 = msg.from_user.id if msg.from_user else 0
    cleaned_query = re.sub(
        r"\b(pl(i|e)\*?(s|z+|ease|se|ese|(e+)s(e)?)|((send|snd|giv(e)?|gib)(\sme)?)|movie(s)?|new|latest|"
        r"br((o|u)h?)\*|^h(e|a)?(l)\*(o)\*|mal(ayalam)?|t(h)?amil|file|that|find|und(o)\*|"
        r"kit(t(i|y)?)?o(w)?|thar(u)?(o)\*w?|kittum(o)\*|aya(k)\*(um(o)\*)?|full\smovie|any(one)|with\ssubtitle(s)?)",
        "", msg.text, flags=re.IGNORECASE
    ).strip()

    # 🟢 1. ബാക്ക്ഗ്രൗണ്ടിൽ മാനുവൽ ഫിൽട്ടർ ഉണ്ടോ എന്ന് ചെക്ക് ചെയ്യുന്നു
    try:
        manual_res = await manual_filters(client, msg)
    except Exception as e:
        logger.error(f"Manual filter error in spell check: {e}")
        manual_res = False

    # 🟢 2. മാനുവൽ ഫിൽട്ടറിൽ സിനിമ ഉണ്ടെങ്കിൽ (True ആണെങ്കിൽ) ഫങ്ഷൻ ഇവിടെ വെച്ച് നിർത്തുന്നു
    # ഗ്രൂപ്പിലേക്ക് സ്പെൽ ചെക്ക് മെസ്സേജ് അയക്കില്ല, സിനിമ ഡാറ്റാബേസിൽ സേവ് ചെയ്യുകയുമില്ല.
    if manual_res == True:
        logger.info(f"Manual filter-ൽ സിനിമ ഉള്ളതിനാൽ സ്പെൽ ചെക്ക് ഒഴിവാക്കി.")
        return

    # 🟢 3. മാനുവൽ ഫിൽട്ടറിലും സിനിമ ഇല്ലെങ്കിൽ മാത്രം missing movie ലിസ്റ്റിലേക്ക് സേവ് ചെയ്യും
    try:
        await save_missing_movie(cleaned_query)
    except Exception as e:
        logger.error(f"Missing movie save error: {e}")

    # 📝 4. സിനിമ ഒന്നിലും ഇല്ലാത്തതുകൊണ്ട് താഴോട്ടുള്ള നിങ്ങളുടെ പഴയ സ്പെൽ ചെക്ക് കോഡുകൾ റൺ ആകുന്നു
    reqst_gle = quote_plus(mv_rqst)
    google_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 𝗖𝗼𝗿𝗿𝗲𝗰𝘁 𝗦𝗽𝗲𝗹𝗹𝗶𝗻𝗴 (𝖦𝗈𝗈𝗀𝗅𝖾)", url=f"https://www.google.com/search?q={reqst_gle}")],
        [InlineKeyboardButton("📜 Rᴜʟᴇs", url="https://t.me/Chithralokham/7"), InlineKeyboardButton("📥 Rᴇqᴜᴇsᴛ", url="http://t.me/UrvasiTheatres_bot")]
    ])

    try:
        movies = await get_poster(cleaned_query, bulk=True)
    except Exception:
        movies = None

    if not movies:
        try:
            await msg.reply_text(
                script.SPELL_TEXT.format(msg.from_user.mention),
                reply_markup=google_button,
                reply_to_message_id=msg.id,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception:
            pass
        return

    movielist = []
    for movie in movies:
        if isinstance(movie, dict):
            title = movie.get('title')
            year = movie.get('year')
        else:
            title = movie.get('title') if hasattr(movie, 'get') else getattr(movie, 'title', None)
            year = movie.get('year') if hasattr(movie, 'get') else getattr(movie, 'year', None)
        
        if title:
            if year and str(year) != "N/A":
                year_str = re.findall(r'\b(19\d{2}|20\d{2})\b', str(year))
                year_val = f" {year_str[0]}" if year_str else ""
            else:
                year_val = ""
                
            movielist.append(f"{title.strip()}{year_val}")

    if not movielist:
        return

    # 📝 Heading ചേർക്കുന്നു
    spell_list_text = script.NO_TXT + "\n\n"
    spell_list_text += "<u><b>SUGGESTIONS 👇</b></u>\n\n"
    
    # സജഷനുകൾ HTML-ൽ ബോൾഡ് ആയി ലിസ്റ്റ് ചെയ്യുന്നു
    for index, movie_name in enumerate(movielist[:4], start=1):
        spell_list_text += f"<b>{index}. {movie_name}</b>\n"

    # 🖼️ ഫോട്ടോ എടുക്കാൻ get_any_movie_poster നിലനിർത്തിയിരിക്കുന്നു
    try: 
        photo_url = await get_poster(cleaned_query)
    except Exception: 
        photo_url = None

    if not photo_url:
        photo_url = "https://files.catbox.moe/8llz8q.jpg"

    # 📥 ഫോട്ടോ സഹിതം മറുപടി അയക്കുന്നു
    try:
        spell_check_del = await msg.reply_photo(
            photo=photo_url,
            caption=spell_list_text,
            reply_markup=google_button,
            reply_to_message_id=msg.id,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception:
        # ഫോട്ടോ അയക്കുന്നതിൽ എന്തെങ്കിലും തടസ്സം വന്നാൽ ബാക്കപ്പ് ആയി ടെക്സ്റ്റ് അയക്കും
        try:
            spell_check_del = await msg.reply_text(
                text=spell_list_text,
                reply_markup=google_button,
                reply_to_message_id=msg.id,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception:
            return
           
                               
        

async def global_filters(client, message, text=False):
    group_id = message.chat.id
    raw_name = text or message.text
    
    # 🌟 ഇവിടെ raw_name-നെ സുരക്ഷിതമായി സ്ട്രിംഗ് (str) ആക്കി മാറ്റുന്നു
    # ഇത് Pyrogram-ന്റെ 'utf-16-le' ഡീകോഡിങ് എറർ പൂർണ്ണമായി ഇല്ലാതാക്കും
    safe_name = str(raw_name) if raw_name else ""

    try:
        # ഇമോജികൾ നീക്കം ചെയ്യുന്നു
        search = emoji.replace_emoji(safe_name, replace='')
    except Exception:
        # ഏതെങ്കിലും സാഹചര്യത്തിൽ വീണ്ടും തകരാർ വന്നാൽ എറർ അടിക്കാതെ മുന്നോട്ട് പോകാൻ
        search = safe_name

    search = re.sub(r'[\u200b\u200c\u200d\ufeff\u200e\u200f]', '', search)
    search = re.sub(r'[\s\u00a0\u2000-\u200a\u202f\u205f\u3000]+', ' ', search)
    search = re.sub(r"['‘’]", "", search)
    search = re.sub(r"[-–—_,#&?/( )\[\]\\\":\.¡%“”]", " ", search)
    search = re.sub(r"\b(hd|full|print|file)\b", "", search, flags=re.IGNORECASE)
    find = search.lower().split(" ")
    removes = {"pls","plz","plzz","please","send","snd","snt","gib","veno","venam","venum","undo","ayakkumo","ayakkamo","und","move","multi","dubb","dub","bro","bruh","broh","dubbed","link","lnk","iruka","pannunga","pannungga","anuppunga","anupunga","anuppungga","anupungga","subtile","kitti","kitty","tharu","kittumo","kittum","da","mwonse","bhai","share","malayalm","malylm","subtitle"}
    search = " ".join(w for w in find if w not in removes)
    clean_name = re.sub(r"\s+", " ", search).strip()

    reply_id = message.reply_to_message.id if message.reply_to_message else message.id
    keywords = await get_gfilters('gfilters')

    for keyword in reversed(sorted(keywords, key=len)):
        pattern = r"^" + re.escape(keyword.strip().lower()) + r"$"
        if re.match(pattern, clean_name, flags=re.IGNORECASE):
            reply_text, btn, alert, fileid = await find_gfilter('gfilters', keyword)
            if reply_text: reply_text = reply_text.replace("\\n", "\n").replace("\\t", "\t")

            if btn is not None:
                try:
                    if btn != "[]":
                        try: button = json.loads(btn)
                        except Exception: button = eval(btn)
                    else: button = []

                    g_msg = None
                    if fileid == "None":
                        while True:
                            try:
                                if btn == "[]":
                                    g_msg = await client.send_message(group_id, reply_text, disable_web_page_preview=True, reply_to_message_id=reply_id)
                                else:
                                    g_msg = await client.send_message(group_id, reply_text, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(button), reply_to_message_id=reply_id)
                                break
                            except FloodWait as e:
                                logger.warning(f"FloodWait triggered! Sleeping for {e.value} seconds.")
                                await asyncio.sleep(e.value)
                    elif btn == "[]":
                        while True:
                            try:
                                g_msg = await client.send_cached_media(group_id, fileid, caption=reply_text or "", reply_to_message_id=reply_id)
                                break
                            except FloodWait as e:
                                logger.warning(f"FloodWait triggered! Sleeping for {e.value} seconds.")
                                await asyncio.sleep(e.value)
                    else:
                        while True:
                            try:
                                g_msg = await client.send_cached_media(group_id, fileid, caption=reply_text or "", reply_markup=InlineKeyboardMarkup(button), reply_to_message_id=reply_id)
                                break
                            except FloodWait as e:
                                logger.warning(f"FloodWait triggered! Sleeping for {e.value} seconds.")
                                await asyncio.sleep(e.value)

                except Exception as e:
                    logger.exception(e)
                break
    else:
        return False




async def manual_filters(client, message, text=False):
    group_id = message.chat.id
    name = text or message.text
    reply_id = message.reply_to_message.id if message.reply_to_message else message.id
    
    # 🟢 universal_manual_filters അടിസ്ഥാനമാക്കി എല്ലാ ഫിൽട്ടറുകളും ഒരുമിച്ച് എടുക്കുന്നു
    keywords = await get_filters('universal_manual_filters')
    
    for keyword in reversed(sorted(keywords, key=len)):
        pattern = r"( |^|[^\w])" + re.escape(keyword) + r"( |$|[^\w])"
        if re.search(pattern, name, flags=re.IGNORECASE):
            # 🟢 ഡാറ്റ കണ്ടെത്തുന്നതിനും universal_manual_filters കീ ഉപയോഗിക്കുന്നു
            reply_text, btn, alert, fileid = await find_filter('universal_manual_filters', keyword)

            if reply_text:
                reply_text = reply_text.replace("\\n", "\n").replace("\\t", "\t")

            if btn is not None:
                try:
                    if fileid == "None":
                        if btn == "" or btn == "[]":
                            await client.send_message(
                                group_id, 
                                reply_text, 
                                disable_web_page_preview=True,
                                reply_to_message_id=reply_id
                            )
                        else:
                            button = eval(btn)
                            await client.send_message(
                                group_id,
                                reply_text,
                                disable_web_page_preview=True,
                                reply_markup=InlineKeyboardMarkup(button),
                                reply_to_message_id=reply_id
                            )
                    elif btn == "" or btn == "[]":
                        # 🛠️ ഫിക്സ് ചെയ്ത ഭാഗം: 'media' മാറ്റി 'file_id' എന്ന് നൽകി
                        await client.send_cached_media(
                            chat_id=group_id,
                            file_id=fileid,
                            caption=reply_text or "",
                            reply_to_message_id=reply_id
                        )
                    else:
                        button = eval(btn)
                        # 🛠️ ഫിക്സ് ചെയ്ത ഭാഗം: 'media' മാറ്റി 'file_id' എന്ന് നൽകി
                        await client.send_cached_media(
                            chat_id=group_id,
                            file_id=fileid,
                            caption=reply_text or "",
                            reply_markup=InlineKeyboardMarkup(button),
                            reply_to_message_id=reply_id
                        )
                except Exception as e:
                    logger.exception(e)
                
                return True
    else:
        return False
