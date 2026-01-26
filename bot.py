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

# --- WEB SERVER FOR RENDER (Keep-Alive) ---
app_web = Flask(__name__)
@app_web.route('/')
def health(): return "Scanner is Active"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- CONFIGURATION ---
TELEGRAM_TOKEN = '8347545464:AAFFpwW2O5P4lt-cS5x1AW6Llx9Z2jKkgr4'

# FIXED: Correct list format for multiple chat IDs
CHAT_IDS = ['6089058395', '-5213714280']

EXCHANGE_IDS = [
    'bybit', 'mexc', 'gate', 'kucoin', 'bitget', 'okx', 'huobi', 'lbank', 'bitmart', 'poloniex',
    'digifinex', 'xt', 'phemex', 'probit', 'coinex', 'bingx', 'whitebit', 'bitrue', 'ascendex',
    'hitbtc', 'toobit', 'woo', 'woofipro', 'blofin', 'bitfinex', 'kraken', 'bitstamp', 'coinbase',
    'gemini', 'cryptocom', 'exmo', 'latoken', 'fmfwio', 'oceanex', 'bigone', 'paymium', 'btcturk'
]

limit_concurrency = asyncio.Semaphore(10)

async def fetch_price(exchange_id, symbol):
    async with limit_concurrency:
        if not hasattr(ccxt, exchange_id): return exchange_id, None
        ex_class = getattr(ccxt, exchange_id)
        exchange = ex_class({'timeout': 10000, 'enableRateLimit': True})
        try:
            ticker = await exchange.fetch_ticker(symbol)
            price = ticker.get('last')
            volume = float(ticker.get('quoteVolume', 0) or 0)
            if price and price > 0:
                return exchange_id, {'price': price, 'volume': volume}
        except:
            pass
        finally:
            await exchange.close()
        return exchange_id, None

async def scan_markets(status_message=None):
    async with ccxt.mexc() as discovery_ex:
        try:
            tickers = await discovery_ex.fetch_tickers()
            pairs = sorted([s for s in tickers if s.endswith('/USDT')], 
                           key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:40]
        except:
            pairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT']

    all_arbs = []
    for i, symbol in enumerate(pairs):
        if status_message and i % 2 == 0:
            progress = int((i / len(pairs)) * 100)
            try: await status_message.edit_text(f"⌛ **Scan Progress: {progress}%**\n🔍 Checking: `{symbol}`")
            except: pass

        tasks = [fetch_price(ex, symbol) for ex in EXCHANGE_IDS]
        results = await asyncio.gather(*tasks)
        valid_data = {ex: data for ex, data in results if data}
        
        if len(valid_data) > 1:
            items = sorted(valid_data.items(), key=lambda x: x[1]['price'])
            low_name, low_data = items[0]
            high_name, high_data = items[-1]
            spread = ((high_data['price'] - low_data['price']) / low_data['price']) * 100
            
            if 1.2 < spread < 50.0:
                all_arbs.append({
                    'symbol': symbol,
                    'low_name': low_name, 'low_p': low_data['price'],
                    'high_name': high_name, 'high_p': high_data['price'],
                    'spread': spread
                })
    return sorted(all_arbs, key=lambda x: x['spread'], reverse=True)

async def perform_and_send_scan(context, status_message=None):
    arbs = await scan_markets(status_message)
    now = datetime.datetime.now().strftime('%H:%M:%S')
    
    if not arbs:
        text = f"🔍 **Scan Complete** ({now})\nNo gaps found > 1.2%."
    else:
        text = f"📊 **Arb Scan Results** ({now})\n\n"
        for a in arbs[:7]:
            text += (f"🪙 *{a['symbol']}*\n"
                     f"🟢 Buy: {a['low_name'].upper()} (${a['low_p']:.6f})\n"
                     f"🔴 Sell: {a['high_name'].upper()} (${a['high_p']:.6f})\n"
                     f"💰 Potential: *{a['spread']:.2f}%*\n\n")

    if status_message:
        try: await status_message.delete()
        except: pass

    # FIXED: This loop sends the same results to EVERY chat in your CHAT_IDS list
    for cid in CHAT_IDS:
        try:
            await context.bot.send_message(
                chat_id=cid, 
                text=text, 
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Scan", callback_data='refresh')]])
            )
        except Exception as e:
            print(f"Error sending to {cid}: {e}")

async def handle_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⌛ Starting Manual Scan...")
    await perform_and_send_scan(context, status_msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # When button is clicked, we send the updated results to all IDs
    await perform_and_send_scan(context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Bot Online.\nUse /scan to check markets. Results will be sent to the group and private chat.")

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", handle_scan))
    application.add_handler(CallbackQueryHandler(handle_button))
    print("Bot is starting (Manual Mode Only)...")
    application.run_polling(close_loop=False)
