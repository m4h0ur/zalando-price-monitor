# src/price_monitor.py

import os
import json
import logging
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import threading
import random
import traceback
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global constants
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '3600'))
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
MIN_DELAY = int(os.getenv('RANDOM_DELAY_MIN', '10'))
MAX_DELAY = int(os.getenv('RANDOM_DELAY_MAX', '20'))

def format_price(price):
    """Format price in correct notation (38.99)"""
    return f"€{price:.2f}"

class ZalandoPriceBot:
    def __init__(self):
        self.data_file = 'data/products.json'
        self.products = self.load_products()
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.check_interval = CHECK_INTERVAL
        self._remove_urls = {}
        self.updater = None
        self.debug_mode = DEBUG_MODE
        self.session = self._create_session()
        self.retry_count = {}

    def _create_session(self):
        """Create a session with default headers and cookies"""
        session = requests.Session()
        session.cookies.update({
            'frsx-enabled': 'false',
            'language': 'nl',
            'country': 'NL',
        })
        return session

    def _get_headers(self):
        """Get randomized headers for requests"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15'
        ]
        
        return {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1',
        }

    def load_products(self):
        try:
            os.makedirs('data', exist_ok=True)
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading products: {e}")
        return {}

    def save_products(self):
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.products, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving products: {e}")

    def is_valid_zalando_url(self, url):
        try:
            parsed = urlparse(url)
            return parsed.netloc == 'www.zalando.nl'
        except:
            return False

    def _handle_retry(self, url):
        """Handle retry logic with exponential backoff"""
        if url not in self.retry_count:
            self.retry_count[url] = 0
        
        self.retry_count[url] += 1
        delay = min(300, 30 * (2 ** (self.retry_count[url] - 1)))  # Max 5 minutes
        time.sleep(delay)
        
        if self.retry_count[url] >= 3:  # Reset after 3 retries
            self.retry_count[url] = 0
            return False
        return True

    def get_price(self, url):
        try:
            headers = self._get_headers()
            
            # Visit homepage first
            try:
                homepage_response = self.session.get(
                    'https://www.zalando.nl/',
                    headers=headers,
                    timeout=10
                )
                time.sleep(random.uniform(2, 4))
            except Exception as e:
                logger.warning(f"Failed to visit homepage: {e}")

            # Add random delay
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            
            # Update headers
            headers = self._get_headers()
            
            # Get product page
            response = self.session.get(
                url,
                headers=headers,
                timeout=15,
                allow_redirects=True
            )
            
            if response.status_code == 403:
                if self._handle_retry(url):
                    return self.get_price(url)
                else:
                    raise Exception("Max retries reached")
            
            response.raise_for_status()
            
            if 'captcha' in response.text.lower():
                raise ValueError("Captcha detected")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if self.debug_mode:
                with open('debug_response.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
            
            # Find product name
            name_selectors = [
                ('span', {'data-testid': 'product-name'}),
                ('h1', {'data-testid': 'product-name'}),
                ('span', {'class': 'EKabf7'}),
                ('h1', {'class': 'OEhtt9'}),
                ('h1', {'class': 'FZrqF6'}),
                ('div', {'data-testid': 'product-name'})
            ]
            
            name_element = None
            for tag, attrs in name_selectors:
                name_element = soup.find(tag, attrs)
                if name_element:
                    break
            
            if not name_element:
                # Fallback: find any heading with product-like content
                for element in soup.find_all(['h1', 'h2']):
                    if element.text.strip() and len(element.text.strip()) > 10:
                        name_element = element
                        break
            
            if not name_element:
                raise ValueError("Product name not found")
            
            product_name = name_element.text.strip()
            
            # Find price
            price_selectors = [
                ('span', {'data-testid': 'product-price'}),
                ('span', {'class': 'sDq_FX'}),
                ('span', {'class': 'VfpFfd'}),
                ('span', {'class': 'QPDz2E'}),
                ('p', {'data-testid': 'price'})
            ]
            
            price_element = None
            for tag, attrs in price_selectors:
                elements = soup.find_all(tag, attrs)
                for element in elements:
                    if element and '€' in element.text and any(c.isdigit() for c in element.text):
                        price_element = element
                        break
                if price_element:
                    break
            
            if not price_element:
                # Fallback: find any element with price-like content
                for element in soup.find_all(['span', 'p', 'div']):
                    if '€' in element.text and any(c.isdigit() for c in element.text):
                        price_element = element
                        break
            
            if not price_element:
                raise ValueError("Price element not found")

            price_text = price_element.text.strip()
            # Clean up price text
            price_text = ''.join(c for c in price_text if c.isdigit() or c in '.,')
            price_text = price_text.replace(',', '.')
            
            if price_text.count('.') > 1:
                parts = price_text.split('.')
                price_text = ''.join(parts[:-1]) + '.' + parts[-1]
            
            price = float(price_text)
            
            # Convert if price seems to be in cents
            if price > 1000 and '.' not in price_text:
                price = price / 100

            # Reset retry count on success
            self.retry_count[url] = 0
            
            logger.info(f"Successfully found price for {product_name}: {format_price(price)}")
            return price, product_name
                
        except Exception as e:
            logger.error(f"Error getting price for {url}: {str(e)}")
            logger.error(traceback.format_exc())
            return None, None

    def start(self, update: Update, context: CallbackContext):
        help_text = """
🤖 Welcome to Zalando Price Monitor Bot!

Available commands:
/add <url> - Start monitoring a new product
/list - List all monitored products
/remove - Remove a product from monitoring
/help - Show this help message
/status - Check bot status

Simply send me a Zalando.nl product URL and I'll monitor its price!
"""
        update.message.reply_text(help_text)

    def help(self, update: Update, context: CallbackContext):
        self.start(update, context)

    def status(self, update: Update, context: CallbackContext):
        chat_id = str(update.effective_chat.id)
        total_products = len(self.products.get(chat_id, {}))
        
        status_text = (
            "📊 Bot Status\n\n"
            f"🔄 Check Interval: {self.check_interval} seconds\n"
            f"📦 Your Monitored Products: {total_products}\n"
            "✅ Bot is running normally"
        )
        update.message.reply_text(status_text)

    def add_product(self, update: Update, context: CallbackContext):
        try:
            if len(context.args) < 1:
                update.message.reply_text(
                    "Please provide a Zalando.nl product URL\n"
                    "Example: /add https://www.zalando.nl/product-url"
                )
                return

            url = context.args[0]
            if not self.is_valid_zalando_url(url):
                update.message.reply_text("Please provide a valid Zalando.nl URL")
                return

            chat_id = str(update.effective_chat.id)
            if chat_id not in self.products:
                self.products[chat_id] = {}

            if url in self.products[chat_id]:
                update.message.reply_text("This product is already being monitored!")
                return

            update.message.reply_text("🔍 Fetching product information...")
            price, name = self.get_price(url)

            if price is None or not name:
                update.message.reply_text(
                    "Sorry, I couldn't fetch the product information. Please check if:\n"
                    "1. The URL is correct\n"
                    "2. The product is still available\n"
                    "3. The website is accessible\n\n"
                    "Try again in a few minutes."
                )
                return

            self.products[chat_id][url] = {
                'name': name,
                'last_price': price,
                'last_check': datetime.now().isoformat(),
                'added_date': datetime.now().isoformat()
            }
            self.save_products()

            update.message.reply_text(
                f"✅ Added to monitoring:\n"
                f"📦 {name}\n"
                f"💰 Current price: {format_price(price)}\n"
                f"⏰ Check interval: {self.check_interval} seconds\n"
                f"I'll notify you when the price changes!"
            )

        except Exception as e:
            logger.error(f"Error adding product: {e}")
            update.message.reply_text("Sorry, something went wrong. Please try again.")

    def list_products(self, update: Update, context: CallbackContext):
        chat_id = str(update.effective_chat.id)
        if chat_id not in self.products or not self.products[chat_id]:
            update.message.reply_text("You have no products being monitored.")
            return

        message = "📊 Your Monitored Products:\n\n"
        for url, data in self.products[chat_id].items():
            message += f"📦 {data['name']}\n"
            message += f"💰 Last price: {format_price(data['last_price'])}\n"
            message += f"⏰ Added: {datetime.fromisoformat(data['added_date']).strftime('%Y-%m-%d')}\n"
            message += f"🔗 {url}\n\n"

        update.message.reply_text(message)

    def remove_product(self, update: Update, context: CallbackContext):
        chat_id = str(update.effective_chat.id)
        if chat_id not in self.products or not self.products[chat_id]:
            update.message.reply_text("You have no products to remove.")
            return

        self._remove_urls.clear()
        
        keyboard = []
        for i, (url, data) in enumerate(self.products[chat_id].items()):
            callback_data = f"rm_{i}"
            self._remove_urls[callback_data] = url
            keyboard.append([InlineKeyboardButton(
                f"{data['name']} ({format_price(data['last_price'])})",
                callback_data=callback_data
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Select a product to remove:", reply_markup=reply_markup)

    def button_callback(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()

        if query.data.startswith('rm_'):
            chat_id = str(update.effective_chat.id)
            if query.data in self._remove_urls:
                url = self._remove_urls[query.data]
                if chat_id in self.products and url in self.products[chat_id]:
                    product_name = self.products[chat_id][url]['name']
                    del self.products[chat_id][url]
                    self.save_products()
                    query.edit_message_text(f"✅ Removed {product_name} from monitoring.")
                else:
                    query.edit_message_text("❌ Error: Product not found.")
            else:
                query.edit_message_text("❌ Error: Invalid removal request.")

    def check_prices(self):
        while True:
            try:
                for chat_id in list(self.products.keys()):
                    for url, data in list(self.products[chat_id].items()):
                        logger.info(f"Checking price for {url}")
                        current_price, _ = self.get_price(url)
                        
                        if current_price is None:
                            logger.warning(f"Could not fetch price for {data['name']}")
                            continue

                        if current_price != data['last_price']:
                            change = current_price - data['last_price']
                            change_percent = (change / data['last_price']) * 100
                            
                            message = (
                                f"💰 Price Change Alert!\n\n"
                                f"📦 {data['name']}\n"
                                f"Old price: {format_price(data['last_price'])}\n"
                                f"New price: {format_price(current_price)}\n"
                                f"Change: {'📈' if change > 0 else '📉'} {format_price(abs(change))} ({change_percent:+.1f}%)\n\n"
                                f"🔗 {url}"
                            )
                            
                            try:
                                self.updater.bot.send_message(chat_id=int(chat_id), text=message)
                                logger.info(f"Sent price alert for {data['name']}")
                            except Exception as e:
                                logger.error(f"Failed to send message: {e}")
                            
                            self.products[chat_id][url]['last_price'] = current_price
                            self.products[chat_id][url]['last_check'] = datetime.now().isoformat()
                            self.save_products()
                        
                        # Add random delay between checks to avoid detection
                        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                
                # Add random delay between check cycles
                sleep_time = self.check_interval + random.randint(60, 180)
                logger.info(f"Sleeping for {sleep_time} seconds before next check cycle")
                time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Error in price check loop: {e}")
                logger.error(traceback.format_exc())
                time.sleep(60)

    def run(self):
        try:
            logger.info("Starting Zalando Price Monitor bot...")
            self.updater = Updater(self.token, use_context=True)
            dp = self.updater.dispatcher

            # Add command handlers
            dp.add_handler(CommandHandler("start", self.start))
            dp.add_handler(CommandHandler("help", self.help))
            dp.add_handler(CommandHandler("add", self.add_product))
            dp.add_handler(CommandHandler("list", self.list_products))
            dp.add_handler(CommandHandler("remove", self.remove_product))
            dp.add_handler(CommandHandler("status", self.status))
            dp.add_handler(CallbackQueryHandler(self.button_callback))

            # Start price checking in a separate thread
            threading.Thread(target=self.check_prices, daemon=True).start()
            
            logger.info("Bot is running!")
            self.updater.start_polling()
            self.updater.idle()
            
        except Exception as e:
            logger.error(f"Critical error: {e}")
            logger.error(traceback.format_exc())

def main():
    try:
        # Create data directory if it doesn't exist
        os.makedirs('data', exist_ok=True)
        
        # Initialize and run the bot
        bot = ZalandoPriceBot()
        bot.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()