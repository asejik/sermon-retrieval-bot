# Import necessary libraries
import os
import re
import json
import gspread
import json # We need this to read the credentials string
import dateparser
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from thefuzz import fuzz
from flask import Flask # New: Import Flask for the web server
from threading import Thread # New: To run the bot and server together

# --- SETUP AND AUTHENTICATION ---

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

genai.configure(api_key=GEMINI_API_KEY)
llm = genai.GenerativeModel('gemini-1.5-flash')

# --- NEW: FLASK WEB SERVER SETUP ---
# This part will keep the Render Web Service "live"
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram bot is running."

def run_flask():
    # Render provides the PORT environment variable
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- MASTER PROMPT FOR THE LLM ---
MASTER_PROMPT = """
You are a highly intelligent sermon retrieval assistant for Citizens of Light Church. Your goal is to analyze the user's message and return a structured JSON object.

RULES:
1.  **Extract Keywords:** Infer themes from situations, Bible verses, or direct queries.
2.  **Extract Limit:** If the user specifies a number of results (e.g., 'give me 5'), extract that number. Default is 10.
3.  **Extract Date:** If the user specifies a date (e.g., 'October 27, 2024'), extract it and format it as 'DD-MM-YYYY'. If no date is mentioned, the value should be null.
4.  **Handle Pagination:** If the user says "more" or "next", use the topic of their most recent search as the keyword.
5.  **Output Format:** Your entire response MUST BE a single, valid JSON object with three keys: "keywords" (string), "limit" (integer), and "date" (string or null).
---
USER'S SEARCH HISTORY (most recent is last): {history}
---
USER'S CURRENT MESSAGE: "{query}"
---
JSON RESPONSE:
"""

print("Final production bot with web server is starting...")

# --- BOT LOGIC ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['search_history'] = []
    context.user_data['pagination_map'] = {}
    user = update.effective_user
    await update.message.reply_text(f"Hi {user.first_name}! This is the final production version. I can now search by date.")

async def get_instructions_from_llm(query, history_list):
    try:
        history_str = ", ".join(history_list) if history_list else "None"
        prompt = MASTER_PROMPT.format(history=history_str, query=query)
        response = llm.generate_content(prompt)
        json_str = response.text.strip().replace("```json", "").replace("```", "")
        instructions = json.loads(json_str)
        
        instructions['keywords'] = instructions.get('keywords', '').lower()
        instructions['limit'] = int(instructions.get('limit', 10))
        instructions['date'] = instructions.get('date', None)
        return instructions
        
    except Exception as e:
        print(f"Error communicating with LLM: {e}")
        return {'keywords': query.lower(), 'limit': 10, 'date': None}

async def search_sermons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (The entire search_sermons function remains unchanged)
    if 'search_history' not in context.user_data: context.user_data['search_history'] = []
    if 'pagination_map' not in context.user_data: context.user_data['pagination_map'] = {}

    raw_query = update.message.text
    await update.message.reply_text(f'Thinking about "{raw_query}"...')
    
    instructions = await get_instructions_from_llm(raw_query, context.user_data['search_history'])

    if not instructions:
        await update.message.reply_text("Sorry, I'm having trouble thinking right now. Please try again.")
        return

    keywords_str = instructions['keywords']
    limit = instructions['limit']
    search_date_str = instructions['date']

    if keywords_str not in context.user_data['search_history']: context.user_data['search_history'].append(keywords_str)
    if keywords_str not in context.user_data['pagination_map']: context.user_data['pagination_map'][keywords_str] = 0

    try:
        # Read the credentials from the environment variable
        creds_json = json.loads(os.getenv('GSPREAD_CREDENTIALS'))
        gc = gspread.service_account_from_dict(creds_json)
        sh = gc.open("CLC Message Prompter").sheet1
        all_sermons = sh.get_all_records()
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        await update.message.reply_text("Sorry, I'm having trouble connecting to the sermon archive.")
        return

    found_sermons = []
    if search_date_str:
        target_date = dateparser.parse(search_date_str, date_formats=['%d-%m-%Y'])
        if target_date:
            for sermon in all_sermons:
                sermon_date = dateparser.parse(str(sermon.get('Date', '')), settings={'DATE_ORDER': 'DMY'})
                if sermon_date and sermon_date.date() == target_date.date():
                    found_sermons.append({'sermon': sermon, 'score': 100})
    else:
        offset = context.user_data['pagination_map'][keywords_str]
        if offset == 0:
            search_terms = [term.strip() for term in keywords_str.split(',')]
            for sermon in all_sermons:
                search_text = f"{sermon.get('Message Title', '')} {sermon.get('Preacher', '')}".lower()
                total_score = sum(fuzz.partial_ratio(term, search_text) for term in search_terms)
                avg_score = total_score / len(search_terms) if search_terms else 0
                if avg_score > 70:
                    found_sermons.append({'sermon': sermon, 'score': avg_score})
            found_sermons.sort(key=lambda x: x['score'], reverse=True)
            context.user_data[keywords_str + '_results'] = found_sermons
    
    if search_date_str:
        all_found_sermons = found_sermons
        offset = 0
    else:
        all_found_sermons = context.user_data.get(keywords_str + '_results', [])
        offset = context.user_data['pagination_map'][keywords_str]

    results_to_show = all_found_sermons[offset : offset + limit]

    if not results_to_show:
        message = "No more results for this search." if offset > 0 else "Sorry, I couldn't find any sermons matching your search."
        await update.message.reply_text(message)
        return

    response_message = f"Showing results {offset + 1} to {offset + len(results_to_show)} of {len(all_found_sermons)}:\n\n"
    for item in results_to_show:
        sermon = item['sermon']
        response_message += f"📖 <b>Message Title:</b> {sermon['Message Title']}\n🎤 <b>Preacher:</b> {sermon['Preacher']}\n🗓️ <b>Date:</b> {sermon['Date']}\n🔗 <b>Download Link:</b> {sermon['Download Link']}\n\n"
    
    if not search_date_str:
        context.user_data['pagination_map'][keywords_str] += len(results_to_show)
    
    await update.message.reply_html(response_message)

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_sermons))
    application.run_polling()

if __name__ == '__main__':
    # Start the Flask server in a new thread
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    
    # Start the Telegram bot
    main()