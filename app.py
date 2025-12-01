import os
import threading
import time
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters
from pymongo import MongoClient
from datetime import datetime, timedelta
import bcrypt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB Connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['expense_tracker']
users_collection = db['users']
expenses_collection = db['expenses']

# Admin credentials
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

# Conversation states
EMAIL, PASSWORD, REGISTER_EMAIL, REGISTER_PASSWORD = range(4)
ADD_AMOUNT, ADD_REASON, ADD_DATE = range(4, 7)
EDIT_AMOUNT, EDIT_REASON, EDIT_DATE = range(7, 10)
DELETE_START_DATE, DELETE_END_DATE = range(10, 12)

# Hash password
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

# [ALL YOUR EXISTING HANDLERS - EXACTLY AS BEFORE]
# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Sign In", callback_data='signin')],
        [InlineKeyboardButton("Sign Up", callback_data='signup')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        '💰 *Welcome to Expense Tracker Bot!*\n\n'
        'Track your daily expenses with ease.',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# Button handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'signin':
        await query.edit_message_text('📧 Please enter your email:')
        return EMAIL
    
    elif query.data == 'signup':
        await query.edit_message_text('📧 Please enter your email for registration:')
        return REGISTER_EMAIL
    
    elif query.data == 'main_menu':
        await show_main_menu(query, context)
        return ConversationHandler.END
    
    elif query.data == 'add_expense':
        await query.edit_message_text('💵 Enter the amount spent:')
        return ADD_AMOUNT
    
    elif query.data == 'view_dashboard':
        await show_dashboard(query, context)
        return ConversationHandler.END
    
    elif query.data == 'edit_expense':
        await show_expenses_for_edit(query, context)
        return ConversationHandler.END
    
    elif query.data == 'delete_expense':
        await show_expenses_for_delete(query, context)
        return ConversationHandler.END
    
    elif query.data == 'delete_range':
        await query.edit_message_text('📅 Enter start date (YYYY-MM-DD):')
        return DELETE_START_DATE
    
    elif query.data == 'admin_panel':
        await show_admin_panel(query, context)
        return ConversationHandler.END
    
    elif query.data == 'logout':
        context.user_data.clear()
        keyboard = [
            [InlineKeyboardButton("Sign In", callback_data='signin')],
            [InlineKeyboardButton("Sign Up", callback_data='signup')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            '👋 *Logged out successfully!*\n\nSee you next time!',
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
    elif query.data.startswith('clearuser_'):
        user_id = query.data.replace('clearuser_', '', 1)
        is_admin = context.user_data.get('is_admin', False)
        
        if is_admin:
            result = expenses_collection.delete_many({'user_id': user_id})
            user = users_collection.find_one({'_id': user_id})
            user_email = user['email'] if user else 'Unknown'
            
            await query.answer(f"✅ Cleared {result.deleted_count} expenses for {user_email}")
            await show_admin_panel(query, context)
        return ConversationHandler.END
    
    elif query.data == 'admin_back':
        await show_admin_menu_callback(query, context)
        return ConversationHandler.END
    
    elif query.data.startswith('edit_'):
        expense_id = query.data.replace('edit_', '', 1)
        context.user_data['edit_expense_id'] = expense_id
        await query.edit_message_text('💵 Enter new amount:')
        return EDIT_AMOUNT
    
    elif query.data.startswith('del_'):
        expense_id = query.data.replace('del_', '', 1)
        expenses_collection.delete_one({'_id': expense_id})
        await query.edit_message_text('✅ Expense deleted successfully!')
        await show_main_menu(query, context)
        return ConversationHandler.END

# [CONTINUE WITH ALL OTHER HANDLERS: email_handler, password_handler, etc. - COPY FROM YOUR ORIGINAL CODE]
# Sign In Flow
async def email_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    context.user_data['email'] = email
    await update.message.reply_text('🔒 Please enter your password:')
    return PASSWORD

async def password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = context.user_data.get('email')
    password = update.message.text.strip()
    
    # Check admin login
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        context.user_data['user_id'] = 'admin'
        context.user_data['is_admin'] = True
        await update.message.reply_text('✅ Admin login successful!')
        await show_admin_menu(update, context)
        return ConversationHandler.END
    
    # Check regular user
    user = users_collection.find_one({'email': email})
    if user and verify_password(password, user['password']):
        context.user_data['user_id'] = str(user['_id'])
        context.user_data['is_admin'] = False
        await update.message.reply_text(f'✅ Welcome back, {user["email"]}!')
        await show_main_menu_message(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text('❌ Invalid credentials. Try /start again.')
        return ConversationHandler.END

# Sign Up Flow
async def register_email_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    
    if users_collection.find_one({'email': email}):
        await update.message.reply_text('❌ Email already exists. Try /start to sign in.')
        return ConversationHandler.END
    
    context.user_data['register_email'] = email
    await update.message.reply_text('🔒 Create a password:')
    return REGISTER_PASSWORD

async def register_password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = context.user_data.get('register_email')
    password = update.message.text.strip()
    
    hashed = hash_password(password)
    user_id = users_collection.insert_one({
        'email': email,
        'password': hashed,
        'created_at': datetime.now()
    }).inserted_id
    
    context.user_data['user_id'] = str(user_id)
    context.user_data['is_admin'] = False
    
    await update.message.reply_text('✅ Registration successful!')
    await show_main_menu_message(update, context)
    return ConversationHandler.END

# Main Menu
async def show_main_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Add Expense", callback_data='add_expense')],
        [InlineKeyboardButton("📊 View Dashboard", callback_data='view_dashboard')],
        [InlineKeyboardButton("✏️ Edit Expense", callback_data='edit_expense')],
        [InlineKeyboardButton("🗑 Delete Expense", callback_data='delete_expense')],
        [InlineKeyboardButton("🗑 Delete Date Range", callback_data='delete_range')],
        [InlineKeyboardButton("🚪 Logout", callback_data='logout')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('📱 *Main Menu*', parse_mode='Markdown', reply_markup=reply_markup)

async def show_main_menu(query, context):
    keyboard = [
        [InlineKeyboardButton("➕ Add Expense", callback_data='add_expense')],
        [InlineKeyboardButton("📊 View Dashboard", callback_data='view_dashboard')],
        [InlineKeyboardButton("✏️ Edit Expense", callback_data='edit_expense')],
        [InlineKeyboardButton("🗑 Delete Expense", callback_data='delete_expense')],
        [InlineKeyboardButton("🗑 Delete Date Range", callback_data='delete_range')],
        [InlineKeyboardButton("🚪 Logout", callback_data='logout')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('📱 *Main Menu*', parse_mode='Markdown', reply_markup=reply_markup)

async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👥 View Users & Manage", callback_data='admin_panel')],
        [InlineKeyboardButton("🚪 Logout", callback_data='logout')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('👑 *Admin Panel*', parse_mode='Markdown', reply_markup=reply_markup)

# Add Expense Flow
async def add_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        context.user_data['add_amount'] = amount
        await update.message.reply_text('📝 Enter the reason for spending:')
        return ADD_REASON
    except ValueError:
        await update.message.reply_text('❌ Invalid amount. Please enter a number.')
        return ADD_AMOUNT

async def add_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text.strip()
    if not reason:
        reason = "No reason"
    context.user_data['add_reason'] = reason
    await update.message.reply_text('📅 Enter the date (YYYY-MM-DD) or type "today":')
    return ADD_DATE

async def add_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = update.message.text.strip().lower()
    
    if date_str == 'today':
        date = datetime.now()
    else:
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            await update.message.reply_text('❌ Invalid date format. Use YYYY-MM-DD.')
            return ADD_DATE
    
    user_id = context.user_data.get('user_id')
    amount = context.user_data.get('add_amount')
    reason = context.user_data.get('add_reason')
    
    expenses_collection.insert_one({
        '_id': f"{user_id}_{datetime.now().timestamp()}",
        'user_id': user_id,
        'amount': amount,
        'reason': reason,
        'date': date,
        'created_at': datetime.now()
    })
    
    await update.message.reply_text(f'✅ Expense added: ₹{amount} for {reason} on {date.strftime("%Y-%m-%d")}')
    await show_main_menu_message(update, context)
    return ConversationHandler.END

# Dashboard
async def show_dashboard(query, context):
    user_id = context.user_data.get('user_id')
    expenses = list(expenses_collection.find({'user_id': user_id}).sort('date', -1))
    
    if not expenses:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('📊 No expenses recorded yet.', reply_markup=reply_markup)
        return
    
    total = sum(e['amount'] for e in expenses)
    
    message = f"📊 *Expense Dashboard*\n\n💰 Total Spent: ₹{total:.2f}\n\n"
    
    for exp in expenses[:10]:
        if isinstance(exp['date'], str):
            date_str = exp['date']
        else:
            date_str = exp['date'].strftime('%Y-%m-%d')
        reason = exp.get('reason', 'No reason')
        message += f"• {date_str}: ₹{exp['amount']:.2f} - {reason}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

# [INCLUDE ALL REMAINING HANDLERS: show_expenses_for_edit, edit_amount_handler, etc. - COPY FROM ORIGINAL]
# Edit Expense
async def show_expenses_for_edit(query, context):
    user_id = context.user_data.get('user_id')
    expenses = list(expenses_collection.find({'user_id': user_id}).sort('date', -1).limit(10))
    
    if not expenses:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('No expenses to edit.', reply_markup=reply_markup)
        return
    
    keyboard = []
    for exp in expenses:
        if isinstance(exp['date'], str):
            date_str = exp['date']
        else:
            date_str = exp['date'].strftime('%Y-%m-%d')
        reason = exp.get('reason', 'No reason')[:20]
        keyboard.append([InlineKeyboardButton(
            f"{date_str}: ₹{exp['amount']} - {reason}", 
            callback_data=f"edit_{exp['_id']}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='main_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('✏️ Select expense to edit:', reply_markup=reply_markup)

async def edit_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        context.user_data['edit_amount'] = amount
        await update.message.reply_text('📝 Enter new reason:')
        return EDIT_REASON
    except ValueError:
        await update.message.reply_text('❌ Invalid amount.')
        return EDIT_AMOUNT

async def edit_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text.strip()
    if not reason:
        reason = "No reason"
    context.user_data['edit_reason'] = reason
    await update.message.reply_text('📅 Enter new date (YYYY-MM-DD):')
    return EDIT_DATE

async def edit_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date = datetime.strptime(update.message.text.strip(), '%Y-%m-%d')
        expense_id = context.user_data.get('edit_expense_id')
        
        expenses_collection.update_one(
            {'_id': expense_id},
            {'$set': {
                'amount': context.user_data.get('edit_amount'),
                'reason': context.user_data.get('edit_reason'),
                'date': date
            }}
        )
        
        await update.message.reply_text('✅ Expense updated successfully!')
        await show_main_menu_message(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text('❌ Invalid date format.')
        return EDIT_DATE

# Delete Expense
async def show_expenses_for_delete(query, context):
    user_id = context.user_data.get('user_id')
    expenses = list(expenses_collection.find({'user_id': user_id}).sort('date', -1).limit(10))
    
    if not expenses:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('No expenses to delete.', reply_markup=reply_markup)
        return
    
    keyboard = []
    for exp in expenses:
        if isinstance(exp['date'], str):
            date_str = exp['date']
        else:
            date_str = exp['date'].strftime('%Y-%m-%d')
        reason = exp.get('reason', 'No reason')[:20]
        keyboard.append([InlineKeyboardButton(
            f"{date_str}: ₹{exp['amount']} - {reason}", 
            callback_data=f"del_{exp['_id']}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='main_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('🗑 Select expense to delete:', reply_markup=reply_markup)

# Delete Date Range
async def delete_start_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        start_date = datetime.strptime(update.message.text.strip(), '%Y-%m-%d')
        context.user_data['delete_start_date'] = start_date
        await update.message.reply_text('📅 Enter end date (YYYY-MM-DD):')
        return DELETE_END_DATE
    except ValueError:
        await update.message.reply_text('❌ Invalid date format.')
        return DELETE_START_DATE

async def delete_end_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        end_date = datetime.strptime(update.message.text.strip(), '%Y-%m-%d')
        start_date = context.user_data.get('delete_start_date')
        user_id = context.user_data.get('user_id')
        
        result = expenses_collection.delete_many({
            'user_id': user_id,
            'date': {'$gte': start_date, '$lte': end_date}
        })
        
        await update.message.reply_text(f'✅ Deleted {result.deleted_count} expenses.')
        await show_main_menu_message(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text('❌ Invalid date format.')
        return DELETE_END_DATE

# Admin Panel
async def show_admin_panel(query, context):
    users = list(users_collection.find())
    
    if not users:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='admin_back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('👥 No users registered yet.', reply_markup=reply_markup)
        return
    
    message = f"👥 *User Management*\n\n📊 Total Users: {len(users)}\n\n"
    
    keyboard = []
    for user in users:
        user_expenses = list(expenses_collection.find({'user_id': str(user['_id'])}))
        total_spent = sum(e['amount'] for e in user_expenses)
        expense_count = len(user_expenses)
        
        message += f"• {user['email']}\n  ₹{total_spent:.2f} ({expense_count} expenses)\n\n"
        
        keyboard.append([InlineKeyboardButton(
            f"🗑 Clear: {user['email'][:25]}", 
            callback_data=f"clearuser_{user['_id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='admin_back')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

async def show_admin_menu_callback(query, context):
    keyboard = [
        [InlineKeyboardButton("👥 View Users & Manage", callback_data='admin_panel')],
        [InlineKeyboardButton("🚪 Logout", callback_data='logout')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('👑 *Admin Panel*', parse_mode='Markdown', reply_markup=reply_markup)

# Cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('❌ Operation cancelled. Use /start to begin again.')
    return ConversationHandler.END

# =====================================================================
# FIXED MAIN: FLASK IN THREAD, BOT POLLING IN MAIN THREAD (NO ERRORS)
# =====================================================================

def run_flask():
    """Flask health check in background thread (for Render port detection)."""
    flask_app = Flask(__name__)

    @flask_app.route('/', defaults={'path': ''})
    @flask_app.route('/<path:path>')
    def catch_all(path):
        return "🤖 Expense Tracker Bot is live on Render! 💰"

    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def main():
    # Start Flask in daemon thread FIRST (non-blocking)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🌐 Flask health server started on $PORT")

    # NOW run bot polling in MAIN thread (safe, no signal errors)
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not found!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(button_handler)  # Global button handling
        ],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_handler)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_handler)],
            REGISTER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email_handler)],
            REGISTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password_handler)],
            ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_amount_handler)],
            ADD_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_reason_handler)],
            ADD_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_date_handler)],
            EDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_amount_handler)],
            EDIT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_reason_handler)],
            EDIT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_date_handler)],
            DELETE_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_start_date_handler)],
            DELETE_END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_end_date_handler)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(button_handler)
        ],
        allow_reentry=True,
        per_message=False  # Harmless warning - ignore
    )

    application.add_handler(conv_handler)

    print("🤖 Bot polling started in main thread...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
