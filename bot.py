# --- TELEGRAM HANDLERS ---

async def perform_and_send_scan(context, chat_id, status_message=None):
    arbs = await scan_markets(status_message)
    text = f"📊 *Live Arbitrage (Filtered)*\n🕒 {datetime.datetime.now().strftime('%H:%M:%S')}\n\n"
    if not arbs:
        text += "No gaps found."
    else:
        for arb in arbs[:7]:
            text += (f"🪙 *{arb['symbol']}*\n"
                     f"🟢 Buy: {arb['low_ex'].upper()} (${arb['low_p']:.8f})\n"
                     f"🔴 Sell: {arb['high_ex'].upper()} (${arb['high_p']:.8f})\n"
                     f"💰 Potential: *{arb['spread']:.2f}%*\n\n")
    
    if status_message: await status_message.delete()
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown',
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Scan", callback_data='refresh')]]))

async def handle_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⌛ Starting Secure Scan...")
    await perform_and_send_scan(context, update.effective_chat.id, status_msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await perform_and_send_scan(context, query.message.chat_id, query.message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Professional Arbitrage Bot\n/scan to start.")

if __name__ == '__main__':
    # 1. Start the Flask server in a separate background thread
    threading.Thread(target=run_flask, daemon=True).start()

    # 2. Run the Telegram Bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", handle_scan))
    application.add_handler(CallbackQueryHandler(handle_button))

    print("Bot starting with Flask keep-alive...")
    application.run_polling(close_loop=False)
    'volume': high_data['volume']
                    })
        except: continue

    return sorted(all_arbs, key=lambda x: x['spread'], reverse=True)

# --- BACKGROUND AUTO-SCANNER ---

async def background_loop(app):
    """The engine that keeps the bot scanning every 3 minutes"""
    print("🚀 Background Engine Started...")
    while True:
        try:
            now = datetime.datetime.now().strftime('%H:%M:%S')
            arbs = await scan_markets()

            if arbs:
                text = f"🚨 **Arbitrage Opportunity** ({now})\n\n"
                for arb in arbs[:7]:
                    text += (
                        f"🪙 *{arb['symbol']}*\n"
                        f"🟢 Buy: {arb['low_ex'].upper()} (${arb['low_p']:.6f})\n"
                        f"🔴 Sell: {arb['high_ex'].upper()} (${arb['high_p']:.6f})\n"
                        f"💰 Potential: *{arb['spread']:.2f}%*\n\n"
                    )
            else:
                text = f"ℹ️ **Scan Result** ({now})\nNo gaps found > 1.2%."

            # Send to your CHAT_ID
            await app.bot.send_message(
                chat_id=CHAT_ID, 
                text=text, 
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Force Scan Now", callback_data='refresh')]])
            )
            
            await asyncio.sleep(180) # 3-minute sleep
        except Exception as e:
            print(f"❌ Loop Error: {e}")
            await asyncio.sleep(60)

# --- TELEGRAM HANDLERS ---

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⌛ Starting Manual Refresh...")
    # This just triggers a one-off scan for you
    arbs = await scan_markets()
    # (Reuse logic from background_loop to format and send)
    # ... Simplified for brevity: usually, we'd send the same message format ...

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot Online and Active.\nScanning every 3 minutes automatically.")

if __name__ == '__main__':
    # 1. Start Web Server for Render
    threading.Thread(target=run_flask, daemon=True).start()

    # 2. Build Telegram App
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_button))

    # 3. Start Background Scanner
    loop = asyncio.get_event_loop()
    loop.create_task(background_loop(application))

    print("Bot is fully running on Render.")
    application.run_polling(close_loop=False)
    
