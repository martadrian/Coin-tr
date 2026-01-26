# -*- coding: utf-8 -*-
import asyncio
import nest_asyncio
import ccxt.async_support as ccxt
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import datetime

# --- APPLY LOOP PATCH ---
nest_asyncio.apply()

# --- CONFIGURATION ---
TELEGRAM_TOKEN = '8347545464:AAFFpwW2O5P4lt-cS5x1AW6Llx9Z2jKkgr4'

# 🔒 SECURITY: Only these User IDs receive alerts
ALLOWED_USERS = [6089058395, 987654321]

EXCHANGE_IDS = [
    'bybit', 'mexc', 'gate', 'kucoin', 'bitget', 'okx', 'huobi', 'lbank', 'bitmart', 'poloniex',
    'digifinex', 'xt', 'phemex', 'probit', 'coinex', 'bingx', 'whitebit', 'bitrue', 'ascendex',
    'hitbtc', 'toobit', 'woo', 'woofipro', 'blofin', 'bitfinex', 'kraken', 'bitstamp', 'coinbase',
    'gemini', 'cryptocom', 'exmo', 'latoken', 'fmfwio', 'oceanex', 'bigone', 'paymium', 'btcturk'
]

# --- CORE LOGIC ---

async def get_top_100_pairs():
    """Reference Binance for discovery to avoid proxy issues common on free tiers"""
    async with ccxt.binance({'enableRateLimit': True}) as ex:
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
        try:
            async with getattr(ccxt, exchange_id)({'timeout': 7000, 'enableRateLimit': True}) as exchange:
                ticker = await exchange.fetch_ticker(symbol)
                price = ticker.get('last')
                volume = float(ticker.get('quoteVolume', 0) or 0)
                if price and price > 0:
                    return exchange_id, {'price': price, 'volume': volume}
        except: pass
        return exchange_id, None

async def scan_markets():
    top_pairs = await get_top_100_pairs()
    all_arbs = []
    active_pairs = top_pairs[:50] 

    for symbol in active_pairs:
        tasks = [fetch_price(ex, symbol) for ex in EXCHANGE_IDS]
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=25.0)
            valid_data = {ex: data for ex, data in results if data}
            
            if len(valid_data) > 1:
                sorted_items = sorted(valid_data.items(), key=lambda x: x[1]['price'])
                low_ex, low_data = sorted_items[0]
                high_ex, high_data = sorted_items[-1]
                
                spread = ((high_data['price'] - low_data['price']) / low_data['price']) * 100
                
                if 1.2 < spread < 50.0:
                    all_arbs.append({
                        'symbol': symbol,
                        'low_ex': low_ex, 'low_p': low_data['price'],
                        'high_ex': high_ex, 'high_p': high_data['price'],
                        'spread': spread,
                        'volume': high_data['volume']
                    })
        except: continue

    return sorted(all_arbs, key=lambda x: x['spread'], reverse=True)

# --- BACKGROUND AUTO-ALERT SYSTEM ---

async def background_scanner(app):
    """Runs forever, scanning every 3 minutes and reporting results"""
    print("🚀 Auto-Alert Loop Started!")
    
    while True:
        try:
            now = datetime.datetime.now().strftime('%H:%M:%S')
            print(f"⏰ Auto-Scan starting at {now}...")
            
            arbs = await scan_markets()

            if arbs:
                text = f"🚨 **Arbitrage Found!** ({now})\n\n"
                for arb in arbs[:5]:
                    text += (
                        f"🪙 *{arb['symbol']}*\n"
                        f"🟢 Buy: {arb['low_ex'].upper()} (${arb['low_p']:.6f})\n"
                        f"🔴 Sell: {arb['high_ex'].upper()} (${arb['high_p']:.6f})\n"
                        f"💰 Profit: *{arb['spread']:.2f}%*\n\n"
                    )
            else:
                # This ensures you get a message even if nothing is found
                text = f"ℹ️ **Scan Complete** ({now})\nNo gaps found above 1.2% in this round."

            # Send result to ALL allowed users
            for user_id in ALLOWED_USERS:
                try:
                    await app.bot.send_message(chat_id=user_id, text=text, parse_mode='Markdown')
                except Exception as e:
                    print(f"❌ Alert Error: {e}")

            print(f"💤 Scan finished. Waiting 3 minutes...")
            await asyncio.sleep(180) # 3-minute interval

        except Exception as e:
            print(f"❌ Loop Error: {e}")
            await asyncio.sleep(60)

# --- TELEGRAM HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in ALLOWED_USERS:
        await update.message.reply_text("✅ Bot Online. Scanning every 3 minutes...")

if __name__ == '__main__':
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    # Start the loop
    loop = asyncio.get_event_loop()
    loop.create_task(background_scanner(application))

    print("Bot is running...")
    application.run_polling(close_loop=False)
              
