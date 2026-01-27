# -*- coding: utf-8 -*-
import asyncio
import nest_asyncio
import ccxt.async_support as ccxt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import datetime
import os
import threading
from flask import Flask

# --- PATCHES ---
nest_asyncio.apply()

app_web = Flask(__name__)

@app_web.route('/')
def health():
    return "Scanner is Active and Running"

def run_flask():
    # Render uses port 10000 by default for web services
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting Flask helper on port {port}...")
    # use_reloader=False is required when running in a thread
    app_web.run(host='0.0.0.0', port=port, use_reloader=False)

# --- CONFIGURATION ---
TELEGRAM_TOKEN = '8347545464:AAFFpwW2O5P4lt-cS5x1AW6Llx9Z2jKkgr4'
CHAT_IDS = ['6089058395', '-5213714280']

EXCHANGE_IDS = [
    'binance', 'bybit', 'mexc', 'gate', 'kucoin', 'bitget', 'huobi', 
    'lbank', 'bitmart', 'poloniex', 'xt', 'phemex', 'coinex', 
    'bingx', 'whitebit', 'bitrue', 'ascendex', 'toobit', 'blofin', 'latoken',
    'gemini', 'bitstamp', 'bitfinex', 'coinbase', 'okx', 'kraken'
]

limit_concurrency = asyncio.Semaphore(30) 

async def fetch_price_optimized(exchange_id, symbol):
    async with limit_concurrency:
        try:
            ex_class = getattr(ccxt, exchange_id)
            async with ex_class({'timeout': 7000, 'enableRateLimit': True}) as exchange:
                ticker = await exchange.fetch_ticker(symbol)
                price = ticker.get('last')
                volume = float(ticker.get('quoteVolume', 0) or 0)
                if price and price > 0 and volume > 500:
                    return exchange_id, symbol, {'price': price, 'volume': volume}
        except:
            pass
        return exchange_id, symbol, None

async def scan_markets(status_message=None):
    async with ccxt.mexc() as discovery_ex:
        try:
            tickers = await discovery_ex.fetch_tickers()
            pairs = sorted([s for s in tickers if s.endswith('/USDT')], 
                           key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:100]
        except:
            pairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'PEPE/USDT', 'DOGE/USDT']

    if status_message:
        try: await status_message.edit_text("⚡ **Turbo Scan: 100 Pairs**\nUsing Colab-optimized parallel processing...")
        except: pass

    all_results = []
    batch_size = 200 
    tasks = [fetch_price_optimized(ex_id, symbol) for symbol in pairs for ex_id in EXCHANGE_IDS]
    
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        all_results.extend(await asyncio.gather(*batch))

    market_data = {pair: {} for pair in pairs}
    for ex_id, symbol, data in all_results:
        if data:
            market_data[symbol][ex_id] = data

    all_arbs = []
    for symbol, exchanges in market_data.items():
        if len(exchanges) > 1:
            items = sorted(exchanges.items(), key=lambda x: x[1]['price'])
            low_n, low_d = items[0]
            high_n, high_d = items[-1]
            spread = ((high_d['price'] - low_d['price']) / low_d['price']) * 100
            
            if 1.2 < spread < 80.0:
                all_arbs.append({'symbol': symbol, 'low_name': low_n, 'low_p': low_d['price'], 
                                 'high_name': high_n, 'high_p': high_d['price'], 
                                 'spread': spread, 'volume': high_d['volume']})
    
    return sorted(all_arbs, key=lambda x: x['spread'], reverse=True)

async def perform_and_send_scan(context, status_message=None):
    start_time = datetime.datetime.now()
    arbs = await scan_markets(status_message)
    duration = (datetime.datetime.now() - start_time).seconds
    now = datetime.datetime.now().strftime('%H:%M:%S')
    
    if not arbs:
        text = f"🔍 **Scan Complete** ({now})\nNo tradeable gaps found (1.2%-80%).\n⏱ Time: {duration}s"
    else:
        text = f"📊 **Top 15 Arb Results** ({now})\n\n"
        for a in arbs[:15]:
            text += (f"🪙 *{a['symbol']}*\n"
                     f"🟢 Buy: {a['low_name'].upper()} (${a['low_p']:.6f})\n"
                     f"🔴 Sell: {a['high_name'].upper()} (${a['high_p']:.6f})\n"
                     f"💰 Potential: *{a['spread']:.2f}%*\n"
                     f"📊 24h Vol: ${a['volume']:,.0f}\n\n")
        text += f"⏱ **Duration: {duration}s** | ⚡ **Colab-Speed Mod**"

    if status_message:
        try: await status_message.delete()
        except: pass

    for cid in CHAT_IDS:
        try:
            await context.bot.send_message(chat_id=cid, text=text, parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Scan", callback_data='refresh')]]))
        except: pass

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 **Scanner Online**\nUse /scan to begin the Top 100 deep search.")

async def handle_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⌛ Starting Optimized Scan...")
    await perform_and_send_scan(context, status_msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await perform_and_send_scan(context)

if __name__ == '__main__':
    # 1. RUN FLASK IN A BACKGROUND THREAD
    print("Pre-loading Flask...")
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # 2. RUN TELEGRAM IN THE MAIN THREAD
    print("Initializing Telegram Bot...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("scan", handle_scan))
    application.add_handler(CallbackQueryHandler(handle_button))
    
    print("Bot is Polling. Ready for /scan")
    # drop_pending_updates=True is vital to avoid 409 Conflict Errors on Render
    application.run_polling(drop_pending_updates=True, close_loop=False)
    
