# Citizens of Light Church - Sermon Retrieval Telegram Bot

A sophisticated, AI-powered Telegram bot designed to help church members easily find and access the complete sermon archive of Citizens of Light Church, stored in a Google Sheet.

This bot understands natural language, allowing users to search by topic, preacher, date, or even by describing a situation or feeling.

## Key Features ✨

* **Natural Language Understanding:** Powered by the Google Gemini LLM, the bot can understand complex queries, typos, and contextual requests (e.g., "I'm feeling sad").
* **Thematic Search:** Recommends sermons on themes like "hope," "faith," or "provision" based on the user's situation.
* **Precise Date Search:** Users can ask for sermons preached on a specific date (e.g., "messages from June 11, 2023").
* **Dynamic Results:** Users can ask for a specific number of results (e.g., "give me 3 messages on favour"). Defaults to 10.
* **Intelligent Pagination:** The bot remembers the user's search history for multiple topics, allowing them to ask for "more" and get the next set of results for each topic.
* **Secure and Live 24/7:** Deployed on Render, the bot runs continuously and handles all secret API keys securely using environment variables.

## Technologies Used 🛠️

* **Language:** Python
* **AI Brain:** Google Gemini API (`gemini-1.5-flash`)
* **Telegram Bot Framework:** `python-telegram-bot`
* **Data Source:** Google Sheets API (`gspread`)
* **Fuzzy Matching:** `thefuzz`
* **Date Parsing:** `dateparser`
* **Deployment:** Render
* **Version Control:** Git & GitHub

## Setup and Installation

To run this project locally, follow these steps:

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/](https://github.com/)[Your-GitHub-Username]/sermon-retrieval-bot.git
    cd sermon-retrieval-bot
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Set up credentials:**
    * **Google Sheets:** Follow the `gspread` documentation to get a `credentials.json` file and enable the Google Sheets & Drive APIs. Share your Google Sheet with the `client_email` from the credentials file.
    * **API Keys:** Get API keys for Telegram (from BotFather) and Google Gemini (from AI Studio).

4.  **Create a `.env` file** in the root directory and add your secret keys:
    ```
    TELEGRAM_TOKEN=your_telegram_token
    GEMINI_API_KEY=your_gemini_api_key
    ```

5.  **Run the bot:**
    ```bash
    python bot.py
    ```
