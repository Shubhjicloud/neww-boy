# bot.py — Ready-to-run (Termux friendly)
import os
import json
import time
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ========== CONFIG - (user-provided, don't share) ==========
TOKEN = "8322047077:AAFSuPisY5Pk6nF2H1PCcZP5u6HdjwpXSLY"
ADMIN_ID = 1330442598
DATA_FILE = "users.json"
PHOTO_DIR = "photos"
CHANNEL_USERNAME = "colorhackop2"   # only username, without @ or https://t.me/
REGISTER_LINK = "https://t.me/+DO562nExrwFiYTE1"
# ==========================================================

Path(PHOTO_DIR).mkdir(parents=True, exist_ok=True)


# ---------- Simple JSON DB helpers ----------
def load_db() -> Dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_db(db: Dict):
    with open(DATA_FILE, "w") as f:
        json.dump(db, f, indent=2)


db = load_db()  # key: str(chat_id) -> info dict


def ensure_user_record(u) -> Dict:
    """Ensure a user record exists and return it (u is telegram.User)."""
    uid = str(u.id)
    if uid not in db:
        db[uid] = {
            "username": u.username or "",
            "first_name": u.first_name or "",
            "verified": False,
            "joined_at": int(time.time()),
            "photos": [],
        }
        save_db(db)
    return db[uid]


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ---------- Handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_record(user)
    text = (
        "Hello bro 👋\n\n"
        f"Es link se ID banao: {REGISTER_LINK}\n\n"
        "2 sureshots pane ka moka unlock ho jayega.\n"
        "Deposit karte hi screenshot yahi bhejo.\n\n"
        "Photo bhejoge toh main usse verify karke reply kar dunga."
    )
    await update.message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Commands:\n"
        "/start - register\n"
        "/status - check your status\n"
        "/members - admin only\n"
        "/broadcast <msg> - admin only (sends private msg to saved users)\n"
        "/reply <user_id> <message> - admin only\n"
        "/approve <user_id> - admin only (mark verified)\n"
        "/sendto <user_id> <message> - admin only\n"
        "/channel - admin only (get invite link if bot is admin of channel)\n"
    )
    await update.message.reply_text(text)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    info = db.get(uid)
    if not info:
        await update.message.reply_text("Tumne abhi /start nahi kiya.")
        return
    verified = info.get("verified", False)
    joined = datetime.utcfromtimestamp(info.get("joined_at")).strftime("%Y-%m-%d %H:%M:%S")
    await update.message.reply_text(f"Hello {info.get('first_name')}\nVerified: {verified}\nJoined: {joined}")


# Photo handler: save photo, mark unverified and notify admin (admin can approve)
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid_str = str(user.id)
    ensure_user_record(user)

    if not update.message.photo:
        await update.message.reply_text("Photo send karo.")
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    ts = int(time.time())
    filename = f"{uid_str}_{ts}.jpg"
    path = os.path.join(PHOTO_DIR, filename)
    await file.download_to_drive(path)

    # update DB: store photo and keep verified=False until admin approves
    db[uid_str]["photos"].append({"file": path, "time": ts})
    db[uid_str]["verified"] = False  # manual approve flow
    save_db(db)

    await update.message.reply_text("✅ Photo received. Waiting for admin verification.")

    # Notify admin with user info + forward the original message
    try:
        uname = user.username or "NoUsername"
        fname = (user.first_name or "") + ((" " + user.last_name) if user.last_name else "")
        info_text = (
            f"📥 New photo from user:\n"
            f"ID: {user.id}\n"
            f"Name: {fname}\n"
            f"Username: @{uname}\n"
            f"Saved as: {filename}\n"
            f"Time: {datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            f"Use /approve {user.id} to mark verified, or /reply {user.id} <msg> to reply."
        )
        await context.bot.send_message(ADMIN_ID, info_text)
        # forward original message (so admin sees original sender in the forward card)
        await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
    except Exception as e:
        # notify admin of error
        try:
            await context.bot.send_message(ADMIN_ID, f"⚠️ Error notifying admin: {e}")
        except Exception:
            pass


# Text handler: notify admin and forward
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid_str = str(user.id)
    ensure_user_record(user)

    text = update.message.text or ""
    # reply to sender
    await update.message.reply_text("Message received ✅")

    # notify admin
    uname = user.username or "NoUsername"
    fname = (user.first_name or "")
    notify = f"✉️ Message from {fname} (@{uname})\nID: {user.id}\n\n{text}"
    try:
        await context.bot.send_message(ADMIN_ID, notify)
        # forward original message for metadata
        await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
    except Exception:
        # ignore forwarding errors but still try to send text
        pass


# Admin: approve user (mark verified True)
async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve <user_id>")
        return
    try:
        target = str(int(context.args[0]))
        if target not in db:
            await update.message.reply_text("User not found in DB.")
            return
        db[target]["verified"] = True
        save_db(db)
        await update.message.reply_text(f"User {target} marked verified.")
        # notify user
        try:
            await context.bot.send_message(int(target), "✅ Aapka photo verify ho gaya hai. Congratulations!")
        except Exception:
            pass
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# Admin: reply to user by id
async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /reply <user_id> <message>")
        return
    try:
        target = int(context.args[0])
        msg = " ".join(context.args[1:])
        await context.bot.send_message(chat_id=target, text=f"📩 Admin reply: {msg}")
        await update.message.reply_text("✅ Reply sent.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# Admin: broadcast to all saved users (private messages)
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    msg = " ".join(context.args)
    await update.message.reply_text("Broadcast starting...")
    sent = 0
    for uid_str in list(db.keys()):
        try:
            await context.bot.send_message(int(uid_str), msg)
            sent += 1
            await asyncio.sleep(0.08)  # small delay to avoid hitting rate limits
        except Exception:
            continue
    await update.message.reply_text(f"Broadcast finished. Sent to {sent} users.")


# Admin: members list (send as text or file)
async def members_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    lines = []
    for uid, info in db.items():
        lines.append(f"{uid} | @{info.get('username','')} | verified={info.get('verified')}")
    text = "\n".join(lines) or "No members yet."
    if len(text) > 4000:
        p = "members_list.txt"
        with open(p, "w") as f:
            f.write(text)
        await context.bot.send_document(update.effective_chat.id, p)
        os.remove(p)
    else:
        await update.message.reply_text(text)


# Admin: send to specific user
async def sendto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /sendto <user_id> <message>")
        return
    try:
        target = int(context.args[0])
        msg = " ".join(context.args[1:])
        await context.bot.send_message(target, msg)
        await update.message.reply_text("Message sent.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# Admin: create channel invite link (bot must be admin in channel)
async def channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if not CHANNEL_USERNAME:
        await update.message.reply_text("CHANNEL_USERNAME not configured.")
        return
    try:
        # create invite link for the channel (bot must be admin)
        # chat_id can be @channelusername
        chat_id = f"@{CHANNEL_USERNAME}"
        link = await context.bot.create_chat_invite_link(chat_id=chat_id, member_limit=0)
        await update.message.reply_text(f"Channel invite link:\n{link.invite_link}")
    except Exception as e:
        await update.message.reply_text(f"Error creating link: {e}")


# Fallback / unknown command handler (optional)
async def unknown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Command not recognized. Type /help")


# ---------- Main ----------
def main():
    app = Application.builder().token(TOKEN).build()

    # user-facing
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))

    # admin
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("reply", reply_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("members", members_cmd))
    app.add_handler(CommandHandler("sendto", sendto_cmd))
    app.add_handler(CommandHandler("channel", channel_cmd))

    # messages
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # unknown
    app.add_handler(MessageHandler(filters.COMMAND, unknown_cmd))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main() 
