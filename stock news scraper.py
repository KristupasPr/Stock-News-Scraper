import requests
from bs4 import BeautifulSoup
import re
import google.generativeai as genai
import discord
from discord.ext import commands
import asyncio
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
import json
from threading import Thread


genai.configure(api_key='-') #insert api key

intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

def load_keywords():
    try:
        with open('keywords.json', 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return ["raktazodis"]

def save_keywords(keywords):
    with open('keywords.json', 'w') as file:
        json.dump(keywords, file)

keywords = load_keywords()

def clean_description(description):
    cleaned_description = re.sub(r'Most Read from Bloomberg.*', '', description).strip()
    return cleaned_description

def summarize_text_gemini(text, prompt):
    try:
        response = genai.generate_text(
            model='models/text-bison-001',
            prompt=f"{prompt} {text}",
            temperature=0.2,
            max_output_tokens=200
        )
        if response and hasattr(response, 'result') and response.result:
            summary = response.result.strip()
        else:
            summary = 'Summary not available.'
        return summary
    except Exception as e:
        print(f"An error occurred while summarizing: {e}")
        return "Summary not available due to an error."

async def scrape_yahoo_finance(keyword, channel_id, prompt, sent_summaries, sent_links):
    print(f"Scraping Yahoo Finance for keyword: {keyword}")  #debug output
    url = "https://finance.yahoo.com/topic/stock-market-news/"

    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to retrieve news: {response.status_code}")
        return

    soup = BeautifulSoup(response.content, "html.parser")
    articles = soup.find_all('div', {'class': 'Ov(h) Pend(44px) Pstart(25px)'}, limit=5)

    print(f"Found {len(articles)} articles.")  #debug output
    for article in articles:
        headline = article.find('h3').text.strip()
        description = article.find('p').text.strip()
        description = clean_description(description)

        link = article.find('a')['href']
        if not link.startswith('http'):
            link = "https://finance.yahoo.com" + link

        print(f"Scraped: {headline}, {description}, {link}") #debug output

        if keyword.lower() in headline.lower() or keyword.lower() in description.lower():
            full_text = extract_article_text(link)
            print(f"Extracted article text for debugging:\n{full_text}\n")

            summary = summarize_text_gemini(full_text, prompt)
            print(f"Summary:\n{summary}\n")

            if summary not in sent_summaries and link not in sent_links:
                sent_summaries.add(summary)
                sent_links.add(link)
                await send_summary_to_discord(channel_id, summary, link)

def extract_article_text(article_url):
    response = requests.get(article_url)
    if response.status_code != 200:
        print(f"Failed to retrieve article: {article_url}")
        return "Error retrieving article content."

    soup = BeautifulSoup(response.text, "html.parser")
    article_body = soup.find('div', class_='caas-body')
    if not article_body:
        print("Failed to find the article body.")
        return "Article content not found."

    article_text = ' '.join(p.get_text() for p in article_body.find_all('p'))
    cleaned_text = re.sub(r'\(Reporting by.*?\)', '', article_text, flags=re.DOTALL).strip()
    return cleaned_text

async def send_summary_to_discord(channel_id, summary, link):
    try:
        print(f"Fetching channel with ID: {channel_id}")
        channel = bot.get_channel(channel_id)

        if channel is not None:
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            message = (
                f"**Summary:**\n{summary}\n"
                f"**Link:**\n{link}\n"
                f"**Extracted on:**\n{timestamp}"
            )
            print(f"Sending message to Discord: {message}")
            await channel.send(message)
        else:
            print(f"Channel with ID {channel_id} not found.")
    except Exception as e:
        print(f"An error occurred while sending message: {e}")

#GUI

class NewsScraperApp:
    def __init__(self, loop):
        self.loop = loop
        self.refreshing = False
        self.sent_summaries = set()
        self.sent_links = set()

        self.window = tk.Tk()
        self.window.title("News Scraper")

        #refresh interval 
        self.refresh_interval_label = tk.Label(self.window, text="Refresh Interval (seconds):")
        self.refresh_interval_label.pack()
        self.refresh_interval_entry = tk.Entry(self.window)
        self.refresh_interval_entry.pack()

        #keywords
        self.keyword_label = tk.Label(self.window, text="Keywords (comma-separated):")
        self.keyword_label.pack()
        self.keyword_text = tk.Text(self.window, height=5, width=50)
        self.keyword_text.pack()

        #prompt
        self.prompt_label = tk.Label(self.window, text="AI Prompt:")
        self.prompt_label.pack()
        self.prompt_text = tk.Text(self.window, height=5, width=50)
        self.prompt_text.pack()

        #timer
        self.countdown_label = tk.Label(self.window, text="Next refresh in: 0 seconds")
        self.countdown_label.pack()

        #buttons
        self.update_interval_button = tk.Button(self.window, text="Update Interval", command=self.update_refresh_interval)
        self.update_interval_button.pack()

        self.update_keywords_button = tk.Button(self.window, text="Update Keywords", command=self.update_keywords)
        self.update_keywords_button.pack()

        self.update_prompt_button = tk.Button(self.window, text="Update Prompt", command=self.update_prompt)
        self.update_prompt_button.pack()

        self.refresh_button = tk.Button(self.window, text="Refresh Now", command=lambda: asyncio.run_coroutine_threadsafe(self.refresh_now(), self.loop))
        self.refresh_button.pack()

        #set defaults
        self.refresh_interval_entry.insert(0, str(refresh_interval))
        self.keyword_text.insert(tk.END, ', '.join(keywords))
        self.prompt_text.insert(tk.END, ai_prompt)

        self.countdown = refresh_interval
        self.update_timer()

    def update_prompt(self):
        global ai_prompt
        ai_prompt = self.prompt_text.get("1.0", tk.END).strip()
        messagebox.showinfo("Prompt Update", "AI prompt has been updated successfully!")

    def update_refresh_interval(self):
        global refresh_interval
        try:
            refresh_interval = int(self.refresh_interval_entry.get())
            self.countdown = refresh_interval
            messagebox.showinfo("Interval Update", f"Refresh interval has been updated to {refresh_interval} seconds.")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid number for the refresh interval.")

    def update_keywords(self):
        global keywords
        keywords = [k.strip() for k in self.keyword_text.get("1.0", tk.END).split(',')]
        save_keywords(keywords)
        messagebox.showinfo("Keywords Update", "Keywords have been updated successfully!")

    def update_timer(self):
        if self.countdown > 0:
            self.countdown -= 1
            self.countdown_label.config(text=f"Next refresh in: {self.countdown} seconds")
        else:
            asyncio.run_coroutine_threadsafe(self.refresh_now(), self.loop)
            self.countdown = refresh_interval

        self.window.after(1000, self.update_timer)

    async def refresh_now(self):
        if self.refreshing:
            print("Refresh already in progress.")  #debug output
            return
        self.refreshing = True  

        channel_id = "channel id"
        tasks = [scrape_yahoo_finance(keyword, channel_id, ai_prompt, self.sent_summaries, self.sent_links) for keyword in keywords]
        await asyncio.gather(*tasks)
        self.refreshing = False

def run_bot():
    loop = asyncio.get_event_loop()
    bot_thread = Thread(target=lambda: loop.run_until_complete(bot.start('bot token')))  #insert bot token
    bot_thread.start()

if __name__ == "__main__":
    refresh_interval = 300
    ai_prompt = "You are a legendary expert of business and investing. Please critically assess this text and summarize the important details in a few sentences and give insights into the event's effects"  #default prompt


    run_bot()

    loop = asyncio.get_event_loop()
    app = NewsScraperApp(loop)
    app.window.mainloop()
