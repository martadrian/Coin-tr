# -*- coding: utf-8 -*-
import asyncio
import nest_asyncio
import ccxt.async_support as ccxt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import datetime, os, gc
from aiohttp import web

nest_asyncio.apply()

# ------------------ 1. CONFIGURATION ------------------
TELEGRAM_TOKEN = '8347545464:AAFFpwW2O5P4lt-cS5x1AW6Llx9Z2jKkgr4'
CHAT_IDS = ['6089058395', '-5213714280']

# Optimized list for memory safety (Most reliable API exchanges)
EXCHANGE_IDS = [
    'binance','bybit','mexc','gate','kucoin','bitget','huobi',
    'lbank','bitmart','poloniex','xt','phemex','coinex',
    'bingx','whitebit','bitrue','ascendex','toobit','blofin'
]

limit_concurrency = asyncio.Semaphore(25)

# ------------------ 2. CORE LOGIC ------------------

async def fetch_price(exchange, exchange_id, symbol):
    async with limit_concurrency:
        try:
            ticker = await exchange.fetch_ticker(symbol)
            price = ticker.get('last')
            vol = float(ticker.get('quoteVolume', 0) or 0)
            if price and price > 0 and vol > 1000:
                return exchange_id, symbol, {'price': price, 'volume': vol}
        except: pass
    return None

async def scan_markets(status_message=None):
    # Discovery phase
    discovery_ex = ccxt.mexc({'enableRateLimit': True})
    try:
        tickers = await discovery_ex.fetch_tickers()
        pairs = sorted([s for s in tickers if s.endswith('/USDT')], 
                       key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:50]
    except:
        pairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT']
    finally:
        await discovery_ex.close()

    # Instance Creation
    exchanges = {}
    for ex_id in EXCHANGE_IDS:
        try:
            ex_class = getattr(ccxt, ex_id)
            exchanges[ex_id] = ex_class({'enableRateLimit': True, 'timeout': 6000})
        except: continue

    # Create Task List
    tasks = [fetch_price(exchanges[ex_id], ex_id, symbol) for symbol in pairs for ex_id in EXCHANGE_IDS]
    
    results = []
    batch_size = 100 
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i : i + batch_size]
        batch_results = await asyncio.gather(*batch, return_exceptions=True)
        results.extend([r for r in batch_results if isinstance(r, tuple)])
        
        # UI Update every 300 tasks
        if status_message and i % 300 == 0:
            prog = int((i / len(tasks)) * 100)
            try: await status_message.edit_text(f"⏳ **Scanning... {prog}%**")
            except: pass
        await asyncio.sleep(0.05)

    # Cleanup Connections
    for ex in exchanges.values():
        await ex.close()

    # Process Results
    market_data = {p: {} for p in pairs}
    for res in results:
        ex_id, symbol, data = res
        market_data[symbol][ex_id] = data

    arbs = []
    for symbol, exs in market_data.items():
        if len(exs) > 1:
            items = sorted(exs.items(), key=lambda x: x[1]['price'])
            l_n, l_p = items[0][0], items[0][1]['price']
            h_n, h_p = items[-1][0], items[-1][1]['price']
            spread = ((h_p - l_p) / l_p) * 100
            if 1.2 < spread < 60:
                arbs.append({'symbol': symbol, 'low_name': l_n, 'low_p': l_p, 
                             'high_name': h_n, 'high_p': h_p, 'spread': spread, 'vol': items[-1][1]['volume']})

    # Force RAM cleanup
    del results, market_data
    gc.collect() 
    return sorted(arbs, key=lambda x: x['spread'], reverse=True)

# ------------------ 3. TELEGRAM HANDLERS ------------------

async def perform_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🚀 Starting Secure Multi-Exchange Scan...") if update.message else None
    
    start_time = datetime.datetime.now()
    arbs = await scan_markets(msg)
    duration = (datetime.datetime.now() - start_time).seconds
    now = datetime.datetime.now().strftime('%H:%M:%S')

    if not arbs:
        text = f"🔍 **Scan Complete** ({now})\nNo profitable gaps found.\n⏱ Time: {duration}s"
    else:
        text = f"📊 **Arbitrage Results** ({now})\n\n"
        for a in arbs[:15]:
            text += (f"🪙 *{a['symbol']}*\n"
                     f"🟢 BUY: {a['low_name'].upper()} (${a['low_p']:.6f})\n"
                     f"🔴 SELL: {a['high_name'].upper()} (${a['high_p']:.6f})\n"
                     f"💰 Gap: *{a['spread']:.2f}%*\n"
                     f"📈 Vol: ${a['vol']:,.0f}\n\n")
        text += f"⏱ **Duration: {duration}s**"

    if msg: await msg.delete()
    
    for cid in CHAT_IDS:
        await context.bot.send_message(chat_id=cid, text=text, parse_mode='Markdown',
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh Scan", callback_data='ref')]]))

# ------------------ 4. SYSTEM BOOT ------------------

async def handle_health(request):
    return web.Response(text="Scanner Operational")

async def main():
    # Application Init
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("✅ Bot Online. /scan to begin.")))
    application.add_handler(CommandHandler("scan", perform_scan))
    application.add_handler(CallbackQueryHandler(lambda u, c: perform_scan(u.callback_query, c), pattern='^ref$'))

    # Web Server (Health Check for Render)
    server = web.Application()
    server.router.add_get('/', handle_health)
    runner = web.AppRunner(server); await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    await web.TCPSite(runner, '0.0.0.0', port).start()
    
    # Start Polling
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        print(f"Bot Active on Port {port}")
        while True: await asyncio.sleep(3600)

if __name__ == '__main__':
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): pass
