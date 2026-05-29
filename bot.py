import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import BOT_TOKEN, CHANNEL_ID, ADMIN_ID, BOT_USERNAME

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

AUTO_DELETE_REPORTS = 100


# ─── Database ────────────────────────────────────────────────────────────────

def init_db():
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY,
            tg_id       INTEGER UNIQUE NOT NULL,
            first_name  TEXT,
            username    TEXT,
            is_banned   INTEGER DEFAULT 0,
            joined_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id           INTEGER NOT NULL,
            message         TEXT NOT NULL,
            anonymous       INTEGER DEFAULT 0,
            channel_msg_id  INTEGER,
            likes           INTEGER DEFAULT 0,
            dislikes        INTEGER DEFAULT 0,
            reports         INTEGER DEFAULT 0,
            deleted         INTEGER DEFAULT 0,
            posted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_id         TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            post_id     INTEGER NOT NULL,
            tg_id       INTEGER NOT NULL,
            vote        TEXT NOT NULL,
            PRIMARY KEY (post_id, tg_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            post_id     INTEGER NOT NULL,
            tg_id       INTEGER NOT NULL,
            PRIMARY KEY (post_id, tg_id)
        )
    """)
    con.commit()
    con.close()


def save_user(tg_id, first_name, username):
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("""
        INSERT INTO users (tg_id, first_name, username)
        VALUES (?, ?, ?)
        ON CONFLICT(tg_id) DO UPDATE SET
            first_name = excluded.first_name,
            username   = excluded.username
    """, (tg_id, first_name, username))
    con.commit()
    con.close()


def get_user(tg_id):
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    con.close()
    return row  # id, tg_id, first_name, username, is_banned, joined_at


def is_banned(tg_id):
    user = get_user(tg_id)
    return user and user[4] == 1


def set_ban(tg_id, banned: bool):
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("UPDATE users SET is_banned = ? WHERE tg_id = ?", (int(banned), tg_id))
    con.commit()
    con.close()


def save_post(tg_id, message, anonymous, channel_msg_id, file_id=None):
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute(
        "INSERT INTO posts (tg_id, message, anonymous, channel_msg_id, file_id) VALUES (?, ?, ?, ?, ?)",
        (tg_id, message, int(anonymous), channel_msg_id, file_id)
    )
    post_id = cur.lastrowid
    con.commit()
    con.close()
    return post_id


def get_post(post_id):
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
    row = cur.fetchone()
    con.close()
    return row  # id, tg_id, message, anonymous, channel_msg_id, likes, dislikes, reports, deleted, posted_at, file_id


def get_user_posts(tg_id):
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("""
        SELECT id, message, likes, dislikes, posted_at, file_id
        FROM posts
        WHERE tg_id = ? AND anonymous = 0 AND deleted = 0
        ORDER BY posted_at DESC
    """, (tg_id,))
    rows = cur.fetchall()
    con.close()
    return rows  # id, message, likes, dislikes, posted_at, file_id


def get_user_vote(post_id, tg_id):
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("SELECT vote FROM votes WHERE post_id = ? AND tg_id = ?", (post_id, tg_id))
    row = cur.fetchone()
    con.close()
    return row[0] if row else None


def set_vote(post_id, tg_id, vote):
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    existing = get_user_vote(post_id, tg_id)
    if existing == vote:
        cur.execute("DELETE FROM votes WHERE post_id = ? AND tg_id = ?", (post_id, tg_id))
        if vote == "like":
            cur.execute("UPDATE posts SET likes = likes - 1 WHERE id = ?", (post_id,))
        else:
            cur.execute("UPDATE posts SET dislikes = dislikes - 1 WHERE id = ?", (post_id,))
        action = "removed"
    elif existing:
        cur.execute("UPDATE votes SET vote = ? WHERE post_id = ? AND tg_id = ?", (vote, post_id, tg_id))
        if vote == "like":
            cur.execute("UPDATE posts SET likes = likes + 1, dislikes = dislikes - 1 WHERE id = ?", (post_id,))
        else:
            cur.execute("UPDATE posts SET likes = likes - 1, dislikes = dislikes + 1 WHERE id = ?", (post_id,))
        action = "switched"
    else:
        cur.execute("INSERT INTO votes (post_id, tg_id, vote) VALUES (?, ?, ?)", (post_id, tg_id, vote))
        if vote == "like":
            cur.execute("UPDATE posts SET likes = likes + 1 WHERE id = ?", (post_id,))
        else:
            cur.execute("UPDATE posts SET dislikes = dislikes + 1 WHERE id = ?", (post_id,))
        action = "added"
    con.commit()
    cur.execute("SELECT likes, dislikes FROM posts WHERE id = ?", (post_id,))
    likes, dislikes = cur.fetchone()
    con.close()
    return likes, dislikes, action


def add_report(post_id, tg_id):
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("SELECT 1 FROM reports WHERE post_id = ? AND tg_id = ?", (post_id, tg_id))
    if cur.fetchone():
        con.close()
        return True, None
    cur.execute("INSERT INTO reports (post_id, tg_id) VALUES (?, ?)", (post_id, tg_id))
    cur.execute("UPDATE posts SET reports = reports + 1 WHERE id = ?", (post_id,))
    con.commit()
    cur.execute("SELECT reports FROM posts WHERE id = ?", (post_id,))
    count = cur.fetchone()[0]
    con.close()
    return False, count


def mark_post_deleted(post_id):
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("UPDATE posts SET deleted = 1 WHERE id = ?", (post_id,))
    con.commit()
    con.close()


def get_all_users():
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("SELECT tg_id, first_name, username, is_banned, joined_at FROM users ORDER BY joined_at DESC")
    rows = cur.fetchall()
    con.close()
    return rows


def get_stats():
    con = sqlite3.connect("bot.db")
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM posts WHERE deleted = 0")
    total_posts = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM posts WHERE anonymous = 1 AND deleted = 0")
    anon_posts = cur.fetchone()[0]
    con.close()
    return total_users, banned_users, total_posts, anon_posts


# ─── Keyboards ───────────────────────────────────────────────────────────────

def make_post_buttons(post_id, likes=0, dislikes=0, anonymous=False):
    row = [
        InlineKeyboardButton(f"👍 {likes}", callback_data=f"like:{post_id}"),
        InlineKeyboardButton(f"👎 {dislikes}", callback_data=f"dislike:{post_id}"),
        InlineKeyboardButton("⚠️ Report", callback_data=f"reportmenu:{post_id}"),
    ]
    keyboard = [row]
    if not anonymous:
        keyboard.append([
            InlineKeyboardButton(
                "👤 Who posted?",
                url=f"https://t.me/{BOT_USERNAME}?start=whoposted_{post_id}"
            )
        ])
    return InlineKeyboardMarkup(keyboard)


def make_report_buttons(post_id, anonymous=False):
    row = [InlineKeyboardButton("🚨 Confirm Report", callback_data=f"report:{post_id}")]
    if not anonymous:
        row.append(InlineKeyboardButton(
            "👤 Who posted?",
            url=f"https://t.me/{BOT_USERNAME}?start=whoposted_{post_id}"
        ))
    return InlineKeyboardMarkup([
        row,
        [InlineKeyboardButton("« Back", callback_data=f"back:{post_id}")]
    ])


def make_history_buttons(poster_tg_id, posts, index):
    total = len(posts)
    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"hist:{poster_tg_id}:{index - 1}"))
    nav.append(InlineKeyboardButton(f"{index + 1} / {total}", callback_data="noop"))
    if index < total - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"hist:{poster_tg_id}:{index + 1}"))
    return InlineKeyboardMarkup([nav])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def build_profile_url(username, tg_id):
    if username:
        return f"https://t.me/{username}"
    return f"tg://user?id={tg_id}"


def build_caption(message_text, first_name, username, tg_id, anonymous):
    if anonymous:
        return f"{message_text}\n\n— _Anonymous posted_"
    url = build_profile_url(username, tg_id)
    return f"{message_text}\n\n— [{first_name}]({url}) posted"


def format_history_post(post, index, total, poster):
    # post: id, message, likes, dislikes, posted_at, file_id
    post_id, message, likes, dislikes, posted_at, file_id = post
    date = posted_at[:10]
    name = poster[2] or "Unknown"
    username = poster[3]
    url = build_profile_url(username, poster[1])
    return (
        f"📬 *Posts by [{name}]({url})*\n"
        f"─────────────────\n"
        f"{message}\n"
        f"─────────────────\n"
        f"👍 {likes}  👎 {dislikes}  🗓 {date}"
    )


# ─── Handlers ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.first_name, user.username)

    if context.args and context.args[0].startswith("whoposted_"):
        try:
            post_id = int(context.args[0].split("_")[1])
            post = get_post(post_id)
            if not post:
                await update.message.reply_text("❌ Post not found.")
                return
            if post[3] == 1:
                await update.message.reply_text("🕶 This post was made anonymously.")
                return

            poster_tg_id = post[1]
            poster = get_user(poster_tg_id)
            if not poster:
                await update.message.reply_text("❓ Poster info not found.")
                return

            posts = get_user_posts(poster_tg_id)
            name = poster[2] or "Unknown"
            url = build_profile_url(poster[3], poster[1])

            if not posts:
                await update.message.reply_text(
                    f"👤 Posted by [{name}]({url})\n\nNo public posts yet.",
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
                return

            first_post = posts[0]
            text = format_history_post(first_post, 0, len(posts), poster)
            buttons = make_history_buttons(poster_tg_id, posts, 0)
            file_id = first_post[5]

            if file_id:
                await update.message.reply_photo(
                    photo=file_id,
                    caption=text,
                    parse_mode="Markdown",
                    reply_markup=buttons
                )
            else:
                await update.message.reply_text(
                    text,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                    reply_markup=buttons
                )
        except Exception as e:
            logger.error(f"whoposted error: {e}")
            await update.message.reply_text("❌ Something went wrong.")
        return

    await update.message.reply_text(
        f"👋 Hey {user.first_name}!\n\n"
        "Send me any message and I'll post it to the channel.\n"
        "You can choose to post with your name or stay anonymous."
    )


async def handle_history_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data == "noop":
        await query.answer()
        return

    _, poster_tg_id_str, index_str = query.data.split(":")
    poster_tg_id = int(poster_tg_id_str)
    index = int(index_str)

    poster = get_user(poster_tg_id)
    if not poster:
        await query.answer("User not found.", show_alert=True)
        return

    posts = get_user_posts(poster_tg_id)
    if not posts:
        await query.answer("No posts found.", show_alert=True)
        return

    index = max(0, min(index, len(posts) - 1))
    post = posts[index]
    file_id = post[5]
    text = format_history_post(post, index, len(posts), poster)
    buttons = make_history_buttons(poster_tg_id, posts, index)

    await query.answer()
    try:
        if file_id:
            await query.message.delete()
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=file_id,
                caption=text,
                parse_mode="Markdown",
                reply_markup=buttons
            )
        else:
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=buttons
            )
    except Exception as e:
        logger.error(f"History nav error: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if is_banned(user.id):
        await update.message.reply_text("🚫 You are banned from posting.")
        return

    save_user(user.id, user.first_name, user.username)

    if update.message.text:
        context.user_data["pending_type"] = "text"
        context.user_data["pending_message"] = update.message.text
        context.user_data["pending_file_id"] = None
    elif update.message.photo:
        context.user_data["pending_type"] = "photo"
        context.user_data["pending_message"] = update.message.caption or ""
        context.user_data["pending_file_id"] = update.message.photo[-1].file_id
    else:
        await update.message.reply_text("⚠️ Only text and photos are supported.")
        return

    name_label = user.first_name
    if user.username:
        name_label += f" (@{user.username})"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"📝 Post as {name_label}", callback_data="post_named"),
        InlineKeyboardButton("🕶 Anonymous", callback_data="post_anon"),
    ]])

    await update.message.reply_text("How do you want to post this?", reply_markup=keyboard)


async def handle_post_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    anonymous = query.data == "post_anon"
    message_text = context.user_data.get("pending_message")
    pending_type = context.user_data.get("pending_type", "text")
    file_id = context.user_data.get("pending_file_id")

    if message_text is None:
        await query.edit_message_text("⚠️ Something went wrong. Send your message again.")
        return

    if is_banned(user.id):
        await query.edit_message_text("🚫 You are banned from posting.")
        return

    caption = build_caption(message_text, user.first_name, user.username, user.id, anonymous)

    try:
        if pending_type == "photo" and file_id:
            sent = await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=file_id,
                caption=caption,
                parse_mode="Markdown",
            )
        else:
            sent = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
    except Exception as e:
        logger.error(f"Send failed: {e}")
        await query.edit_message_text("❌ Failed to post. Make sure the bot is an admin in the channel.")
        return

    post_id = save_post(
        user.id, message_text, anonymous, sent.message_id,
        file_id if pending_type == "photo" else None
    )

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID,
            message_id=sent.message_id,
            reply_markup=make_post_buttons(post_id, anonymous=anonymous)
        )
    except Exception as e:
        logger.error(f"Button edit failed: {e}")

    await query.edit_message_text("✅ Posted to the channel!")
    context.user_data.pop("pending_message", None)
    context.user_data.pop("pending_type", None)
    context.user_data.pop("pending_file_id", None)


async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, post_id_str = query.data.split(":")
    post_id = int(post_id_str)

    post = get_post(post_id)
    if not post or post[8] == 1:
        await query.answer("❌ This post no longer exists.", show_alert=True)
        return

    vote = "like" if action == "like" else "dislike"
    likes, dislikes, result = set_vote(post_id, query.from_user.id, vote)

    messages = {
        ("like", "added"):       "👍 Liked!",
        ("like", "removed"):     "👍 Like removed",
        ("like", "switched"):    "👍 Switched to like",
        ("dislike", "added"):    "👎 Disliked!",
        ("dislike", "removed"):  "👎 Dislike removed",
        ("dislike", "switched"): "👎 Switched to dislike",
    }
    await query.answer(messages.get((vote, result), "Done"))

    try:
        await query.edit_message_reply_markup(
            reply_markup=make_post_buttons(post_id, likes, dislikes, anonymous=bool(post[3]))
        )
    except Exception:
        pass


async def handle_report_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    post_id = int(query.data.split(":")[1])

    post = get_post(post_id)
    if not post or post[8] == 1:
        await query.answer("❌ This post no longer exists.", show_alert=True)
        return

    await query.answer()
    try:
        await query.edit_message_reply_markup(
            reply_markup=make_report_buttons(post_id, anonymous=bool(post[3]))
        )
    except Exception:
        pass


async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    post_id = int(query.data.split(":")[1])

    post = get_post(post_id)
    if not post:
        await query.answer()
        return

    await query.answer()
    try:
        await query.edit_message_reply_markup(
            reply_markup=make_post_buttons(post_id, post[5], post[6], anonymous=bool(post[3]))
        )
    except Exception:
        pass


async def handle_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    post_id = int(query.data.split(":")[1])

    post = get_post(post_id)
    if not post or post[8] == 1:
        await query.answer("❌ This post no longer exists.", show_alert=True)
        return

    already, report_count = add_report(post_id, query.from_user.id)

    if already:
        await query.answer("⚠️ You already reported this post.", show_alert=True)
        return

    await query.answer("🚨 Report submitted. Thank you.", show_alert=True)

    try:
        updated_post = get_post(post_id)
        await query.edit_message_reply_markup(
            reply_markup=make_post_buttons(post_id, updated_post[5], updated_post[6], anonymous=bool(post[3]))
        )
    except Exception:
        pass

    poster = get_user(post[1])
    poster_info = "Anonymous" if post[3] else (
        f"{poster[2]} (@{poster[3]})" if poster and poster[3] else
        f"{poster[2] if poster else 'Unknown'} (id:{post[1]})"
    )
    preview = post[2][:100] + ("..." if len(post[2]) > 100 else "")

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🚨 <b>Post Reported</b>\n\n"
            f"Post ID: <code>{post_id}</code>\n"
            f"Posted by: {poster_info}\n"
            f"Reports: <b>{report_count}</b>/{AUTO_DELETE_REPORTS}\n\n"
            f"<i>{preview}</i>\n\n"
            f"Use /deletepost {post_id} to remove it manually."
        ),
        parse_mode="HTML"
    )

    if report_count >= AUTO_DELETE_REPORTS:
        try:
            await context.bot.delete_message(chat_id=CHANNEL_ID, message_id=post[4])
            mark_post_deleted(post_id)
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🗑 Post <code>{post_id}</code> auto-deleted after {AUTO_DELETE_REPORTS} reports.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Auto-delete failed: {e}")


# ─── Admin Commands ───────────────────────────────────────────────────────────

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("⛔ Not authorized.")
            return
        return await func(update, context)
    return wrapper


@admin_only
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users, banned_users, total_posts, anon_posts = get_stats()
    text = (
        "🛠 <b>Admin Panel</b>\n\n"
        f"👥 Total users: <b>{total_users}</b>\n"
        f"🚫 Banned: <b>{banned_users}</b>\n"
        f"📨 Total posts: <b>{total_posts}</b>\n"
        f"🕶 Anonymous: <b>{anon_posts}</b>\n\n"
        "<b>Commands:</b>\n"
        "/ban &lt;id&gt; — Ban user\n"
        "/unban &lt;id&gt; — Unban user\n"
        "/deletepost &lt;id&gt; — Delete a post\n"
        "/users — List all users"
    )
    await update.message.reply_text(text, parse_mode="HTML")


@admin_only
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    try:
        set_ban(int(context.args[0]), True)
        await update.message.reply_text(f"🚫 User {context.args[0]} banned.")
    except ValueError:
        await update.message.reply_text("⚠️ Invalid ID.")


@admin_only
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        set_ban(int(context.args[0]), False)
        await update.message.reply_text(f"✅ User {context.args[0]} unbanned.")
    except ValueError:
        await update.message.reply_text("⚠️ Invalid ID.")


@admin_only
async def delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /deletepost <post_id>")
        return
    try:
        post_id = int(context.args[0])
        post = get_post(post_id)
        if not post:
            await update.message.reply_text("❌ Post not found.")
            return
        await context.bot.delete_message(chat_id=CHANNEL_ID, message_id=post[4])
        mark_post_deleted(post_id)
        await update.message.reply_text(f"🗑 Post {post_id} deleted.")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed: {e}")


@admin_only
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    if not users:
        await update.message.reply_text("No users yet.")
        return
    chunk = ""
    for tg_id, first_name, username, banned, joined_at in users:
        status = "🚫" if banned else "✅"
        uname = f"@{username}" if username else f"id:{tg_id}"
        line = f"{status} {first_name} ({uname}) — {joined_at[:10]}\n"
        if len(chunk) + len(line) > 3800:
            await update.message.reply_text(chunk)
            chunk = ""
        chunk += line
    if chunk:
        await update.message.reply_text(chunk)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("stats", admin_panel))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("deletepost", delete_post))
    app.add_handler(CommandHandler("users", list_users))

    app.add_handler(CallbackQueryHandler(handle_post_choice,  pattern=r"^post_(named|anon)$"))
    app.add_handler(CallbackQueryHandler(handle_vote,         pattern=r"^(like|dislike):\d+$"))
    app.add_handler(CallbackQueryHandler(handle_report_menu,  pattern=r"^reportmenu:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_report,       pattern=r"^report:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_back,         pattern=r"^back:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_history_nav,  pattern=r"^hist:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_history_nav,  pattern=r"^noop$"))

    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()