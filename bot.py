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
    # Render uses port 10000 by default
    port = int(os.environ.get("PORT", 10000))
    # use_reloader=False prevents Render from starting the bot twice
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

# Set to 40 for speed, but keep it stable
limit_concurrency = asyncio.Semaphore(40)

# ------------------ PRICE FETCH ------------------
async def fetch_price(exchange, exchange_id, symbol):
    async with limit_concurrency:
        try:
            # Reusing the existing 'exchange' session
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
    # 1. Discover top pairs
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
        try: await status_message.edit_text("⚡ **Turbo Scan: 100 Pairs**\nReusing exchange sessions for speed...")
        except: pass

    # 2. Setup reusable exchange instances
    exchanges = {}
    for ex_id in EXCHANGE_IDS:
        try:
            ex_class = getattr(ccxt, ex_id)
            exchanges[ex_id] = ex_class({
                'enableRateLimit': True,
                'timeout': 7000
            })
        except:
            continue

    # 3. Gather all prices
    tasks = []
    for symbol in pairs:
        for ex_id, ex in exchanges.items():
            tasks.append(fetch_price(ex, ex_id, symbol))

    # gather_results safely handles the mass requests
    results = await asyncio.gather(*tasks)

    # 4. CRITICAL: Close all connections to prevent memory leak
    for ex in exchanges.values():
        try: await ex.close()
        except: pass

    # 5. Analyze results
    market_data = {p: {} for p in pairs}
    for ex_id, symbol, data in results:
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
                    'symbol': symbol,
                    'low_name': low_n,
                    'low_p': low_d['price'],
                    'high_name': high_n,
                    'high_p': high_d['price'],
                    'spread': spread,
                    'volume': high_d['volume']
                })

    return sorted(arbs, key=lambda x: x['spread'], reverse=True)

# ------------------ TELEGRAM ------------------
async def perform_and_send_scan(context, status_message=None):
    start = datetime.datetime.now()
    arbs = await scan_markets(status_message)
    duration = (datetime.datetime.now() - start).seconds
    now = datetime.datetime.now().strftime('%H:%M:%S')

    if not arbs:
        text = f"🔍 **Scan Complete** ({now})\nNo tradeable gaps found (1.2%-80%).\n⏱ {duration}s"
    else:
        text = f"📊 **Top 15 Arb Results** ({now})\n\n"
        for a in arbs[:15]:
            text += (
                f"🪙 *{a['symbol']}*\n"
                f"🟢 Buy: {a['low_name'].upper()} (${a['low_p']:.6f})\n"
                f"🔴 Sell: {a['high_name'].upper()} (${a['high_p']:.6f})\n"
                f"💰 Potential: *{a['spread']:.2f}%*\n"
                f"📊 Vol: ${a['volume']:,.0f}\n\n"
            )
        text += f"⏱ **Duration: {duration}s** | ⚡ **Reuse-Mod**"

    if status_message:
        try: await status_message.delete()
        except: pass

    for cid in CHAT_IDS:
        try:
            await context.bot.send_message(
                chat_id=cid,
                text=text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔄 New Scan", callback_data='refresh')]]
                )
            )
        except: pass

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 **Scanner Online**\nUse /scan to start.")

async def handle_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⌛ Starting Optimized Scan...")
    await perform_and_send_scan(context, msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await perform_and_send_scan(context)

# ------------------ RUN ------------------
if __name__ == '__main__':
    # Start Web Server
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Bot
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("scan", handle_scan))
    app.add_handler(CallbackQueryHandler(handle_button))

    print("Bot is Polling (Reuse Strategy)...")
    app.run_polling(drop_pending_updates=True, close_loop=False)
    
