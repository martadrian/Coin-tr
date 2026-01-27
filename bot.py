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
def health(): return "Scanner is Active"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- CONFIGURATION ---
TELEGRAM_TOKEN = '8257534645:AAFjgSdcxFjhv9mNct-hPHXHDcX8VyUwQv4'
CHAT_IDS = ['6089058395', '-5213714280']

# Your Full 26 Exchange List
EXCHANGE_IDS = [
    'binance', 'bybit', 'mexc', 'gate', 'kucoin', 'bitget', 'huobi', 
    'lbank', 'bitmart', 'poloniex', 'xt', 'phemex', 'coinex', 
    'bingx', 'whitebit', 'bitrue', 'ascendex', 'toobit', 'blofin', 'latoken',
    'gemini', 'bitstamp', 'bitfinex', 'coinbase', 'okx', 'kraken'
]

limit_concurrency = asyncio.Semaphore(15)

async def fetch_price(exchange_id, symbol):
    async with limit_concurrency:
        if not hasattr(ccxt, exchange_id): return exchange_id, None
        ex_class = getattr(ccxt, exchange_id)
        exchange = ex_class({'timeout': 15000, 'enableRateLimit': True})
        try:
            ticker = await exchange.fetch_ticker(symbol)
            price = ticker.get('last')
            volume = float(ticker.get('quoteVolume', 0) or 0)
            
            # GHOST FILTER: Kept at $500 to ensure tradeability
            if price and price > 0 and volume > 500:
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
            # UPDATED: Now scanning 100 pairs for deeper arbitrage discovery
            pairs = sorted([s for s in tickers if s.endswith('/USDT')], 
                           key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:100]
        except:
            # SAFETY NET: BTC, ETH and core pairs kept as backup
            pairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'PEPE/USDT', 'DOGE/USDT']

    all_arbs = []
    for i, symbol in enumerate(pairs):
        if status_message and i % 5 == 0:
            progress = int((i / len(pairs)) * 100)
            try: await status_message.edit_text(f"🚀 **Deep Scan (Top 100): {progress}%**\n🔍 Checking: `{symbol}`")
            except: pass

        tasks = [fetch_price(ex, symbol) for ex in EXCHANGE_IDS]
        results = await asyncio.gather(*tasks)
        valid_data = {ex: data for ex, data in results if data}
        
        if len(valid_data) > 1:
            items = sorted(valid_data.items(), key=lambda x: x[1]['price'])
            low_name, low_data = items[0]
            high_name, high_data = items[-1]
            spread = ((high_data['price'] - low_data['price']) / low_data['price']) * 100
            
            # UPDATED: Spread max extended to 80%
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
        text = f"🔍 **Scan Complete** ({now})\nNo tradeable gaps found (1.2%-80%).\n⏱ Time: {duration}s"
    else:
        # UPDATED: Extended output to show Top 15 Arb results
        text = f"📊 **Top 15 Arb Results (Top 100 pairs)** ({now})\n\n"
        for a in arbs[:15]:
            vol_str = f"${a['volume']:,.0f}"
            text += (f"🪙 *{a['symbol']}*\n"
                     f"🟢 Buy: {a['low_name'].upper()} (${a['low_p']:.6f})\n"
                     f"🔴 Sell: {a['high_name'].upper()} (${a['high_p']:.6f})\n"
                     f"💰 Potential: *{a['spread']:.2f}%*\n"
                     f"📊 24h Vol: {vol_str}\n\n")
        text += f"⏱ **Duration: {duration}s** | 🏛 **Exchanges: 26**"

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
    status_msg = await update.message.reply_text("⌛ Starting Full Deep Scan (Top 100)...")
    await perform_and_send_scan(context, status_msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await perform_and_send_scan(context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Scanner Online.\nDeep Scan (100 pairs) | Results (Top 15) | Max Spread (80%)")

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", handle_scan))
    application.add_handler(CallbackQueryHandler(handle_button))
    application.run_polling(close_loop=False)
            
