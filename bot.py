import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters
from pymongo import MongoClient
from datetime import datetime
import bcrypt
from dotenv import load_dotenv
import pandas as pd
from io import BytesIO
from bson import ObjectId  # IMPORTED TO FIX ID MATCHING ISSUES
from flask import Flask
from threading import Thread

# Load environment variables
load_dotenv()

# MongoDB Connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://bookhiversd:8D6pLujBM9rLVi8B@bookhive.7h76ryz.mongodb.net/ExpenseTrackerManage?retryWrites=true&w=majority&appName=BookHive')
client = MongoClient(MONGO_URI)
db = client['expense_tracker']
users_collection = db['users']
expenses_collection = db['expenses']
groups_collection = db['groups']

# Admin credentials
ADMIN_EMAIL = "bookhive.rsd@gmail.com"
ADMIN_PASSWORD = "bookhive.rsd123"

# Conversation states
EMAIL, PASSWORD, REGISTER_EMAIL, REGISTER_PASSWORD = range(4)
ADD_AMOUNT, ADD_REASON, ADD_DATE, ADD_GROUP = range(4, 8)
EDIT_AMOUNT, EDIT_REASON, EDIT_DATE, EDIT_GROUP = range(8, 12)
DELETE_START_DATE, DELETE_END_DATE = range(12, 14)
CREATE_GROUP_NAME = 14
EXPORT_START_DATE, EXPORT_END_DATE = range(15, 17)

# Hash password
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

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

# Button handler - MAIN callback handler
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
    
    elif query.data == 'manage_groups':
        await show_groups_menu(query, context)
        return ConversationHandler.END
    
    elif query.data == 'create_group':
        await query.edit_message_text('📝 Enter group name (e.g., Goa Trip, Office, Gym):')
        return CREATE_GROUP_NAME
    
    elif query.data == 'view_groups':
        await show_all_groups(query, context)
        return ConversationHandler.END
    
    elif query.data == 'export_menu':
        await show_export_menu(query, context)
        return ConversationHandler.END
    
    elif query.data == 'export_monthly':
        await export_monthly_report(query, context)
        return ConversationHandler.END
    
    elif query.data == 'export_quarterly':
        await export_quarterly_report(query, context)
        return ConversationHandler.END
    
    elif query.data == 'export_yearly':
        await export_yearly_report(query, context)
        return ConversationHandler.END
    
    elif query.data == 'export_custom':
        await query.edit_message_text('📅 Enter start date for export (YYYY-MM-DD):')
        return EXPORT_START_DATE
    
    elif query.data == 'export_all':
        await export_all_report(query, context)
        return ConversationHandler.END
    
    elif query.data.startswith('viewgroup_'):
        group_id = query.data.replace('viewgroup_', '', 1)
        await show_group_details(query, context, group_id)
        return ConversationHandler.END
    
    elif query.data.startswith('delgroup_'):
        group_id = query.data.replace('delgroup_', '', 1)
        await delete_group(query, context, group_id)
        return ConversationHandler.END
    
    elif query.data.startswith('exportgroup_'):
        group_id = query.data.replace('exportgroup_', '', 1)
        await export_group_report(query, context, group_id)
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
        user_id_str = query.data.replace('clearuser_', '', 1)
        is_admin = context.user_data.get('is_admin', False)
        
        if is_admin:
            # Delete expenses (stored with string user_id)
            result = expenses_collection.delete_many({'user_id': user_id_str})
            
            # Find user details (User ID is ObjectId)
            try:
                user = users_collection.find_one({'_id': ObjectId(user_id_str)})
                user_email = user['email'] if user else 'Unknown'
            except:
                user_email = 'Unknown'
            
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
        # Expenses use custom string IDs, so this is fine
        expenses_collection.delete_one({'_id': expense_id})
        await query.edit_message_text('✅ Expense deleted successfully!')
        await show_main_menu(query, context)
        return ConversationHandler.END
    
    # Handle group selection for adding expense
    elif query.data.startswith('selectgroup_') or query.data == 'skipgroup':
        return await handle_group_selection_callback(query, context)
    
    # Handle group selection for editing expense
    elif query.data.startswith('editselgroup_') or query.data == 'editskipgroup':
        return await handle_edit_group_selection_callback(query, context)

# New function to handle group selection callback
async def handle_group_selection_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle group selection after choosing a group or skipping"""
    user_id = context.user_data.get('user_id')
    amount = context.user_data.get('add_amount')
    reason = context.user_data.get('add_reason')
    date = context.user_data.get('add_date')
    
    if not all([user_id, amount, reason, date]):
        await query.edit_message_text('❌ Error: Missing expense data. Please try again.')
        await show_main_menu(query, context)
        return ConversationHandler.END
    
    expense_data = {
        '_id': f"{user_id}_{datetime.now().timestamp()}",
        'user_id': user_id,
        'amount': amount,
        'reason': reason,
        'date': date,
        'created_at': datetime.now()
    }
    
    group_msg = ""
    if query.data.startswith('selectgroup_'):
        group_id_str = query.data.replace('selectgroup_', '', 1)
        expense_data['group_id'] = group_id_str
        
        # FIX: Convert to ObjectId for Lookup
        try:
            group = groups_collection.find_one({'_id': ObjectId(group_id_str)})
            group_name = group['name'] if group else 'Unknown'
            group_msg = f" in group '{group_name}'"
        except Exception:
            group_msg = " in group (Error)"
    
    expenses_collection.insert_one(expense_data)
    
    await query.edit_message_text(f'✅ Expense added: ₹{amount} for {reason} on {date.strftime("%Y-%m-%d")}{group_msg}')
    await show_main_menu(query, context)
    return ConversationHandler.END

# New function to handle edit group selection callback
async def handle_edit_group_selection_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle group selection when editing an expense"""
    expense_id = context.user_data.get('edit_expense_id')
    update_data = {
        'amount': context.user_data.get('edit_amount'),
        'reason': context.user_data.get('edit_reason'),
        'date': context.user_data.get('edit_date')
    }
    
    if query.data.startswith('editselgroup_'):
        group_id = query.data.replace('editselgroup_', '', 1)
        update_data['group_id'] = group_id
    else:
        # Remove group if "No Group" selected
        expenses_collection.update_one(
            {'_id': expense_id},
            {'$unset': {'group_id': ''}}
        )
    
    expenses_collection.update_one(
        {'_id': expense_id},
        {'$set': update_data}
    )
    
    await query.edit_message_text('✅ Expense updated successfully!')
    await show_main_menu(query, context)
    return ConversationHandler.END

# Separate handler for group selection (for the ConversationHandler)
async def group_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for group selection in conversation flow"""
    query = update.callback_query
    await query.answer()
    
    # Process based on the callback data
    if query.data.startswith('selectgroup_') or query.data == 'skipgroup':
        return await handle_group_selection_callback(query, context)
    elif query.data.startswith('editselgroup_') or query.data == 'editskipgroup':
        return await handle_edit_group_selection_callback(query, context)
    
    return ConversationHandler.END

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
        [InlineKeyboardButton("📁 Manage Groups", callback_data='manage_groups')],
        [InlineKeyboardButton("📥 Export Reports", callback_data='export_menu')],
        [InlineKeyboardButton("✏️ Edit Expense", callback_data='edit_expense')],
        [InlineKeyboardButton("🗑 Delete Expense", callback_data='delete_expense')],
        [InlineKeyboardButton("🗓 Delete Date Range", callback_data='delete_range')],
        [InlineKeyboardButton("🚪 Logout", callback_data='logout')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('📱 *Main Menu*', parse_mode='Markdown', reply_markup=reply_markup)

async def show_main_menu(query, context):
    keyboard = [
        [InlineKeyboardButton("➕ Add Expense", callback_data='add_expense')],
        [InlineKeyboardButton("📊 View Dashboard", callback_data='view_dashboard')],
        [InlineKeyboardButton("📁 Manage Groups", callback_data='manage_groups')],
        [InlineKeyboardButton("📥 Export Reports", callback_data='export_menu')],
        [InlineKeyboardButton("✏️ Edit Expense", callback_data='edit_expense')],
        [InlineKeyboardButton("🗑 Delete Expense", callback_data='delete_expense')],
        [InlineKeyboardButton("🗓 Delete Date Range", callback_data='delete_range')],
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

# Groups Management
async def show_groups_menu(query, context):
    keyboard = [
        [InlineKeyboardButton("➕ Create New Group", callback_data='create_group')],
        [InlineKeyboardButton("📂 View All Groups", callback_data='view_groups')],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('📁 *Groups Management*\n\nOrganize expenses by groups (trips, projects, etc.)', parse_mode='Markdown', reply_markup=reply_markup)

async def create_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_name = update.message.text.strip()
    user_id = context.user_data.get('user_id')
    
    if not group_name:
        await update.message.reply_text('❌ Group name cannot be empty.')
        return CREATE_GROUP_NAME
    
    group_id = groups_collection.insert_one({
        'user_id': user_id,
        'name': group_name,
        'created_at': datetime.now()
    }).inserted_id
    
    await update.message.reply_text(f'✅ Group "{group_name}" created successfully!')
    await show_main_menu_message(update, context)
    return ConversationHandler.END

async def show_all_groups(query, context):
    user_id = context.user_data.get('user_id')
    groups = list(groups_collection.find({'user_id': user_id}))
    
    if not groups:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='manage_groups')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('📂 No groups created yet.\n\nCreate groups to organize your expenses!', reply_markup=reply_markup)
        return
    
    message = "📂 *Your Groups*\n\n"
    keyboard = []
    
    for group in groups:
        # Note: expense stored group_id as String
        group_expenses = list(expenses_collection.find({'user_id': user_id, 'group_id': str(group['_id'])}))
        total = sum(e['amount'] for e in group_expenses)
        count = len(group_expenses)
        
        message += f"• {group['name']}: ₹{total:.2f} ({count} expenses)\n"
        keyboard.append([
            InlineKeyboardButton(f"👁 {group['name']}", callback_data=f"viewgroup_{group['_id']}"),
            InlineKeyboardButton("📥", callback_data=f"exportgroup_{group['_id']}"),
            InlineKeyboardButton("🗑", callback_data=f"delgroup_{group['_id']}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='manage_groups')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

async def show_group_details(query, context, group_id_str):
    user_id = context.user_data.get('user_id')
    
    # FIX: Convert string to ObjectId
    try:
        group = groups_collection.find_one({'_id': ObjectId(group_id_str), 'user_id': user_id})
    except:
        group = None
    
    if not group:
        await query.edit_message_text('❌ Group not found.')
        return
    
    # Expenses store group_id as string
    expenses = list(expenses_collection.find({'user_id': user_id, 'group_id': group_id_str}).sort('date', -1))
    
    if not expenses:
        message = f"📂 *{group['name']}*\n\nNo expenses in this group yet."
    else:
        total = sum(e['amount'] for e in expenses)
        message = f"📂 *{group['name']}*\n\n💰 Total: ₹{total:.2f}\n📊 Expenses: {len(expenses)}\n\n"
        
        for exp in expenses[:10]:
            if isinstance(exp['date'], str):
                date_str = exp['date']
            else:
                date_str = exp['date'].strftime('%Y-%m-%d')
            reason = exp.get('reason', 'No reason')
            message += f"• {date_str}: ₹{exp['amount']:.2f} - {reason}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Groups", callback_data='view_groups')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

async def delete_group(query, context, group_id_str):
    user_id = context.user_data.get('user_id')
    
    # FIX: Use ObjectId
    try:
        group_oid = ObjectId(group_id_str)
        group = groups_collection.find_one({'_id': group_oid, 'user_id': user_id})
        
        if group:
            groups_collection.delete_one({'_id': group_oid})
            # Don't delete expenses, just remove group reference
            expenses_collection.update_many(
                {'user_id': user_id, 'group_id': group_id_str},
                {'$unset': {'group_id': ''}}
            )
            await query.answer(f"✅ Group '{group['name']}' deleted!")
    except Exception as e:
        await query.answer("Error deleting group.")
    
    await show_all_groups(query, context)

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
    
    context.user_data['add_date'] = date
    
    # Show groups selection
    user_id = context.user_data.get('user_id')
    groups = list(groups_collection.find({'user_id': user_id}))
    
    keyboard = [[InlineKeyboardButton("⏭ Skip (No Group)", callback_data='skipgroup')]]
    for group in groups[:10]:
        keyboard.append([InlineKeyboardButton(f"📁 {group['name']}", callback_data=f"selectgroup_{group['_id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('📁 Select a group (optional):', reply_markup=reply_markup)
    return ADD_GROUP

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
        
        group_tag = ""
        if 'group_id' in exp:
            try:
                # FIX: Convert string group_id from expense to ObjectId for group lookup
                group = groups_collection.find_one({'_id': ObjectId(exp['group_id'])})
                if group:
                    group_tag = f" [{group['name']}]"
            except:
                pass
        
        message += f"• {date_str}: ₹{exp['amount']:.2f} - {reason}{group_tag}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

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
        context.user_data['edit_date'] = date
        
        # Show groups selection
        user_id = context.user_data.get('user_id')
        groups = list(groups_collection.find({'user_id': user_id}))
        
        keyboard = [[InlineKeyboardButton("⏭ No Group", callback_data='editskipgroup')]]
        for group in groups[:10]:
            keyboard.append([InlineKeyboardButton(f"📁 {group['name']}", callback_data=f"editselgroup_{group['_id']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('📁 Select a group (optional):', reply_markup=reply_markup)
        return EDIT_GROUP
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

# Export Reports
async def show_export_menu(query, context):
    keyboard = [
        [InlineKeyboardButton("📅 This Month", callback_data='export_monthly')],
        [InlineKeyboardButton("📊 This Quarter", callback_data='export_quarterly')],
        [InlineKeyboardButton("📈 This Year", callback_data='export_yearly')],
        [InlineKeyboardButton("🗓 Custom Date Range", callback_data='export_custom')],
        [InlineKeyboardButton("📋 All Expenses", callback_data='export_all')],
        [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('📥 *Export Reports*\n\nSelect report type:', parse_mode='Markdown', reply_markup=reply_markup)

def create_excel_report(expenses, groups_dict):
    """Create Excel file from expenses data"""
    data = []
    for exp in expenses:
        if isinstance(exp['date'], str):
            date_str = exp['date']
        else:
            date_str = exp['date'].strftime('%Y-%m-%d')
        
        group_name = ""
        # exp['group_id'] is a string, and groups_dict keys are strings
        if 'group_id' in exp and exp['group_id'] in groups_dict:
            group_name = groups_dict[exp['group_id']]
        
        data.append({
            'Date': date_str,
            'Amount': exp['amount'],
            'Reason': exp.get('reason', 'No reason'),
            'Group': group_name
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Expenses', index=False)
        
        # Add summary sheet
        if not df.empty:
            summary_data = {
                'Metric': ['Total Expenses', 'Total Amount', 'Average Amount'],
                'Value': [len(expenses), df['Amount'].sum(), df['Amount'].mean()]
            }
        else:
            summary_data = {'Metric': ['Total'], 'Value': [0]}
            
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
    
    output.seek(0)
    return output

async def export_monthly_report(query, context):
    user_id = context.user_data.get('user_id')
    now = datetime.now()
    start_of_month = datetime(now.year, now.month, 1)
    
    expenses = list(expenses_collection.find({
        'user_id': user_id,
        'date': {'$gte': start_of_month}
    }).sort('date', -1))
    
    if not expenses:
        await query.answer("No expenses found for this month!")
        return
    
    # Get groups (Keys as Strings)
    groups = {str(g['_id']): g['name'] for g in groups_collection.find({'user_id': user_id})}
    
    excel_file = create_excel_report(expenses, groups)
    
    await query.answer("Generating report...")
    await query.message.reply_document(
        document=excel_file,
        filename=f"expenses_monthly_{now.strftime('%Y-%m')}.xlsx",
        caption=f"📊 Monthly Report - {now.strftime('%B %Y')}\n💰 Total: ₹{sum(e['amount'] for e in expenses):.2f}"
    )
    await show_main_menu(query, context)

async def export_quarterly_report(query, context):
    user_id = context.user_data.get('user_id')
    now = datetime.now()
    quarter = (now.month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    start_of_quarter = datetime(now.year, start_month, 1)
    
    expenses = list(expenses_collection.find({
        'user_id': user_id,
        'date': {'$gte': start_of_quarter}
    }).sort('date', -1))
    
    if not expenses:
        await query.answer("No expenses found for this quarter!")
        return
    
    groups = {str(g['_id']): g['name'] for g in groups_collection.find({'user_id': user_id})}
    excel_file = create_excel_report(expenses, groups)
    
    await query.answer("Generating report...")
    await query.message.reply_document(
        document=excel_file,
        filename=f"expenses_Q{quarter}_{now.year}.xlsx",
        caption=f"📊 Q{quarter} {now.year} Report\n💰 Total: ₹{sum(e['amount'] for e in expenses):.2f}"
    )
    await show_main_menu(query, context)

async def export_yearly_report(query, context):
    user_id = context.user_data.get('user_id')
    now = datetime.now()
    start_of_year = datetime(now.year, 1, 1)
    
    expenses = list(expenses_collection.find({
        'user_id': user_id,
        'date': {'$gte': start_of_year}
    }).sort('date', -1))
    
    if not expenses:
        await query.answer("No expenses found for this year!")
        return
    
    groups = {str(g['_id']): g['name'] for g in groups_collection.find({'user_id': user_id})}
    excel_file = create_excel_report(expenses, groups)
    
    await query.answer("Generating report...")
    await query.message.reply_document(
        document=excel_file,
        filename=f"expenses_yearly_{now.year}.xlsx",
        caption=f"📊 Yearly Report {now.year}\n💰 Total: ₹{sum(e['amount'] for e in expenses):.2f}"
    )
    await show_main_menu(query, context)

async def export_all_report(query, context):
    user_id = context.user_data.get('user_id')
    expenses = list(expenses_collection.find({'user_id': user_id}).sort('date', -1))
    
    if not expenses:
        await query.answer("No expenses found!")
        return
    
    groups = {str(g['_id']): g['name'] for g in groups_collection.find({'user_id': user_id})}
    excel_file = create_excel_report(expenses, groups)
    
    await query.answer("Generating report...")
    await query.message.reply_document(
        document=excel_file,
        filename=f"expenses_all_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        caption=f"📊 All Expenses Report\n💰 Total: ₹{sum(e['amount'] for e in expenses):.2f}"
    )
    await show_main_menu(query, context)

async def export_start_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        start_date = datetime.strptime(update.message.text.strip(), '%Y-%m-%d')
        context.user_data['export_start_date'] = start_date
        await update.message.reply_text('📅 Enter end date (YYYY-MM-DD):')
        return EXPORT_END_DATE
    except ValueError:
        await update.message.reply_text('❌ Invalid date format.')
        return EXPORT_START_DATE

async def export_end_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        end_date = datetime.strptime(update.message.text.strip(), '%Y-%m-%d')
        start_date = context.user_data.get('export_start_date')
        user_id = context.user_data.get('user_id')
        
        expenses = list(expenses_collection.find({
            'user_id': user_id,
            'date': {'$gte': start_date, '$lte': end_date}
        }).sort('date', -1))
        
        if not expenses:
            await update.message.reply_text("No expenses found in this date range!")
            await show_main_menu_message(update, context)
            return ConversationHandler.END
        
        groups = {str(g['_id']): g['name'] for g in groups_collection.find({'user_id': user_id})}
        excel_file = create_excel_report(expenses, groups)
        
        await update.message.reply_document(
            document=excel_file,
            filename=f"expenses_{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}.xlsx",
            caption=f"📊 Custom Report\n📅 {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n💰 Total: ₹{sum(e['amount'] for e in expenses):.2f}"
        )
        await show_main_menu_message(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text('❌ Invalid date format.')
        return EXPORT_END_DATE

async def export_group_report(query, context, group_id_str):
    user_id = context.user_data.get('user_id')
    
    # FIX: Use ObjectId for group lookup
    try:
        group = groups_collection.find_one({'_id': ObjectId(group_id_str), 'user_id': user_id})
    except:
        group = None

    if not group:
        await query.answer("Group not found!")
        return
    
    # Expenses store string ID
    expenses = list(expenses_collection.find({
        'user_id': user_id,
        'group_id': group_id_str
    }).sort('date', -1))
    
    if not expenses:
        await query.answer("No expenses in this group!")
        return
    
    groups = {str(g['_id']): g['name'] for g in groups_collection.find({'user_id': user_id})}
    excel_file = create_excel_report(expenses, groups)
    
    await query.answer("Generating report...")
    await query.message.reply_document(
        document=excel_file,
        filename=f"expenses_{group['name'].replace(' ', '_')}.xlsx",
        caption=f"📊 Group Report: {group['name']}\n💰 Total: ₹{sum(e['amount'] for e in expenses):.2f}"
    )
    await show_all_groups(query, context)

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

# --- FLASK KEEP ALIVE SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run_http():
    # Render sets the PORT env var. Default to 8080 if not found.
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=8000)

def keep_alive():
    t = Thread(target=run_http)
    t.start()

# --- End Of Flask ---

def main():
    # keep_alive()
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(button_handler)
        ],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_handler)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_handler)],
            REGISTER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email_handler)],
            REGISTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password_handler)],
            ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_amount_handler)],
            ADD_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_reason_handler)],
            ADD_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_date_handler)],
            ADD_GROUP: [CallbackQueryHandler(group_selection_handler)],  
            EDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_amount_handler)],
            EDIT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_reason_handler)],
            EDIT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_date_handler)],
            EDIT_GROUP: [CallbackQueryHandler(group_selection_handler)],  
            DELETE_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_start_date_handler)],
            DELETE_END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_end_date_handler)],
            CREATE_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_group_handler)],
            EXPORT_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, export_start_date_handler)],
            EXPORT_END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, export_end_date_handler)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(button_handler)
        ],
        allow_reentry=True,
        # REMOVED per_message=True (It breaks conversation flow)
    )
    
    app.add_handler(conv_handler)
    
    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()




