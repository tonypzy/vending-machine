import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the API key from the environment
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY")

if not CHATGPT_API_KEY:
    raise ValueError("CHATGPT_API_KEY is not set. Please configure it in your environment.")

# Use CHATGPT_API_KEY securely in your code