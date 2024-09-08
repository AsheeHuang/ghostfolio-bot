import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler

from ghostfolio import Ghostfolio
from data_importer import DataImporter
import json
import matplotlib.pyplot as plt
import os

holding_list = []
STAGE1, STAGE2, STAGE3, STAGE4 = range(4)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ghost = context.bot_data["ghostfolio"]
    raw_data = context.bot_data["raw_data"]
    demo_mode = context.bot_data["demo_mode"]

    resp = ghost.accounts()

    if raw_data:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=json.dumps(resp, indent=2))
        return

    if "accounts" not in resp:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Error")
        return

    total_value = round(resp["totalValueInBaseCurrency"], 2)
    txt = ""
    for info in resp["accounts"]:
        value_in_base_currency = round(info["valueInBaseCurrency"], 2)
        propotion = round(value_in_base_currency / total_value * 100, 2)
        value = round(info["value"], 2)
        currency = info['currency']

        if demo_mode:
            txt += f"{info['name']}: \t\t ***** {currency}\t {propotion} %\n"
        else:
            txt += f"{info['name']}: \t\t {value} {currency}\t {propotion} %\n"

    txt += "\n"
    if demo_mode:
        txt += "Total: ***** TWD"
    else:
        txt += f"Total: {total_value} TWD"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=txt)

async def holdings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ghost = context.bot_data["ghostfolio"]
    raw_data = context.bot_data["raw_data"]
    demo_mode = context.bot_data["demo_mode"]
    resp = ghost.holdings()
    if raw_data:
        # send resp by chunks
        for holding in resp["holdings"]:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=json.dumps(holding, indent=2))
        return

    if "holdings" not in resp:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Error")
        return

    txt = ""
    for holding in resp["holdings"]:
        if demo_mode:
            value = "*****"
            quantity = "*****"
        else:
            value = round(holding["valueInBaseCurrency"])
            quantity = holding["quantity"]

        txt += f"{holding['name']} ({holding['symbol']}): \n"
        txt += f"\t\t Quantity: {quantity}\n"
        txt += f"\t\t Price: {holding['marketPrice']} {holding['currency']}\n"
        txt += f"\t\t Value: {value} TWD \n"
        txt += f"\t\t Propotion: {round(holding['allocationInPercentage'] * 100, 2)}% \n"

    if len(txt) > 4096:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="The message is too long")
        return

    await context.bot.send_message(chat_id=update.effective_chat.id, text=txt)

async def select_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Year to Date", callback_data="ytd"),
         InlineKeyboardButton("Month to Date", callback_data="mtd"),
         InlineKeyboardButton("Week to Date", callback_data="wtd")],
        [InlineKeyboardButton("2021", callback_data="2021"),
         InlineKeyboardButton("2022", callback_data="2022"),
         InlineKeyboardButton("2023", callback_data="2023")],
        [InlineKeyboardButton("1Y", callback_data="1y"),
         InlineKeyboardButton("5Y", callback_data="5y")],
        [InlineKeyboardButton("Max", callback_data="max")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose range:', reply_markup=reply_markup)
    return STAGE1

async def performance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_range = query.data

    ghost = context.bot_data["ghostfolio"]
    raw_data = context.bot_data["raw_data"]
    demo_mode = context.bot_data["demo_mode"]

    if raw_data:
        context.bot.send_message(chat_id=update.effective_chat.id, text="This command does not support raw data")

    try:
        resp = ghost.performance(data_range)
    except Exception as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=str(e))
        return

    if "chart" not in resp:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Error")

    date = [data["date"] for data in resp["chart"]]
    performance = [data["netPerformanceInPercentage"] for data in resp["chart"]]
    value = [data["value"] for data in resp["chart"]]
    value[0] = value[1] if value[0] == 0 else value[0]

    # draw a line chart, performance and value is y-axis, date is x-axis
    fig, ax = plt.subplots()
    ax.plot(date, performance, color="tab:blue", label="Performance")
    ax.set_xlabel("Date")
    ax.set_ylabel("Performance")
    ax.legend(loc="upper left")
    if not demo_mode:
        ax2 = ax.twinx()
        ax2.plot(date, value, color="tab:red", label="Value in TWD")
        ax2.get_yaxis().get_major_formatter().set_scientific(False)
        ax2.set_ylabel("Value in TWD")
        ax2.legend(loc="upper right")

    plt.title(f"Performance of {data_range}")
    plt.tight_layout()
    plt.savefig("performance.png")

    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=open("performance.png", "rb"))

    plt.close()
    return ConversationHandler.END

async def select_holding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not holding_list:
        ghost = context.bot_data["ghostfolio"]
        resp = ghost.holdings()
        if "holdings" not in resp:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Error")
            return

        for holding in resp["holdings"]:
            if holding.get("symbol", "") not in holding_list:
                holding_list.append(holding["symbol"])
        print(holding_list)

    keyboard = []
    for index in range(0, len(holding_list), 3):
        line = []
        line.append(InlineKeyboardButton(holding_list[index], callback_data=holding_list[index]))
        if index + 1 < len(holding_list):
            line.append(InlineKeyboardButton(holding_list[index + 1], callback_data=holding_list[index + 1]))
        if index + 2 < len(holding_list):
            line.append(InlineKeyboardButton(holding_list[index + 2], callback_data=holding_list[index + 2]))
        keyboard.append(line)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose holding:', reply_markup=reply_markup)
    return STAGE1

async def position_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    symbol = query.data

    ghost = context.bot_data["ghostfolio"]
    raw_data = context.bot_data["raw_data"]
    demo_mode = context.bot_data["demo_mode"]

    data_sources = ["YAHOO", "COINGECKO"]
    try:
        found = False
        for source in data_sources:
            resp = ghost.position(source, symbol)
            if "SymbolProfile" in resp:
                found = True
                break
        if not found:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Symbol not found")
            return
    except Exception as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=str(e))
        return

    if raw_data:
        resp.pop("orders", None)
        resp.pop("historicalData", None)

        await context.bot.send_message(chat_id=update.effective_chat.id, text=json.dumps(resp, indent=2))
        return

    txt = ""
    profile = resp["SymbolProfile"]
    txt += f"{profile['name']} ({profile['symbol']})\n"
    txt += f"\t\t Price: {resp['marketPrice']} {profile['currency']}\n"
    if not demo_mode:
        txt += f"\t\t Quantity: {resp['quantity']}\n"
        txt += f"\t\t Cost: {round(resp['investment'], 2)} {profile['currency']}\n" 
        txt += f"\t\t Current Value: {round(resp['value'], 2)} {profile['currency']}\n"
        txt += f"\t\t Profit: {round(resp['netPerformance'], 2)} {profile['currency']}\n"
    profit_percentage = round(resp['netPerformance'] / resp['investment'] * 100, 2)
    txt += f"\t\t Profit Percentage: {profit_percentage} %\n"

    await query.edit_message_text(text=txt)
    return ConversationHandler.END

async def select_broker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Cathay", callback_data="cathay"),
         InlineKeyboardButton("Firstrade", callback_data="ft")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose broker:', reply_markup=reply_markup)
    return STAGE1

async def ask_import_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    broker = query.data
    context.bot_data["broker"] = broker

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Please upload the csv file of {broker}")
    return STAGE2

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    broker = context.bot_data["broker"]
    if broker not in ["cathay", "ft"]:
        await update.message.reply_text("Invalid broker")
        return ConversationHandler.END

    file = await update.message.document.get_file()
    csv = await file.download_to_drive("import.csv")
    with open(csv, "r") as f:
        activities = DataImporter(broker, f).activities()
        print(activities)
        context.bot_data["activities"] = activities

    await update.message.reply_text("Successfully uploaded the file")
    return await start_import(update, context)

async def start_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("start_import")
    activities = context.bot_data["activities"]
    keyboard = [
        [InlineKeyboardButton("Import", callback_data="import"),
         InlineKeyboardButton("Cancel", callback_data="cancel")],
    ]
    activity = activities.pop(0)
    context.bot_data["cur_activity"] = activity

    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Do you want to import {}".format(json.dumps(activity["activities"], indent=2)),
                                   reply_markup=reply_markup)
    return STAGE4

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    confirm = query.data == "import"

    ghost = context.bot_data["ghostfolio"]
    activity = context.bot_data["cur_activity"]

    if confirm:
        ghost.import_transactions(activity)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Imported successfully with response")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Import canceled")

    if context.bot_data["activities"]:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Continue to import")
        return await start_import(update, context)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="No more activities to import")
        return ConversationHandler.END

async def order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ghost = context.bot_data["ghostfolio"]
    raw_data = context.bot_data["raw_data"]
    cur_activity = context.bot_data.get("cur_activity", None)
    if cur_activity is None:
        cur_activity = 0
    else:
        cur_activity += 10

    try:
        resp = ghost.orders(skip=cur_activity)
        context.bot_data["cur_activity"] = cur_activity
    except Exception as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=str(e))
        return

    if raw_data:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=json.dumps(resp, indent=2))
        return

    if "activities" not in resp:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Error Resp: {}".format(resp))

    txt = ""
    for activity in resp["activities"]:
        symbol_profile = activity["SymbolProfile"]
        account_info = activity["Account"]
        date = activity["date"].split("T")[0]
        txt += "{} {} {} at {} \n".format(activity["type"], activity["quantity"], symbol_profile["symbol"], date)
        txt += "\t with price {} {} in account {} \n".format(activity["unitPrice"], symbol_profile["currency"], account_info["name"])

    await context.bot.send_message(chat_id=update.effective_chat.id, text=txt)
    keyboard = [
        [InlineKeyboardButton("Yes", callback_data="yes"),
         InlineKeyboardButton("No", callback_data="no")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text='More activities ?', reply_markup=reply_markup)
    return STAGE1

async def order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    more = query.data == "yes"

    if more:
        return await order(update, context)
    else:
        context.bot_data.pop("cur_activity", None)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="End of activities")
        return ConversationHandler.END

async def toggle_raw_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data["raw_data"] = not context.bot_data["raw_data"]
    txt = "Raw data is now enabled" if context.bot_data["raw_data"] else "Raw data is now disabled"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=txt)

async def toggle_demo_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data["demo_mode"] = not context.bot_data["demo_mode"]
    txt = "Demo mode is now enabled" if context.bot_data["demo_mode"] else "Demo mode is now disabled"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=txt)

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Unknown Command")

if __name__ == '__main__':
    bot_token = os.getenv("BOT_TOKEN")
    host = os.getenv("HOST")
    ghostfolio_token = os.getenv("GHOSTFOLIO_TOKEN")

    application = ApplicationBuilder().token(bot_token).build()

    ghost = Ghostfolio(token=ghostfolio_token, host=host)

    application.bot_data["ghostfolio"] = ghost
    application.bot_data["raw_data"] = False
    application.bot_data["demo_mode"] = False

    performance_handler = ConversationHandler(
        entry_points=[CommandHandler('performance', select_range)],
        states={
            STAGE1: [CallbackQueryHandler(performance_callback)],
        },
        fallbacks=[CommandHandler('performance', select_range)],
    )

    position_handler = ConversationHandler(
        entry_points=[CommandHandler('position', select_holding)],
        states={
            STAGE1: [CallbackQueryHandler(position_callback)],
        },
        fallbacks=[CommandHandler('position', select_holding)],
    )

    import_handler = ConversationHandler(
        entry_points=[CommandHandler('import', select_broker)],
        states={
            STAGE1: [CallbackQueryHandler(ask_import_file)],
            STAGE2: [MessageHandler(filters.Document.MimeType("text/csv"), handle_file)],
            STAGE4: [CallbackQueryHandler(confirm_callback)],
        },
        fallbacks=[CommandHandler('import', select_broker)],
    )

    order_handler = ConversationHandler(
        entry_points=[CommandHandler('orders', order)],
        states={
            STAGE1: [CallbackQueryHandler(order_callback)],
        },
        fallbacks=[CommandHandler('orders', order)],
    )

    # Commands
    application.add_handler(CommandHandler('accounts', accounts))
    application.add_handler(CommandHandler('holdings', holdings))
    application.add_handler(position_handler)
    application.add_handler(import_handler)
    application.add_handler(performance_handler)
    application.add_handler(order_handler)

    # Settings
    application.add_handler(CommandHandler('raw_data', toggle_raw_data))
    application.add_handler(CommandHandler('demo_mode', toggle_demo_mode))

    # Unknown
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    application.run_polling()
