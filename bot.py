# -*- coding: utf-8 -*-
import asyncio
import nest_asyncio
import ccxt.async_support as ccxt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import datetime
import os
from aiohttp import web

nest_asyncio.apply()

# ------------------ CONFIGURATION ------------------
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
            return None
        return None

# ------------------ SCAN LOGIC ------------------
async def scan_markets(status_message=None):
    discovery_ex = ccxt.mexc()
    try:
        tickers = await discovery_ex.fetch_tickers()
        pairs = sorted([s for s in tickers if s.endswith('/USDT')], 
                       key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:100]
    except:
        pairs = ['BTC/USDT','ETH/USDT','SOL/USDT']
    finally:
        await discovery_ex.close()

    if status_message:
        try: await status_message.edit_text("⚡ **Turbo Scan: 100 Pairs**\nUsing Stable-Batch technology...")
        except: pass

    exchanges = {}
    for ex_id in EXCHANGE_IDS:
        try:
            ex_class = getattr(ccxt, ex_id)
            exchanges[ex_id] = ex_class({'enableRateLimit': True, 'timeout': 7000})
        except: continue

    tasks = [fetch_price(exchanges[ex_id], ex_id, symbol) for symbol in pairs for ex_id in EXCHANGE_IDS]
    
    results = []
    batch_size = 150 # Safe chunk size for Render Free CPU
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i : i + batch_size]
        batch_results = await asyncio.gather(*batch, return_exceptions=True)
        results.extend([r for r in batch_results if isinstance(r, tuple)])
        await asyncio.sleep(0.05)

    for ex in exchanges.values():
        await ex.close()

    market_data = {p: {} for p in pairs}
    for res in results:
        if res:
            ex_id, symbol, data = res
            market_data[symbol][ex_id] = data

    arbs = []
    for symbol, exs in market_data.items():
        if len(exs) > 1:
            items = sorted(exs.items(), key=lambda x: x[1]['price'])
            low_n, low_p = items[0][0], items[0][1]['price']
            high_n, high_p = items[-1][0], items[-1][1]['price']
            spread = ((high_p - low_p) / low_p) * 100
            if 1.2 < spread < 80:
                arbs.append({'symbol': symbol, 'low_name': low_n, 'low_p': low_p, 
                             'high_name': high_n, 'high_p': high_p, 'spread': spread, 'volume': items[-1][1]['volume']})

    return sorted(arbs, key=lambda x: x['spread'], reverse=True)

# ------------------ HANDLERS ------------------
async def perform_and_send_scan(context, status_message=None):
    start = datetime.datetime.now()
    arbs = await scan_markets(status_message)
    duration = (datetime.datetime.now() - start).seconds
    now = datetime.datetime.now().strftime('%H:%M:%S')

    if not arbs:
        text = f"🔍 **Scan Complete** ({now})\nNo gaps found.\n⏱ {duration}s"
    else:
        text = f"📊 **Top 15 Results** ({now})\n\n"
        for a in arbs[:15]:
            text += (f"🪙 *{a['symbol']}*\n🟢 {a['low_name'].upper()} (${a['low_p']:.4f})\n"
                     f"🔴 {a['high_name'].upper()} (${a['high_p']:.4f})\n💰 *{a['spread']:.2f}%*\n\n")
        text += f"⏱ {duration}s | ⚡ Stable-Batch"

    if status_message:
        try: await status_message.delete()
        except: pass

    for cid in CHAT_IDS:
        try:
            await context.bot.send_message(chat_id=cid, text=text, parse_mode='Markdown',
                                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Scan", callback_data='refresh')]]))
        except: pass

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Bot Online. Use /scan")

async def handle_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⌛ Starting Scan...")
    await perform_and_send_scan(context, msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await perform_and_send_scan(context)

# ------------------ ASYNC MAIN LOOP ------------------
async def handle_health(request):
    return web.Response(text="Bot is Active")

async def main():
    # 1. Initialize Bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("scan", handle_scan))
    application.add_handler(CallbackQueryHandler(handle_button))

    # 2. Initialize Web Server (aiohttp)
    server = web.Application()
    server.router.add_get('/', handle_health)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    # 3. Start Web Server
    await site.start()
    print(f"Web server running on port {port}")
    
    # 4. Start Bot Polling
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        print("Bot polling started. All systems green.")
        # This keeps the loop running forever
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    
