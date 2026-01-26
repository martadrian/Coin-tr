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

# --- WEB SERVER FOR RENDER ---
app_web = Flask(__name__)
@app_web.route('/')
def health(): return "Scanner is Active"

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
    'gemini', 'cryptocom', 'exmo', 'latoken', 'fmfwio', 'oceanex', 'bigone', 'paymium', 'btcturk'
]

limit_concurrency = asyncio.Semaphore(10)

async def fetch_price(exchange_id, symbol):
    """Fetch price and explicitly close the connection to prevent leaks"""
    async with limit_concurrency:
        if not hasattr(ccxt, exchange_id): return exchange_id, None
        # Initialize exchange
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
            await exchange.close() # THIS FIXES THE RESOURCE LEAK
        return exchange_id, None

async def scan_markets():
    """Main scanning logic with proper resource cleanup"""
    async with ccxt.mexc() as discovery_ex:
        try:
            tickers = await discovery_ex.fetch_tickers()
            pairs = sorted([s for s in tickers if s.endswith('/USDT')], 
                           key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:40]
        except:
            pairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT']

    all_arbs = []
    for symbol in pairs:
        tasks = [fetch_price(ex, symbol) for ex in EXCHANGE_IDS]
        results = await asyncio.gather(*tasks)
        valid_data = {ex: data for ex, data in results if data}
        
        if len(valid_data) > 1:
            items = sorted(valid_data.items(), key=lambda x: x[1]['price'])
            low_ex_name, low_data = items[0]
            high_ex_name, high_data = items[-1]
            
            spread = ((high_data['price'] - low_data['price']) / low_data['price']) * 100
            
            if 1.2 < spread < 50.0:
                all_arbs.append({
                    'symbol': symbol,
                    'low_name': low_ex_name, 'low_p': low_data['price'],
                    'high_name': high_ex_name, 'high_p': high_data['price'],
                    'spread': spread
                })
    return all_arbs

async def background_loop(app):
    """The 24/7 background engine"""
    print("🚀 Background Engine Started...")
    while True:
        try:
            now = datetime.datetime.now().strftime('%H:%M:%S')
            arbs = await scan_markets()
            
            if arbs:
                text = f"🚨 **Arbitrage Alert** ({now})\n\n"
                for a in arbs[:6]:
                    text += (f"🪙 *{a['symbol']}*\n"
                             f"🟢 Buy: {a['low_name'].upper()} (${a['low_p']:.6f})\n"
                             f"🔴 Sell: {a['high_name'].upper()} (${a['high_p']:.6f})\n"
                             f"💰 Potential: *{a['spread']:.2f}%*\n\n")
            else:
                text = f"ℹ️ **Scan Complete** ({now})\nNo gaps found > 1.2%."

            await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode='Markdown')
            print(f"✅ Message sent to Telegram at {now}")
            
            await asyncio.sleep(180) # Wait 3 minutes
        except Exception as e:
            print(f"❌ Loop Error: {e}")
            await asyncio.sleep(60)

if __name__ == '__main__':
    # 1. Start Web Server
    threading.Thread(target=run_flask, daemon=True).start()

    # 2. Setup Telegram Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # 3. Start the background scan task
    loop = asyncio.get_event_loop()
    loop.create_task(background_loop(application))

    # 4. Start Telegram Polling
    print("Bot is fully starting...")
    application.run_polling(close_loop=False)
