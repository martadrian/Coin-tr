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

# --- APPLY LOOP PATCH ---
nest_asyncio.apply()

# --- RENDER KEEP-ALIVE (Minimal Addition) ---
app_web = Flask(__name__)
@app_web.route('/')
def health_check(): return "Bot is live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- CONFIGURATION ---
TELEGRAM_TOKEN = '8347545464:AAFFpwW2O5P4lt-cS5x1AW6Llx9Z2jKkgr4'
CHAT_ID = '6089058395'

EXCHANGE_IDS = [
    'bybit', 'mexc', 'gate', 'kucoin', 'bitget', 'okx', 'huobi', 'lbank', 'bitmart', 'poloniex',
    'digifinex', 'xt', 'phemex', 'probit', 'coinex', 'bingx', 'whitebit', 'bitrue', 'ascendex',
    'hitbtc', 'toobit', 'woo', 'woofipro', 'blofin', 'bitfinex', 'kraken', 'bitstamp', 'coinbase',
    'gemini', 'cryptocom', 'exmo', 'latoken', 'fmfwio', 'oceanex', 'bigone', 'paymium', 'btcturk',
    'independentreserve', 'coincheck', 'zaif', 'bitbank', 'bithumb', 'coinone', 'korbit', 'paribu',
    'tidex', 'dextrade', 'vitex', 'wavesexchange', 'bequant', 'timex'
]

# --- CORE LOGIC (Exactly as your Colab code) ---

async def get_top_100_pairs():
    async with ccxt.mexc({'enableRateLimit': True}) as ex:
        try:
            tickers = await ex.fetch_tickers()
            usdt_pairs = [s for s in tickers if s.endswith('/USDT')]
            sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)
            return sorted_pairs[:100]
        except Exception as e:
            return ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT']

limit_concurrency = asyncio.Semaphore(15)

async def fetch_price(exchange_id, symbol):
    async with limit_concurrency:
        if not hasattr(ccxt, exchange_id): return exchange_id, None
        try:
            async with getattr(ccxt, exchange_id)({'timeout': 7000, 'enableRateLimit': True}) as exchange:
                ticker = await exchange.fetch_ticker(symbol)
                price = ticker.get('last')
                volume = float(ticker.get('quoteVolume', 0) or 0)
                if price and price > 0: return exchange_id, {'price': price, 'volume': volume}
        except: return exchange_id, None

async def scan_markets(status_message=None):
    top_pairs = await get_top_100_pairs()
    all_arbs = []
    active_pairs = top_pairs[:50]

    for i, symbol in enumerate(active_pairs):
        if status_message and i % 2 == 0:
            progress = int((i / len(active_pairs)) * 100)
            try: await status_message.edit_text(f"⌛ **Turbo Scan Progress: {progress}%**\n🔍 Checking: `{symbol}`\n📈 Gaps Found: {len(all_arbs)}")
            except: pass

        tasks = [fetch_price(ex, symbol) for ex in EXCHANGE_IDS]
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=20.0)
            valid_data = {ex: data for ex, data in results if data}
            if len(valid_data) > 1:
                items = sorted(valid_data.items(), key=lambda x: x[1]['price'])
                low_ex, low_d = items[0]
                high_ex, high_d = items[-1]
                spread = ((high_d['price'] - low_d['price']) / low_d['price']) * 100
                if 1.2 < spread < 80.0:
                    all_arbs.append({'symbol': symbol, 'low_ex': low_ex, 'low_p': low_d['price'], 'high_ex': high_ex, 'high_p': high_d['price'], 'spread': spread, 'volume': high_d['volume']})
        except: continue
    return sorted(all_arbs, key=lambda x: x['spread'], reverse=True)

async def perform_and_send_scan(context, chat_id, status_message=None):
    arbs = await scan_markets(status_message)
    text = f"📊 *Live Arbitrage*\n🕒 {datetime.datetime.now().strftime('%H:%M:%S')}\n\n"
    if not arbs: text = "🔍 No gaps found."
    else:
        for arb in arbs[:7]:
            text += (f"🪙 *{arb['symbol']}*\n🟢 Buy: {arb['low_ex'].upper()} (${arb['low_p']:.8f})\n🔴 Sell: {arb['high_ex'].upper()} (${arb['high_p']:.8f})\n💰 Spread: *{arb['spread']:.2f}%*\n\n")
    if status_message:
        try: await status_message.delete()
        except: pass
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Scan", callback_data='refresh')]]))

async def handle_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⌛ Starting Manual Scan...")
    await perform_and_send_scan(context, update.effective_chat.id, status_msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await perform_and_send_scan(context, query.message.chat_id, query.message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Professional Arbitrage Bot\nUse /scan to start.")

if __name__ == '__main__':
    # Start the "Health Check" website so Render doesn't shut us down
    threading.Thread(target=run_flask, daemon=True).start()

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", handle_scan))
    application.add_handler(CallbackQueryHandler(handle_button))

    print("Bot is fully starting. Polling active.")
    application.run_polling(close_loop=False)
              
