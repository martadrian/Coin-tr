# -*- coding: utf-8 -*-
import asyncio
import nest_asyncio
import ccxt.async_support as ccxt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import datetime
import os
from aiohttp import web  # New: Required for Render health checks

# --- APPLY LOOP PATCH ---
nest_asyncio.apply()

# --- CONFIGURATION ---
# It's better to keep your token in environment variables, but I've left your original here.
TELEGRAM_TOKEN = '8132941174:AAExO2F-1DBKMGkXA8kcudBWqzCUGcy6njg'
CHAT_ID = '6089058395'

EXCHANGE_IDS = [
    'bybit', 'mexc', 'gate', 'kucoin', 'bitget', 'okx', 'huobi', 'lbank', 'bitmart', 'poloniex',
    'digifinex', 'xt', 'phemex', 'probit', 'coinex', 'bingx', 'whitebit', 'bitrue', 'ascendex',
    'hitbtc', 'toobit', 'woo', 'woofipro', 'blofin', 'bitfinex', 'kraken', 'bitstamp', 'coinbase',
    'gemini', 'cryptocom', 'exmo', 'latoken', 'fmfwio', 'oceanex', 'bigone', 'paymium', 'btcturk',
    'independentreserve', 'coincheck', 'zaif', 'bitbank', 'bithumb', 'coinone', 'korbit', 'paribu',
    'tidex', 'dextrade', 'vitex', 'wavesexchange', 'bequant', 'timex'
]

# --- CORE LOGIC ---

async def get_top_100_pairs():
    async with ccxt.mexc({'enableRateLimit': True}) as ex:
        try:
            tickers = await ex.fetch_tickers()
            usdt_pairs = [s for s in tickers if s.endswith('/USDT')]
            sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)
            return sorted_pairs[:100]
        except Exception as e:
            print(f"⚠️ Discovery Error: {e}")
            return ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT']

limit_concurrency = asyncio.Semaphore(15)

async def fetch_price(exchange_id, symbol):
    async with limit_concurrency:
        if not hasattr(ccxt, exchange_id):
            return exchange_id, None
        config = {'timeout': 7000, 'enableRateLimit': True}
        try:
            async with getattr(ccxt, exchange_id)(config) as exchange:
                ticker = await exchange.fetch_ticker(symbol)
                price = ticker.get('last')
                raw_vol = ticker.get('quoteVolume', 0)
                volume = float(raw_vol) if raw_vol is not None else 0.0
                if price is None or price <= 0 or volume < 100:
                    return exchange_id, None
                return exchange_id, {'price': price, 'volume': volume}
        except:
            return exchange_id, None

async def scan_markets(status_message=None):
    top_pairs = await get_top_100_pairs()
    all_arbs = []
    active_pairs = top_pairs[:50]
    for i, symbol in enumerate(active_pairs):
        if status_message and i % 2 == 0:
            progress = int((i / len(active_pairs)) * 100)
            try:
                await status_message.edit_text(
                    f"⌛ **Turbo Scan Progress: {progress}%**\n🔍 Checking: `{symbol}`\n📈 Gaps Found: {len(all_arbs)}"
                )
            except: pass
        tasks = [fetch_price(ex, symbol) for ex in EXCHANGE_IDS]
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=20.0)
        except asyncio.TimeoutError:
            results = []
        valid_data = {ex: data for ex, data in results if data is not None and isinstance(data, dict)}
        if len(valid_data) > 1:
            sorted_items = sorted(valid_data.items(), key=lambda x: x[1]['price'])
            low_ex, low_data = sorted_items[0]
            high_ex, high_data = sorted_items[-1]
            low_p, high_p = low_data['price'], high_data['price']
            spread = ((high_p - low_p) / low_p) * 100
            if 1.2 < spread < 80.0:
                all_arbs.append({'symbol': symbol, 'low_ex': low_ex, 'low_p': low_p, 'high_ex': high_ex, 'high_p': high_p, 'spread': spread, 'volume': high_data.get('volume', 0)})
    return sorted(all_arbs, key=lambda x: x['spread'], reverse=True)

# --- TELEGRAM HANDLERS ---

async def perform_and_send_scan(context, chat_id, status_message=None):
    try:
        arbs = await scan_markets(status_message)
        if not arbs:
            text = "🔍 Scan complete. No tradable gaps found (1.2% - 80%)."
        else:
            text = f"📊 *Live Arbitrage (Filtered)*\n🕒 {datetime.datetime.now().strftime('%H:%M:%S')}\n\n"
            for arb in arbs[:7]:
                vol = arb.get('volume', 0)
                vol_str = f"${vol:,.0f}" if vol > 0 else "Low Vol"
                text += (f"🪙 *{arb['symbol']}*\n🟢 Buy: {arb['low_ex'].upper()} (${arb['low_p']:.8f})\n🔴 Sell: {arb['high_ex'].upper()} (${arb['high_p']:.8f})\n💰 Potential: *{arb['spread']:.2f}%*\n📊 24h Vol: {vol_str}\n\n")
    except Exception as e:
        text = f"❌ **Scan Error:** `{str(e)}`"
    if status_message:
        try: await status_message.delete()
        except: pass
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Scan", callback_data='refresh')]]))

async def handle_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⌛ Starting Secure Bybit Scan...")
    await perform_and_send_scan(context, update.effective_chat.id, status_msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await perform_and_send_scan(context, query.message.chat_id, query.message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Professional Arbitrage Bot Online.\n/scan to start.")

# --- NEW: RENDER HEALTH CHECK SERVER ---
async def health_check(request):
    return web.Response(text="I am alive!")

async def main():
    # 1. Start the Telegram Bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", handle_scan))
    application.add_handler(CallbackQueryHandler(handle_button, pattern='^refresh$'))

    # 2. Start a tiny Web Server for Render
    server = web.Application()
    server.router.add_get('/', health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # 3. Keep everything running
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        print(f"Bot and Health Check running on port {port}...")
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
