# ThesisAI

AI-powered autonomous research assistant for thesis and academic writing.

**Live Demo:** [https://thesisai-one-lake.vercel.app](https://thesisai-one-lake.vercel.app)

## Features

- **Web Search** — Search for academic papers, datasets, and documentation across arXiv, Google Scholar, IEEE, ACM
- **Paper Analysis** — Analyze and compare research papers side-by-side
- **Thesis Outline Generation** — Auto-generate structured thesis outlines
- **Chapter Drafting** — Write full chapter drafts with proper academic tone
- **Abstract Generation** — Generate concise, publication-ready abstracts
- **Writing Improvement** — Refine academic writing for clarity and style
- **Paraphrasing** — Rephrase text while preserving meaning
- **Citation Generation** — Generate formatted citations (APA, IEEE, etc.)
- **Experiment Design** — Suggest experiment methodologies for your research
- **Code Generation** — Generate research-related code snippets
- **Viva Preparation** — Generate potential viva/defense questions
- **Research Timeline** — Plan and schedule your research milestones
- **PDF Upload & Parsing** — Upload PDFs and extract text for analysis
- **Export** — Export to Word (.docx), LaTeX (.tex), Markdown, and bibliography files
- **Conversation Memory** — Persistent memory across sessions
- **Multi-Conversation Support** — Manage multiple research threads
- **Per-User API Keys** — Each user brings their own API key (no shared quota)
- **Multi-Provider Support** — GitHub Models, OpenAI, Groq, OpenRouter, Together AI, Ollama
- **Web UI** — Clean, dark-themed browser interface via Flask

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/Rubai106/ThesisAI.git
cd ThesisAI
pip install -r requirements.txt
```

### 2. Configure API Key

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and add your API key:

```env
# Option A: GitHub Models (free, limited)
# Get a token at https://github.com/settings/tokens
GITHUB_TOKEN=ghp_your-token-here
GITHUB_MODEL=gpt-4o-mini
GITHUB_BASE_URL=https://models.inference.ai.azure.com

# Option B: OpenAI
# GITHUB_TOKEN=sk-your-openai-key
# GITHUB_MODEL=gpt-4o-mini
# GITHUB_BASE_URL=https://api.openai.com/v1

# Option C: Groq (free, generous limits)
# GITHUB_TOKEN=gsk_your-groq-key
# GITHUB_MODEL=llama-3.3-70b-versatile
# GITHUB_BASE_URL=https://api.groq.com/openai/v1
```

### 3. Run

```bash
python app.py
```

Open **http://localhost:5000** in your browser.

### CLI Mode (optional)

```bash
python main.py
```

## Per-User API Keys

Each user can set their **own API key** via the **Settings** button in the UI. This means:

- **No shared quota** — each user's API usage is independent
- **No overlap** — one user hitting their limit doesn't affect others
- Keys are stored per-user on the server and never shared

### Supported Providers

| Provider | Free Tier | How to Get a Key |
|---|---|---|
| **GitHub Models** | Yes (limited) | [github.com/settings/tokens](https://github.com/settings/tokens) |
| **OpenAI** | No (paid) | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| **Groq** | Yes (generous) | [console.groq.com/keys](https://console.groq.com/keys) |
| **OpenRouter** | Pay-per-use | [openrouter.ai/keys](https://openrouter.ai/keys) |
| **Together AI** | Free credits | [api.together.xyz/settings/api-keys](https://api.together.xyz/settings/api-keys) |
| **Ollama** | Unlimited (local) | [ollama.com/download](https://ollama.com/download) |

## Slash Commands

| Command | Description |
|---|---|
| `/help` | Show all available commands |
| `/topic <topic>` | Set your thesis topic |
| `/area <area>` | Set research area |
| `/method <method>` | Set methodology |
| `/outline` | Generate a full thesis outline |
| `/write <chapter>` | Draft a thesis chapter |
| `/abstract` | Generate a thesis abstract |
| `/references` | Generate bibliography (APA/IEEE/Harvard) |
| `/timeline` | Create a research timeline |
| `/paraphrase <text>` | Paraphrase text in academic style |
| `/viva` | Generate viva/defense questions |
| `/progress` | View thesis completion dashboard |
| `/reset` | Clear conversation (memory persists) |
| `/memory` | View stored thesis context |

## Tech Stack

- **Backend:** Python, Flask, OpenAI SDK
- **Frontend:** Vanilla HTML/CSS/JS
- **AI:** OpenAI-compatible API (GitHub Models, OpenAI, Groq, etc.)
- **Hosting:** Vercel (serverless)
