import mysql.connector
import json
import os
import argparse
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler

# Argument parsing
parser = argparse.ArgumentParser()
parser.add_argument("-d", "--db-config", help="DB config file path", default="/usr/src/app/db_config.json")
parser.add_argument("-e", "--env-file", help="Env file", default="/usr/src/app/.env")
args = parser.parse_args()

# Load environment variables
load_dotenv(args.env_file)
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))

# Load DB config
def load_db_config():
    with open(args.db_config, 'r') as file:
        return json.load(file)
db_config = load_db_config()
db = mysql.connector.connect(**db_config)

# Define conversation states
TASK_PLANNING, TASK_DECISION, TASK_COMPLETION, TASK_DELETION_CONFIRMATION = range(4)

# Global dictionary for pending user requests
pending_requests = {}

def auth_required(admin_only=False):
    def decorator(func):
        def wrapper(update: Update, context: CallbackContext):
            user_id = update.effective_user.id
            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (user_id,))
            user = cursor.fetchone()
            
            if user and (user['is_authorized'] or user['is_admin']):
                if admin_only and user_id != ADMIN_USER_ID:
                    update.message.reply_text("You do not have permission to perform this action.")
                    return
                return func(update, context)
            elif user_id == ADMIN_USER_ID:
                if admin_only:
                    return func(update, context)
                update.message.reply_text("Admin actions are not restricted.")
                return func(update, context)
            else:
                request_admin_approval(update, context)
                return
        return wrapper
    return decorator

def request_admin_approval(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = update.effective_user.username
    pending_requests[user_id] = username
    admin_message = (f"User @{username} (ID: {user_id}) is requesting access to the bot. "
                     "Do you want to approve the access request? (approve/reject)")
    context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_message)
    update.message.reply_text("Your request has been sent to the admin for approval.")

@auth_required()
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Welcome to the Task Manager Bot! Use /plantask to plan your tasks, /completetask to complete your tasks, /listtasks to list tasks planned for the next day, and /deletetasks to delete tasks.")

@auth_required()
def plantask(update: Update, context: CallbackContext):
    update.message.reply_text("Please enter the tasks you plan to complete for the next day, separated by commas.")
    return TASK_PLANNING

def receive_tasks(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    tasks = [task.strip() for task in update.message.text.split(',')]
    cursor = db.cursor()

    cursor.execute("SELECT tasks FROM tasks WHERE user_id = %s AND task_date = CURDATE() + INTERVAL 1 DAY", (user_id,))
    result = cursor.fetchone()

    if result:
        existing_tasks = result[0].split(',')
        context.user_data['new_tasks'] = tasks
        context.user_data['existing_tasks'] = existing_tasks
        update.message.reply_text(f"You already have tasks planned for the next day: {existing_tasks}. Do you want to append the new tasks or reject them? (append/reject)")
        return TASK_DECISION
    else:
        cursor.execute("INSERT INTO tasks (user_id, tasks, task_date) VALUES (%s, %s, CURDATE() + INTERVAL 1 DAY)", (user_id, ','.join(tasks)))
        db.commit()
        update.message.reply_text("Tasks saved successfully.")
        return ConversationHandler.END

def task_decision(update: Update, context: CallbackContext):
    decision = update.message.text.lower()
    user_id = update.effective_user.id
    new_tasks = context.user_data['new_tasks']
    existing_tasks = context.user_data['existing_tasks']

    cursor = db.cursor()

    if decision == 'append':
        updated_tasks = existing_tasks + new_tasks
        cursor.execute("UPDATE tasks SET tasks = %s WHERE user_id = %s AND task_date = CURDATE() + INTERVAL 1 DAY", (','.join(updated_tasks), user_id))
        db.commit()
        update.message.reply_text("Tasks appended successfully.")
    elif decision == 'reject':
        update.message.reply_text("New tasks rejected.")
    else:
        update.message.reply_text("Invalid choice. Please type 'append' or 'reject'.")
    return ConversationHandler.END

@auth_required()
def completetask(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor = db.cursor()
    cursor.execute("SELECT tasks FROM tasks WHERE user_id = %s AND task_date = CURDATE()", (user_id,))
    result = cursor.fetchone()

    if result:
        tasks = result[0].split(',')
        keyboard = [[InlineKeyboardButton(task, callback_data=f"complete_{task}")] for task in tasks]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Please select the tasks you have completed:", reply_markup=reply_markup)
        return TASK_COMPLETION
    else:
        update.message.reply_text("No tasks found for today.")
        return ConversationHandler.END

def mark_task_complete(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data.startswith("complete_"):
        task_to_complete = data[len("complete_"):]
        cursor = db.cursor()
        cursor.execute("SELECT tasks FROM tasks WHERE user_id = %s AND task_date = CURDATE()", (user_id,))
        result = cursor.fetchone()
        tasks = result[0].split(',')

        if task_to_complete in tasks:
            tasks.remove(task_to_complete)
            cursor.execute("UPDATE tasks SET tasks = %s WHERE user_id = %s AND task_date = CURDATE()", (','.join(tasks), user_id))
            db.commit()
            query.edit_message_text(text=f"Task '{task_to_complete}' marked as complete.")
        else:
            query.edit_message_text(text=f"Task '{task_to_complete}' not found.")
    else:
        query.edit_message_text(text="Invalid task selection.")

@auth_required()
def listtasks(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor = db.cursor()
    cursor.execute("SELECT tasks FROM tasks WHERE user_id = %s AND task_date = CURDATE() + INTERVAL 1 DAY", (user_id,))
    result = cursor.fetchone()

    if result:
        tasks = result[0].split(',')
        tasks_list = "\n".join(tasks)
        update.message.reply_text(f"Tasks planned for the next day:\n{tasks_list}")
    else:
        update.message.reply_text("No tasks found for the next day.")

@auth_required()
def deletetasks(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor = db.cursor()
    cursor.execute("SELECT tasks FROM tasks WHERE user_id = %s AND task_date = CURDATE() + INTERVAL 1 DAY", (user_id,))
    result = cursor.fetchone()

    if result:
        tasks = result[0].split(',')
        keyboard = [[InlineKeyboardButton(task, callback_data=f"delete_{task}")] for task in tasks]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Select the tasks you want to delete:", reply_markup=reply_markup)
        return TASK_DELETION_CONFIRMATION
    else:
        update.message.reply_text("No tasks found for the next day.")
        return ConversationHandler.END

def confirm_delete_task(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data.startswith("delete_"):
        task_to_delete = data[len("delete_"):]
        cursor = db.cursor()
        cursor.execute("SELECT tasks FROM tasks WHERE user_id = %s AND task_date = CURDATE() + INTERVAL 1 DAY", (user_id,))
        result = cursor.fetchone()
        tasks = result[0].split(',')

        if task_to_delete in tasks:
            tasks.remove(task_to_delete)
            cursor.execute("UPDATE tasks SET tasks = %s WHERE user_id = %s AND task_date = CURDATE() + INTERVAL 1 DAY", (','.join(tasks), user_id))
            db.commit()
            query.edit_message_text(text=f"Task '{task_to_delete}' has been deleted.")
        else:
            query.edit_message_text(text=f"Task '{task_to_delete}' not found.")
    else:
        query.edit_message_text(text="Invalid task selection.")

def approve_user(update: Update, context: CallbackContext, user_id, username):
    cursor = db.cursor()
    cursor.execute("INSERT INTO users (telegram_id, username, is_authorized) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE is_authorized = VALUES(is_authorized)", (user_id, username, True))
    db.commit()
    context.bot.send_message(chat_id=user_id, text="Your request has been approved. You can now use the bot.")
    context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"User {user_id} has been approved.")
    del pending_requests[user_id]

def reject_user(update: Update, context: CallbackContext, user_id):
    if user_id in pending_requests:
        context.bot.send_message(chat_id=user_id, text="Your request has been rejected.")
        context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"User {user_id} has been rejected.")
        del pending_requests[user_id]

def handle_admin_response(update: Update, context: CallbackContext):
    decision = update.message.text.lower()
    if pending_requests:
        user_id, username = next(iter(pending_requests.items()))
        if decision == 'approve':
            approve_user(update, context, user_id, username)
        elif decision == 'reject':
            reject_user(update, context, user_id)
        else:
            update.message.reply_text("Invalid choice. Please type 'approve' or 'reject'.")
    else:
        update.message.reply_text("No pending user requests.")

@auth_required(admin_only=True)
def list_users(update: Update, context: CallbackContext):
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    user_list = "\n".join([f"ID: {user['telegram_id']}, Username: {user['username']}, Authorized: {user['is_authorized']}, Admin: {user['is_admin']}" for user in users])
    update.message.reply_text(f"Users in the system:\n{user_list}")

@auth_required(admin_only=True)
def revoke_user(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Please provide the user ID to revoke. Usage: /revokeuser <user_id>")
        return
    user_id = int(context.args[0])
    cursor = db.cursor()
    cursor.execute("DELETE FROM users WHERE telegram_id = %s", (user_id,))
    db.commit()
    update.message.reply_text(f"User {user_id} has been revoked.")
    context.bot.send_message(chat_id=user_id, text="Your access to the bot has been revoked.")

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    task_planning_conv = ConversationHandler(
        entry_points=[CommandHandler('plantask', plantask)],
        states={
            TASK_PLANNING: [MessageHandler(Filters.text & ~Filters.command, receive_tasks)],
            TASK_DECISION: [MessageHandler(Filters.text & ~Filters.command, task_decision)]
        },
        fallbacks=[]
    )

    task_completion_conv = ConversationHandler(
        entry_points=[CommandHandler('completetask', completetask)],
        states={
            TASK_COMPLETION: [CallbackQueryHandler(mark_task_complete)]
        },
        fallbacks=[]
    )

    task_deletion_conv = ConversationHandler(
        entry_points=[CommandHandler('deletetasks', deletetasks)],
        states={
            TASK_DELETION_CONFIRMATION: [CallbackQueryHandler(confirm_delete_task)]
        },
        fallbacks=[]
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(task_planning_conv)
    dp.add_handler(task_completion_conv)
    dp.add_handler(task_deletion_conv)
    dp.add_handler(CommandHandler("listtasks", listtasks))
    dp.add_handler(CommandHandler("listusers", list_users))
    dp.add_handler(CommandHandler("revokeuser", revoke_user))
    dp.add_handler(MessageHandler(Filters.text & Filters.chat(ADMIN_USER_ID), handle_admin_response))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()

