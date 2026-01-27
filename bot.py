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

nest_asyncio.apply()

# ------------------ Flask ------------------
app_web = Flask(__name__)

@app_web.route('/')
def health():
    return "Scanner is Active and Running"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port, use_reloader=False)

# ------------------ CONFIG ------------------
TELEGRAM_TOKEN = '8347545464:AAFFpwW2O5P4lt-cS5x1AW6Llx9Z2jKkgr4'
CHAT_IDS = ['6089058395', '-5213714280']

EXCHANGE_IDS = [
    'binance','bybit','mexc','gate','kucoin','bitget','huobi',
    'lbank','bitmart','poloniex','xt','phemex','coinex',
    'bingx','whitebit','bitrue','ascendex','toobit','blofin','latoken',
    'gemini','bitstamp','bitfinex','coinbase','okx','kraken'
]

limit_concurrency = asyncio.Semaphore(40)

# ------------------ PRICE FETCH ------------------
async def fetch_price(exchange, exchange_id, symbol):
    async with limit_concurrency:
        try:
            ticker = await exchange.fetch_ticker(symbol)
            price = ticker.get('last')
            volume = float(ticker.get('quoteVolume', 0) or 0)
            if price and price > 0 and volume > 500:
                return exchange_id, symbol, {'price': price, 'volume': volume}
        except:
            return exchange_id, symbol, None
        return exchange_id, symbol, None

# ------------------ SCAN ------------------
async def scan_markets(status_message=None):
    discovery_ex = ccxt.mexc()
    try:
        tickers = await discovery_ex.fetch_tickers()
        pairs = sorted(
            [s for s in tickers if s.endswith('/USDT')],
            key=lambda x: tickers[x].get('quoteVolume', 0),
            reverse=True
        )[:100]
    except:
        pairs = ['BTC/USDT','ETH/USDT','SOL/USDT','XRP/USDT','DOGE/USDT']
    finally:
        await discovery_ex.close()

    if status_message:
        try: await status_message.edit_text("⚡ **Turbo Scan: 100 Pairs**\nProcessing in stable batches...")
        except: pass

    exchanges = {}
    for ex_id in EXCHANGE_IDS:
        try:
            ex_class = getattr(ccxt, ex_id)
            exchanges[ex_id] = ex_class({'enableRateLimit': True, 'timeout': 7000})
        except:
            continue

    tasks = []
    for symbol in pairs:
        for ex_id, ex in exchanges.items():
            tasks.append(fetch_price(ex, ex_id, symbol))

    # --- FIXED: BATCH PROCESSING TO PREVENT HANGING ---
    results = []
    batch_size = 150 # Process 150 requests at a time
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i : i + batch_size]
        # return_exceptions=True ensures one failure doesn't stop the whole scan
        batch_results = await asyncio.gather(*batch, return_exceptions=True)
        for res in batch_results:
            if isinstance(res, tuple): # Ensure it's a valid result, not an error
                results.append(res)
        await asyncio.sleep(0.05) # Tiny breather for Render's CPU

    for ex in exchanges.values():
        try: await ex.close()
        except: pass

    market_data = {p: {} for p in pairs}
    for item in results:
        if item and len(item) == 3:
            ex_id, symbol, data = item
            if data:
                market_data[symbol][ex_id] = data

    arbs = []
    for symbol, exs in market_data.items():
        if len(exs) > 1:
            items = sorted(exs.items(), key=lambda x: x[1]['price'])
            low_n, low_d = items[0]
            high_n, high_d = items[-1]
            spread = ((high_d['price'] - low_d['price']) / low_d['price']) * 100
            if 1.2 < spread < 80:
                arbs.append({
                    'symbol': symbol, 'low_name': low_n, 'low_p': low_d['price'],
                    'high_name': high_n, 'high_p': high_d['price'],
                    'spread': spread, 'volume': high_d['volume']
                })

    return sorted(arbs, key=lambda x: x['spread'], reverse=True)

# ------------------ TELEGRAM ------------------
async def perform_and_send_scan(context, status_message=None):
    start = datetime.datetime.now()
    arbs = await scan_markets(status_message)
    duration = (datetime.datetime.now() - start).seconds
    now = datetime.datetime.now().strftime('%H:%M:%S')

    if not arbs:
        text = f"🔍 **Scan Complete** ({now})\nNo tradeable gaps found.\n⏱ {duration}s"
    else:
        text = f"📊 **Top 15 Arb Results** ({now})\n\n"
        for a in arbs[:15]:
            text += (f"🪙 *{a['symbol']}*\n"
                     f"🟢 Buy: {a['low_name'].upper()} (${a['low_p']:.6f})\n"
                     f"🔴 Sell: {a['high_name'].upper()} (${a['high_p']:.6f})\n"
                     f"💰 Potential: *{a['spread']:.2f}%*\n"
                     f"📊 Vol: ${a['volume']:,.0f}\n\n")
        text += f"⏱ **Duration: {duration}s** | ⚡ **Stable-Batch**"

    if status_message:
        try: await status_message.delete()
        except: pass

    for cid in CHAT_IDS:
        try:
            await context.bot.send_message(
                chat_id=cid, text=text, parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Scan", callback_data='refresh')]]))
        except: pass

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 **Scanner Online**\nUse /scan to start.")

async def handle_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⌛ Starting Optimized Scan...")
    await perform_and_send_scan(context, msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await perform_and_send_scan(context)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("scan", handle_scan))
    app.add_handler(CallbackQueryHandler(handle_button))
    print("Bot is Polling (Stable Batch Strategy)...")
    app.run_polling(drop_pending_updates=True, close_loop=False)
    
