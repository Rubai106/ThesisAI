# ThesisAI — Autonomous Research Assistant

An AI-powered agent that helps computer science undergraduates with their thesis work: research discovery, literature review, experiment design, coding, writing, and viva preparation.

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API key

```bash
copy .env.example .env
```

Edit `.env` and paste your OpenAI API key:

```
OPENAI_API_KEY=sk-your-key-here
```

### 3. Run

```bash
python main.py
```

## Features

| Capability               | Description                                                        |
| ------------------------ | ------------------------------------------------------------------ |
| Research Discovery       | Search for papers, identify trends, methods, datasets, and gaps    |
| Literature Review        | Extract & summarize problem, method, dataset, metrics, results     |
| Research Gap Analysis    | Cross-paper analysis, underexplored areas, novel experiment ideas  |
| Experiment Design        | Pipelines, baselines, metrics, datasets, risk assessment           |
| Coding Assistance        | Clean modular code, algorithm explanation, optimization, debugging |
| Writing Assistance       | Academic tone conversion, clarity, structure, citation placement    |
| Viva Preparation         | Defense questions, examiner simulation, argument strengthening     |
| Persistent Memory        | Remembers your topic, area, methodology, and discussed papers      |

## CLI Commands

| Command               | Action                                  |
| --------------------- | --------------------------------------- |
| `/help`               | Show available commands                 |
| `/topic <topic>`      | Set your thesis topic                   |
| `/area <area>`        | Set your research area                  |
| `/method <method>`    | Set your chosen methodology             |
| `/memory`             | View stored memory context              |
| `/reset`              | Clear conversation (memory persists)    |
| `/quit`               | Exit                                    |

## Project Structure

```
Agent/
├── main.py              # CLI entry point
├── config.py            # Settings & env loading
├── requirements.txt     # Python dependencies
├── .env.example         # API key template
├── memory.json          # Auto-generated persistent memory
├── readme.text          # Original spec
├── README.md            # This file
└── agent/
    ├── __init__.py
    ├── thesis_ai.py     # Core agent loop with OpenAI function calling
    ├── prompts.py       # System prompt construction
    ├── memory.py        # JSON-file-backed memory manager
    └── tools.py         # Tool schemas & implementations
```

## How It Works

1. **System prompt** is constructed from the spec rules + injected memory context.
2. **User message** is appended to the conversation history.
3. The **OpenAI API** processes the conversation with tool schemas available.
4. If the model calls a tool (e.g. `web_search`), the tool is executed locally and the result is fed back.
5. The **agent loop** repeats until the model produces a final text response (up to 15 iterations).
6. Important context (topic, papers, decisions) is saved to **persistent memory** across sessions.
