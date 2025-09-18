# Import necessary libraries
import os
import re
import json
import gspread
import dateparser
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from thefuzz import fuzz

# --- SETUP AND AUTHENTICATION ---

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

genai.configure(api_key=GEMINI_API_KEY)
llm = genai.GenerativeModel('gemini-1.5-flash')

# Final MASTER_PROMPT with current date context
MASTER_PROMPT = """
You are a highly intelligent sermon retrieval assistant for Citizens of Light Church.
Your goal is to analyze the user's message and return a structured JSON object.
The current date is Thursday, September 18, 2025.

RULES:
1.  **Extract Keywords:** Infer themes from situations, Bible verses, or direct queries.
2.  **Extract Limit:** If the user specifies a number of results (e.g., 'give me 5'), extract that number. Default is 10.
3.  **Extract Date:**
    - If the user specifies a date (e.g., 'October 27, 2024', 'last sunday'), calculate and extract it, formatted as 'DD-MM-YYYY'.
    - If the user only specifies a year (e.g., 'messages from 2022'), extract the year as a four-digit string 'YYYY'.
    - If no date is mentioned, the value should be null.
4.  **Handle Pagination:** If the user says "more" or "next", use the topic of their most recent search as the keyword.
5.  **Output Format:** Your entire response MUST BE a single, valid JSON object with three keys: "keywords" (string), "limit" (integer), and "date" (string or null).

---
USER'S SEARCH HISTORY (most recent is last):
{history}
---
USER'S CURRENT MESSAGE:
"{query}"
---
JSON RESPONSE:
"""

print("Bot with Debug Mode is starting...")

# --- BOT LOGIC ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['search_history'] = []
    context.user_data['pagination_map'] = {}
    user = update.effective_user
    welcome_message = (
        f"Hi {user.first_name}! You can search for messages of Citizens of Light Church through this bot. "
        "Just send me a message with your request, like 'sermons on faith' or 'messages from last Sunday'."
    )
    await update.message.reply_text(welcome_message)

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
        creds_json = json.loads(os.getenv('GSPREAD_CREDENTIALS'))
        gc = gspread.service_account_from_dict(creds_json)
        sh = gc.open("CLC Message Prompter").sheet1
        all_sermons = sh.get_all_records()
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        await update.message.reply_text("Sorry, I'm having trouble connecting to the sermon archive.")
        return

    found_sermons = []
    # --- ADDED DEBUG VARIABLE ---
    highest_score_found = 0

    if search_date_str:
        # (Date logic is unchanged)
        if len(search_date_str) == 10:
            target_date = dateparser.parse(search_date_str, date_formats=['%d-%m-%Y'])
            if target_date:
                for sermon in all_sermons:
                    sermon_date = dateparser.parse(str(sermon.get('Date', '')), settings={'DATE_ORDER': 'DMY'})
                    if sermon_date and sermon_date.date() == target_date.date():
                        found_sermons.append({'sermon': sermon, 'score': 100})
        elif len(search_date_str) == 4 and search_date_str.isdigit():
            target_year = int(search_date_str)
            for sermon in all_sermons:
                sermon_date = dateparser.parse(str(sermon.get('Date', '')), settings={'DATE_ORDER': 'DMY'})
                if sermon_date and sermon_date.year == target_year:
                    found_sermons.append({'sermon': sermon, 'score': 100})
    else:
        offset = context.user_data['pagination_map'][keywords_str]
        if offset == 0:
            search_terms = [term.strip() for term in keywords_str.split(',')]
            for sermon in all_sermons:
                search_text = f"{sermon.get('Message Title', '')} {sermon.get('Preacher', '')}".lower()
                total_score = sum(fuzz.token_set_ratio(term, search_text) for term in search_terms)
                avg_score = total_score / len(search_terms) if search_terms else 0
                
                if avg_score > highest_score_found:
                    highest_score_found = avg_score # Track the best score we see

                if avg_score > 70:
                    found_sermons.append({'sermon': sermon, 'score': avg_score})
            found_sermons.sort(key=lambda x: x['score'], reverse=True)
            context.user_data[keywords_str + '_results'] = found_sermons
            context.user_data[keywords_str + '_highest_score'] = highest_score_found
    
    if search_date_str:
        all_found_sermons = found_sermons
        offset = 0
    else:
        all_found_sermons = context.user_data.get(keywords_str + '_results', [])
        offset = context.user_data['pagination_map'][keywords_str]

    results_to_show = all_found_sermons[offset : offset + limit]

    if not results_to_show:
        if offset == 0:
            # --- OUR NEW DEBUG REPLY ---
            highest_score = context.user_data.get(keywords_str + '_highest_score', 0)
            debug_message = (
                f"I couldn't find a confident match. Here's my thinking process:\n\n"
                f"🧠 **AI Brain Keywords:** `{keywords_str}`\n"
                f"📈 **Highest Match Score Found:** `{highest_score:.0f}%`\n"
                f"🎯 **Confidence Threshold:** `70%`"
            )
            await update.message.reply_html(debug_message)
        else:
            await update.message.reply_text("No more results for this search.")
        return

    response_message = f"Showing results {offset + 1} to {offset + len(results_to_show)} of {len(all_found_sermons)}:\n\n"
    for item in results_to_show:
        sermon = item['sermon']
        response_message += f"📖 <b>Message Title:</b> {sermon['Message Title']}\n🎤 <b>Preacher:</b> {sermon['Preacher']}\n🗓️ <b>Date:</b> {sermon['Date']}\n🔗 <b>Download Link:</b> {sermon['Download Link']}\n\n"
    
    if not search_date_str:
        context.user_data['pagination_map'][keywords_str] += len(results_to_show)
    
    await update.message.reply_html(response_message)

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_sermons))
    application.run_polling()

if __name__ == '__main__':
    main()