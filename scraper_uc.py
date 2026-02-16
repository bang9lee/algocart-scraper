"""
Coupang Scraper using invisible window (headless=False but positioned off-screen)
"""
import sys
import json
import re
import time
import os
from pathlib import Path
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configure stdout for utf-8
sys.stdout.reconfigure(encoding='utf-8')

def scrape(url):
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    # Render/server 환경에서는 headless 실행이 필요합니다.
    if os.getenv("SCRAPER_HEADLESS", "1") == "1":
        options.add_argument("--headless=new")

    chrome_bin = os.getenv("CHROME_BIN") or os.getenv("CHROME_BINARY")
    if not chrome_bin:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/opt/google/chrome/chrome",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                chrome_bin = candidate
                break

    if chrome_bin:
        options.binary_location = chrome_bin
    
    # We use visible (headless=False) mode to bypass anti-bot
    # Window move off-screen to minimize disruption
    
    try:
        driver = uc.Chrome(options=options, use_subprocess=False)
    except Exception as e:
        return {"error": f"Chrome launch failed: {str(e)}"}
    
    try:
        driver.set_window_position(-10000, 0)
        driver.get(url)
        
        # Wait for title to appear
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "title"))
            )
        except:
            pass
        
        # Check Access Denied
        if "Access Denied" in driver.title:
           time.sleep(2)
           driver.refresh()
           time.sleep(3)
           if "Access Denied" in driver.title:
               driver.quit()
               return {"error": "Access Denied (Detection)"}

        # Scroll to load dynamic prices
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(1.5)

        html = driver.page_source
        
        # Title
        page_title = ""
        m = re.search(r'<meta\s+(?:property="og:title"\s+content="([^"]+)"|content="([^"]+)"\s+property="og:title")', html, re.I)
        if m:
            page_title = m.group(1) or m.group(2)
        if not page_title:
             page_title = re.sub(r'\s*[|\-–]\s*쿠팡.*$', '', driver.title).strip()
             
        # Price extraction - Prioritized Strategy
        price = 0
        
        # Strategy 0: JSON-LD (Most Reliable for Sale Price)
        if not price:
            try:
                scripts = driver.find_elements(By.XPATH, "//script[@type='application/ld+json']")
                for script in scripts:
                    try:
                        content = script.get_attribute('innerHTML')
                        data = json.loads(content)
                        
                        # Normalize to list
                        items = data if isinstance(data, list) else [data]
                        
                        for item in items:
                            if item.get('@type') in ['Product', 'SoftwareApplication']:
                                offers = item.get('offers')
                                if offers:
                                    offer_list = offers if isinstance(offers, list) else [offers]
                                    for offer in offer_list:
                                        p = offer.get('price')
                                        if p:
                                            price = int(float(p))
                                            break
                            if price: break
                    except:
                        continue
                    if price: break
            except:
                pass

        # Strategy 1: Look for explicit "sale price" or "coupon price" elements first via JS
        if not price:
            try:
                val = driver.execute_script("""
                    // Priority 1: Coupon price (usually lowest)
                    let el = document.querySelector('.prod-coupon-price .total-price > strong');
                    if (el && el.innerText.trim()) return el.innerText;
                    
                    // Priority 2: Sale price (Rocket/Discount)
                    el = document.querySelector('.prod-sale-price .total-price > strong');
                    if (el && el.innerText.trim()) return el.innerText;
                    
                    // Priority 3: Unit price (sometimes useful but skip for now)
                    
                    // Priority 4: Standard total price
                    el = document.querySelector('.total-price > strong');
                    if (el && el.innerText.trim()) return el.innerText;
                    
                    return '';
                """)
                if val:
                    price = int(re.sub(r'[^\d]', '', val) or '0')
            except:
                pass

        # Strategy 2: Look for JSON data "salePrice" (reliable backup)
        if not price:
             m = re.search(r'"salePrice"\s*:\s*(\d+)', html)
             if m:
                 price = int(m.group(1))

        # Strategy 3: Meta tag (often outdated or original price, so lower priority)
        if not price:
            m = re.search(r'<meta\s+(?:property="product:price:amount"\s+content="([^"]+)"|content="([^"]+)"\s+property="product:price:amount")', html, re.I)
            if m:
                val = m.group(1) or m.group(2)
                price = int(re.sub(r'[^\d]', '', val) or '0')

        # Strategy 4: Fallback text search, but exclude "original price" context
        if not price:
            try:
                # Get visible text of price area only if possible
                body_text = driver.execute_script("""
                    // Try to get text from the price-container specifically
                    const priceArea = document.querySelector('.prod-price-container') || document.body;
                    return priceArea.innerText;
                """)
                
                # Find all prices
                matches = re.findall(r'(\d{1,3}(?:,\d{3})*)\s*원', body_text)
                valid_prices = []
                for p in matches:
                    p_int = int(p.replace(',', ''))
                    if p_int > 100:
                        valid_prices.append(p_int)
                
                if valid_prices:
                    # Look for prices > 2000 won to filter out unit prices (e.g. 10g당 100원)
                    reasonable_prices = [p for p in valid_prices if p > 2000]
                    if reasonable_prices:
                        price = min(reasonable_prices) 
                    elif valid_prices:
                        price = max(valid_prices) # Fallback to max if all seem small? Or min?
            except:
                pass

        # Image
        image = ""
        m = re.search(r'<meta\s+(?:property="og:image"\s+content="([^"]+)"|content="([^"]+)"\s+property="og:image")', html, re.I)
        if m:
            image = m.group(1) or m.group(2)
            if image.startswith('//'):
                image = 'https:' + image
                
        return {"title": page_title, "price": price, "image": image}
        
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "URL required"}))
        sys.exit(1)
        
    url = sys.argv[1]
    try:
        result = scrape(url)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
