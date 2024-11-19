import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler

from ghostfolio import Ghostfolio
from data_importer import DataImporter
from decouple import config
import json
import matplotlib.pyplot as plt
import pandas as pd

holding_list = []
STAGE1, STAGE2, STAGE3, STAGE4 = range(4)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def get_detail(ghost):
    def format_number(x):
        if isinstance(x, str):
            return x
        if isinstance(x, float):
            if x.is_integer():
                return "{:.0f}".format(x)
            return "{:.2f}".format(x)
        if isinstance(x, int):
            return "{:d}".format(x)
        return x

    usd_twd = ghost.position(data_source="YAHOO", symbol="USDTWD").get("marketPrice")

    def TWD_to_USD(x):
        return x / usd_twd

    df = pd.DataFrame(columns=["Account", "Stock", "Price", "Quantity", "Unit Cost", "Cost", "Change", "Change(%)", "Allocation", "Total"])
    accounts = ghost.accounts()
    total_value = accounts.get("totalValueInBaseCurrency", 0)
    accounts.get("accounts", {}).sort(key=lambda x: x.get("valueInBaseCurrency", 0), reverse=True)
    accounts = accounts.get("accounts", [])

    for account in accounts:
        holdings = ghost.holdings(account_id=account.get("id", "")).get("holdings", {})
        holdings.sort(key=lambda x: x.get("allocationInPercentage", 0), reverse=True)
        for h in holdings:
            currency = h.get("currency", "")
            if h.get("symbol", "") == "TWD" or h.get("symbol", "") == "USD":
                continue
            Cost = h.get("investment", 0) if currency == "TWD" else TWD_to_USD(h.get("investment", 0))
            Quantity = h.get("quantity", 0)
            UnitCost = Cost / Quantity if Quantity != 0 else 0
            Change = h.get("netPerformance", 0) if currency == "TWD" else TWD_to_USD(h.get("netPerformance", 0))
            allocation_of_account = h.get('allocationInPercentage', 0) * 100
            allocation = h.get('valueInBaseCurrency', 0) / total_value * 100
            df.loc[len(df)] = {
                "Account": "",
                "Stock": "{}".format(h.get("symbol", "No Name Found")),
                "Price": format_number(h.get("marketPrice", 0)),
                "Quantity": format_number(Quantity),
                "Unit Cost": format_number(UnitCost),
                "Cost": format_number(Cost),
                "Change": format_number(Change),
                "Change(%)": format_number(Change / Cost * 100) + " %",
                "Allocation": "{} % ({} %)".format(format_number(allocation_of_account), format_number(allocation)),
                "Total": "{} {}".format(format_number(h.get('quantity', 0) * h.get('marketPrice')), h.get('currency', ''))
            }
        total_cost = df.loc[len(df) - len(holdings) + 1: len(df)]["Cost"].map(float).sum()
        total_change = df.loc[len(df) - len(holdings) + 1: len(df)]["Change"].map(float).sum()
        df.loc[len(df)] = {
            "Account": account.get("name", "No Name Found"),
            "Allocation": format_number(account.get('valueInBaseCurrency', 0) / total_value * 100) + " %",
            "Cost": format_number(total_cost),
            "Change": format_number(total_change),
            "Change(%)": format_number(total_change / total_cost * 100) + " %",
            "Total": format_number(account.get('value', 0)) + " " + account.get('currency', '')
        }
    df.loc[len(df)] = {
        "Account": "Total",
        "Total": format_number(total_value) + " " + "TWD"
    }

    df = df.fillna("")
    return df

async def detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ghost = context.bot_data["ghostfolio"]
    df = get_detail(ghost)

    # transfer the dataframe to an image
    fig, ax = plt.subplots(figsize=(16, 8))
    ax.axis("off")
    ax.axis("tight")
    table = ax.table(cellText=df.values, colLabels=df.columns, cellLoc="left", loc="upper center")
    for (row, col), cell in table.get_celld().items():
        if col == df.columns.get_loc("Change") and row != 0:
            cell.set_text_props(color='darkred' if cell.get_text().get_text() != "" and float(cell.get_text().get_text()) < 0 else 'darkgreen')
            cell.set_text_props(ha='right')
        if col == df.columns.get_loc("Change(%)") and row != 0:
            cell.set_text_props(color='darkred' if cell.get_text().get_text() != "" and float(cell.get_text().get_text().replace("%", "")) < 0 else 'darkgreen')
        if col == df.columns.get_loc("Total") and row != 0:
            cell.set_text_props(ha='right')
        if col == df.columns.get_loc("Cost") and row != 0:
            cell.set_text_props(ha='right')
        if 0 < row <= len(df) and df.loc[row - 1]["Account"] != "":
            cell.set_text_props(weight='bold')
        if row % 2 == 0:
            cell.set_facecolor("#eaeaea")

    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    plt.title(f"Portfolio Detail on {today}")
    plt.tight_layout()
    plt.savefig("detail.png", bbox_inches="tight", dpi=300)

    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=open("detail.png", "rb"))
    plt.close()
    # delete the image after sending

    return ConversationHandler.END


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
    try:
        with open(csv, "r") as f:
            activities = DataImporter(broker, f).activities()
            context.bot_data["activities"] = activities
    except Exception as e:
        await update.message.reply_text("Error: ", str(e))
        return ConversationHandler.END

    await update.message.reply_text("Successfully uploaded the file")
    return await start_import(update, context)

async def start_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    bot_token = config("BOT_TOKEN", "")
    ghostfolio_token = config("GHOSTFOLIO_TOKEN", "")
    host = config("HOST", "http://localhost:3333")

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
    application.add_handler(CommandHandler('detail', detail))
    application.add_handler(import_handler)
    application.add_handler(performance_handler)
    application.add_handler(order_handler)

    # Settings
    application.add_handler(CommandHandler('raw_data', toggle_raw_data))
    application.add_handler(CommandHandler('demo_mode', toggle_demo_mode))

    # Unknown
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    application.run_polling()
