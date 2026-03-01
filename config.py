"""Configuration for ThesisAI agent."""

import os
from dotenv import load_dotenv

load_dotenv()

# GitHub Models API (free) — use your GitHub personal access token
# Get a token at https://github.com/settings/tokens
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_MODEL = os.getenv("GITHUB_MODEL", "gpt-4o-mini")
GITHUB_BASE_URL = os.getenv("GITHUB_BASE_URL", "https://models.inference.ai.azure.com")

_IS_VERCEL = os.environ.get("VERCEL", "") == "1"
if _IS_VERCEL:
    MEMORY_FILE = os.path.join("/tmp", "memory.json")
else:
    MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")
# Lower iterations on Vercel to stay within function timeout
MAX_AGENT_ITERATIONS = 5 if _IS_VERCEL else 15
MAX_CONVERSATION_HISTORY = 50
