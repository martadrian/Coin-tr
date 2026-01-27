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

app_web = Flask(__name__)
@app_web.route('/')
def health(): return "Scanner is Active"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- CONFIGURATION ---
TELEGRAM_TOKEN = '7792086126:AAHunvNfw67O1O-Gkv49mgRx-SinM712t0Q'
CHAT_IDS = ['6089058395', '-5213714280']

EXCHANGE_IDS = [
    'binance', 'bybit', 'mexc', 'gate', 'kucoin', 'bitget', 'huobi', 
    'lbank', 'bitmart', 'poloniex', 'xt', 'phemex', 'coinex', 
    'bingx', 'whitebit', 'bitrue', 'ascendex', 'toobit', 'blofin', 'latoken',
    'gemini', 'bitstamp', 'bitfinex', 'coinbase', 'okx', 'kraken'
]

async def fetch_exchange_data(exchange_id, pairs):
    """Fetch ALL prices for ALL pairs in one single request per exchange."""
    if not hasattr(ccxt, exchange_id): return exchange_id, {}
    ex_class = getattr(ccxt, exchange_id)
    # Use a shorter timeout to prevent one slow exchange from hanging the whole scan
    exchange = ex_class({'timeout': 10000, 'enableRateLimit': True})
    try:
        # fetch_tickers is the key to speed—it gets everything at once
        tickers = await exchange.fetch_tickers(pairs)
        valid_results = {}
        for symbol, ticker in tickers.items():
            price = ticker.get('last')
            volume = float(ticker.get('quoteVolume', 0) or 0)
            if price and price > 0 and volume > 500:
                valid_results[symbol] = {'price': price, 'volume': volume}
        return exchange_id, valid_results
    except:
        return exchange_id, {}
    finally:
        await exchange.close()

async def scan_markets(status_message=None):
    async with ccxt.mexc() as discovery_ex:
        try:
            # Step 1: Find the Top 100 pairs
            tickers = await discovery_ex.fetch_tickers()
            pairs = sorted([s for s in tickers if s.endswith('/USDT')], 
                           key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:100]
        except:
            pairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'PEPE/USDT', 'DOGE/USDT']

    if status_message:
        await status_message.edit_text(f"🚀 **Batch Scanning 26 Exchanges...**\nThis will be MUCH faster.")

    # Step 2: Request data from all 26 exchanges in parallel
    tasks = [fetch_exchange_data(ex, pairs) for ex in EXCHANGE_IDS]
    exchange_results = await asyncio.gather(*tasks)
    
    # Map results by pair for easy comparison
    pair_data_map = {pair: {} for pair in pairs}
    for ex_id, data in exchange_results:
        for symbol, info in data.items():
            if symbol in pair_data_map:
                pair_data_map[symbol][ex_id] = info

    # Step 3: Compare prices
    all_arbs = []
    for symbol, exchanges in pair_data_map.items():
        if len(exchanges) > 1:
            items = sorted(exchanges.items(), key=lambda x: x[1]['price'])
            low_name, low_data = items[0]
            high_name, high_data = items[-1]
            spread = ((high_data['price'] - low_data['price']) / low_data['price']) * 100
            
            if 1.2 < spread < 80.0:
                all_arbs.append({
                    'symbol': symbol,
                    'low_name': low_name, 'low_p': low_data['price'],
                    'high_name': high_name, 'high_p': high_data['price'],
                    'spread': spread,
                    'volume': high_data['volume']
                })
    return sorted(all_arbs, key=lambda x: x['spread'], reverse=True)

async def perform_and_send_scan(context, status_message=None):
    start_time = datetime.datetime.now()
    arbs = await scan_markets(status_message)
    duration = (datetime.datetime.now() - start_time).seconds
    now = datetime.datetime.now().strftime('%H:%M:%S')
    
    if not arbs:
        text = f"🔍 **Scan Complete** ({now})\nNo tradeable gaps found (1.2%-80%)."
    else:
        text = f"📊 **Top 15 Arb Results** ({now})\n\n"
        for a in arbs[:15]:
            vol_str = f"${a['volume']:,.0f}"
            text += (f"🪙 *{a['symbol']}*\n"
                     f"🟢 Buy: {a['low_name'].upper()} (${a['low_p']:.6f})\n"
                     f"🔴 Sell: {a['high_name'].upper()} (${a['high_p']:.6f})\n"
                     f"💰 Potential: *{a['spread']:.2f}%*\n"
                     f"📊 24h Vol: {vol_str}\n\n")
        text += f"⏱ **Duration: {duration}s** | ⚡ **Turbo Mode**"

    if status_message:
        try: await status_message.delete()
        except: pass

    for cid in CHAT_IDS:
        try:
            await context.bot.send_message(
                chat_id=cid, text=text, parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Scan", callback_data='refresh')]])
            )
        except: pass

async def handle_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⌛ Starting Turbo Scan...")
    await perform_and_send_scan(context, status_msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await perform_and_send_scan(context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Turbo Scanner Online.")

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", handle_scan))
    application.add_handler(CallbackQueryHandler(handle_button))
    
    # Conflict Fix
    application.run_polling(drop_pending_updates=True, close_loop=False)
