# -*- coding: utf-8 -*-
import asyncio
import nest_asyncio
import ccxt.async_support as ccxt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import datetime
import os
from aiohttp import web # Better than Flask for Render bots

nest_asyncio.apply()

# ------------------ CONFIG ------------------
TELEGRAM_TOKEN = '8257534645:AAFR5BWqEykB9m1XehqtQ4mtuCFBjKBNaQ0'
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
            return None
    return None

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
        try: await status_message.edit_text("⚡ **Turbo Scan: 100 Pairs**\nUsing optimized batching...")
        except: pass

    # ✅ STEP 1: OPEN CONNECTIONS ONCE
    exchanges = {}
    for ex_id in EXCHANGE_IDS:
        try:
            exchanges[ex_id] = getattr(ccxt, ex_id)({'enableRateLimit': True, 'timeout': 10000})
        except: continue

    # ✅ STEP 2: PREPARE TASKS
    tasks = []
    for symbol in pairs:
        for ex_id, ex in exchanges.items():
            tasks.append(fetch_price(ex, ex_id, symbol))

    # ✅ STEP 3: BATCHED GATHER (The Fix for the "Hang")
    results = []
    batch_size = 150 # Process 150 at a time instead of 2600
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i : i + batch_size]
        batch_results = await asyncio.gather(*batch, return_exceptions=True)
        results.extend([r for r in batch_results if isinstance(r, tuple)])
        
        # Give progress updates so you know it's working
        if status_message and i % 600 == 0:
            prog = int((i / len(tasks)) * 100)
            try: await status_message.edit_text(f"⌛ **Scanning Market: {prog}%**")
            except: pass

    # ✅ STEP 4: CLOSE CONNECTIONS
    for ex in exchanges.values():
        await ex.close()

    # Analyze Results
    market_data = {p: {} for p in pairs}
    for res in results:
        ex_id, symbol, data = res
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

# ------------------ TELEGRAM & SYSTEM ------------------
async def perform_and_send_scan(context, update=None, status_message=None):
    start = datetime.datetime.now()
    arbs = await scan_markets(status_message)
    duration = (datetime.datetime.now() - start).seconds
    now = datetime.datetime.now().strftime('%H:%M:%S')

    text = f"📊 **Arb Results** ({now})\n\n"
    if not arbs:
        text += "No gaps found (1.2%-80%)."
    else:
        for a in arbs[:15]:
            text += (f"🪙 *{a['symbol']}*\n🟢 {a['low_name'].upper()} (${a['low_p']:.6f})\n"
                     f"🔴 {a['high_name'].upper()} (${a['high_p']:.6f})\n💰 *{a['spread']:.2f}%*\n\n")
    text += f"⏱ **Duration: {duration}s**"

    if status_message:
        try: await status_message.delete()
        except: pass

    for cid in CHAT_IDS:
        await context.bot.send_message(chat_id=cid, text=text, parse_mode='Markdown',
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Scan", callback_data='refresh')]]))

async def handle_health(request):
    return web.Response(text="Bot is Active")

async def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("🚀 Bot Online. /scan to start.")))
    application.add_handler(CommandHandler("scan", lambda u, c: perform_and_send_scan(c, u, u.message.reply_text("⌛ Starting Scan..."))))
    application.add_handler(CallbackQueryHandler(lambda u, c: perform_and_send_scan(c), pattern='^refresh$'))

    # Web Server for Render
    server = web.Application()
    server.router.add_get('/', handle_health)
    runner = web.AppRunner(server); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 10000))).start()
    
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
        
