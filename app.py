"""ThesisAI — Web interface (Flask)

Run:  python app.py
Then open http://localhost:5000 in your browser.
"""

import json
import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file
import config
from agent.thesis_ai import ThesisAI
from agent.export import (
    extract_pdf_text,
    save_draft_markdown,
    export_to_word,
    export_to_latex,
    export_conversation,
    generate_bibliography_file,
)

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB upload limit

# Per-user agent instances and last responses
_agents: dict[str, ThesisAI] = {}
_last_responses: dict[str, str] = {}

# ── User ID helper ───────────────────────────────────────────────

import re as _re

def _get_user_id() -> str:
    """Extract a sanitised user ID from the X-User-ID header."""
    uid = request.headers.get("X-User-ID", "default")
    # Sanitise: allow only alphanumeric and hyphens
    uid = _re.sub(r"[^a-zA-Z0-9\-]", "", uid)[:64]
    return uid or "default"

# ── Conversations Persistence ────────────────────────────────────

# On Vercel, use /tmp since the main filesystem is read-only
_IS_VERCEL = os.environ.get("VERCEL", "") == "1"
_BASE_DATA_DIR = "/tmp" if _IS_VERCEL else os.path.dirname(__file__)


def _user_conversations_dir(user_id: str) -> str:
    """Return (and create) a per-user conversations directory."""
    d = os.path.join(_BASE_DATA_DIR, "user_data", user_id, "conversations")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _user_drafts_dir(user_id: str) -> str:
    """Return (and create) a per-user drafts directory."""
    d = os.path.join(_BASE_DATA_DIR, "user_data", user_id, "drafts")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _user_memory_file(user_id: str) -> str:
    """Return the memory JSON path for a given user."""
    d = os.path.join(_BASE_DATA_DIR, "user_data", user_id)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return os.path.join(d, "memory.json")


def _conv_path(user_id: str, conv_id: str) -> str:
    """Return the file path for a conversation."""
    return os.path.join(_user_conversations_dir(user_id), f"{conv_id}.json")


def _load_conversation(user_id: str, conv_id: str) -> dict | None:
    """Load a single conversation by ID."""
    path = _conv_path(user_id, conv_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def _save_conversation(user_id: str, conv: dict) -> None:
    """Save a conversation to disk."""
    try:
        with open(_conv_path(user_id, conv["id"]), "w", encoding="utf-8") as f:
            json.dump(conv, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


def _create_conversation(user_id: str, title: str = "New Chat") -> dict:
    """Create a new conversation and return it."""
    conv = {
        "id": uuid.uuid4().hex[:12],
        "title": title,
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "messages": [],
    }
    _save_conversation(user_id, conv)
    return conv


def _list_conversations(user_id: str) -> list[dict]:
    """List all conversations sorted by last update (newest first)."""
    convs = []
    conv_dir = _user_conversations_dir(user_id)
    for fname in os.listdir(conv_dir):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(conv_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            convs.append({
                "id": data["id"],
                "title": data.get("title", "Untitled"),
                "created": data.get("created", ""),
                "updated": data.get("updated", ""),
                "message_count": len(data.get("messages", [])),
            })
        except (json.JSONDecodeError, IOError, KeyError):
            continue
    convs.sort(key=lambda c: c.get("updated", ""), reverse=True)
    return convs


def _append_chat(user_id: str, conv_id: str, user_msg: str, ai_msg: str) -> None:
    """Append a user/AI message pair to a conversation."""
    conv = _load_conversation(user_id, conv_id)
    if conv is None:
        conv = _create_conversation(user_id)
        conv["id"] = conv_id  # keep requested ID
    conv["messages"].append({"role": "user", "content": user_msg})
    conv["messages"].append({"role": "ai", "content": ai_msg})
    # Auto-title from first user message
    if conv["title"] == "New Chat" and user_msg and not user_msg.startswith("/"):
        conv["title"] = user_msg[:60] + ("..." if len(user_msg) > 60 else "")
    conv["updated"] = datetime.now().isoformat()
    _save_conversation(user_id, conv)


def get_agent(user_id: str) -> ThesisAI:
    """Return (or create) a per-user agent instance."""
    if user_id not in _agents:
        mem_file = _user_memory_file(user_id)
        _agents[user_id] = ThesisAI(memory_file=mem_file)
    return _agents[user_id]


# ── Routes ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    uid = _get_user_id()
    data = request.get_json(force=True)
    user_message = data.get("message", "").strip()
    conv_id = data.get("conversation_id", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400
    if not conv_id:
        return jsonify({"error": "No conversation_id"}), 400

    ai = get_agent(uid)

    # Handle slash commands server-side
    if user_message.startswith("/"):
        result = _handle_command(user_message, ai, uid)
        if result is not None:
            _last_responses[uid] = result
            _append_chat(uid, conv_id, user_message, result)
            return jsonify({"response": result})
        # result is None → route /outline, /write, and other commands through the AI agent
        parts = user_message.strip().split(maxsplit=1)
        keyword = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        topic = ai.memory.data.get("thesis_topic", "")
        methodology = ai.memory.data.get("methodology", "")
        deadline = ai.memory.data.get("deadline", "")

        if keyword == "/outline":
            ai_prompt = (
                f"Generate a detailed thesis outline for the topic: "
                f"\"{arg or topic}\". Include chapter numbers, titles, "
                f"section headings, and a brief description of what each "
                f"section should cover. Make it comprehensive and structured."
            )
        elif keyword == "/write":
            ai_prompt = (
                f"Write a detailed first draft for the thesis chapter: "
                f"\"{arg}\" for the thesis topic: \"{topic}\". "
                f"Write in academic style with proper structure, subsections, "
                f"placeholder citations like [AuthorYear], and logical flow. "
                f"Aim for roughly 1500-2000 words. Make it publication-ready."
            )
        elif keyword == "/abstract":
            ai_prompt = (
                f"Generate a thesis abstract for the topic: \"{arg or topic}\". "
                f"Methodology: \"{methodology or 'not specified'}\". "
                f"The abstract should be 150-300 words, structured with: "
                f"background/context, problem statement, methodology, "
                f"key findings/expected results, and significance. "
                f"Write in formal academic style."
            )
        elif keyword in ("/references", "/bibliography"):
            papers = ai.memory.data.get("discussed_papers", [])
            style = arg.strip().lower() if arg else "apa"
            if style not in ("apa", "ieee", "harvard"):
                style = "apa"
            papers_info = "; ".join(p.get("title", "") for p in papers[-20:])
            ai_prompt = (
                f"Generate a formatted bibliography/references section in "
                f"{style.upper()} citation style for these papers: {papers_info}. "
                f"If exact details are unknown, provide the best approximation "
                f"with placeholder fields marked as [?]. Format each reference "
                f"properly according to {style.upper()} guidelines."
            )
        elif keyword in ("/timeline", "/schedule"):
            ai_prompt = (
                f"Generate a detailed research timeline/schedule for the thesis "
                f"topic: \"{topic}\". Deadline: \"{arg or deadline}\". "
                f"Include phases: literature review, methodology design, "
                f"data collection, implementation, experimentation, "
                f"writing, revision, and submission. Include specific "
                f"milestones, deliverables, and time allocations for each phase. "
                f"Present as a structured schedule with dates."
            )
        elif keyword == "/paraphrase":
            ai_prompt = (
                f"Paraphrase the following text in academic style. "
                f"Preserve the meaning but restructure sentences, change "
                f"vocabulary, and ensure it's plagiarism-safe. Provide the "
                f"paraphrased version followed by a brief note on what was "
                f"changed:\\n\\n{arg}"
            )
        elif keyword in ("/viva", "/defense"):
            ai_prompt = (
                f"Generate 10-15 likely thesis defense/viva questions for "
                f"the topic: \"{topic}\". Methodology: \"{methodology or 'not specified'}\". "
                f"For each question, provide:\\n"
                f"1. The question itself\\n"
                f"2. Why the examiner might ask it\\n"
                f"3. A suggested strong answer strategy\\n\\n"
                f"Cover: motivation, methodology, results, limitations, "
                f"future work, and theoretical foundations."
            )
        else:
            ai_prompt = user_message

        drafts_dir = _user_drafts_dir(uid)
        try:
            response = ai.chat(ai_prompt)
            _last_responses[uid] = response
            _append_chat(uid, conv_id, user_message, response)

            # Auto-save chapter drafts and other generated content
            if keyword == "/write" and response:
                try:
                    safe_name = arg.replace(" ", "_").lower()
                    save_draft_markdown(response, f"{safe_name}.md", drafts_dir=drafts_dir)
                except Exception:
                    pass
            elif keyword == "/abstract" and response:
                try:
                    save_draft_markdown(response, "abstract.md", drafts_dir=drafts_dir)
                except Exception:
                    pass
            elif keyword in ("/references", "/bibliography") and response:
                try:
                    save_draft_markdown(response, "references.md", drafts_dir=drafts_dir)
                except Exception:
                    pass
            elif keyword in ("/timeline", "/schedule") and response:
                try:
                    save_draft_markdown(response, "research_timeline.md", drafts_dir=drafts_dir)
                except Exception:
                    pass
            elif keyword in ("/viva", "/defense") and response:
                try:
                    save_draft_markdown(response, "viva_questions.md", drafts_dir=drafts_dir)
                except Exception:
                    pass

            return jsonify({"response": response})
        except Exception as exc:
            return jsonify({"error": f"Error: {exc}"}), 500

    try:
        response = ai.chat(user_message)
        _last_responses[uid] = response
        _append_chat(uid, conv_id, user_message, response)
        return jsonify({"response": response})
    except Exception as exc:
        err = str(exc)
        if "insufficient_quota" in err or "429" in err:
            return jsonify({"error": "API quota exceeded. Check your GitHub token permissions."}), 429
        return jsonify({"error": f"Error: {err}"}), 500


# ── PDF Upload ───────────────────────────────────────────────────

@app.route("/api/upload-pdf", methods=["POST"])
def upload_pdf():
    uid = _get_user_id()
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    conv_id = request.form.get("conversation_id", "").strip()
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Please upload a PDF file"}), 400

    ai = get_agent(uid)

    # Save temporarily
    upload_dir = os.path.join(_BASE_DATA_DIR, "user_data", uid, "uploads")
    try:
        os.makedirs(upload_dir, exist_ok=True)
    except OSError:
        pass
    filepath = os.path.join(upload_dir, file.filename)
    file.save(filepath)

    try:
        # Extract text
        text = extract_pdf_text(filepath)
        if not text.strip():
            return jsonify({"error": "Could not extract text from this PDF."}), 400

        # Send to AI for analysis
        prompt = (
            f"I've uploaded a research paper titled \"{file.filename}\". "
            f"Here is the extracted text:\n\n---\n{text}\n---\n\n"
            f"Please analyze this paper and provide:\n"
            f"1. **Problem Statement** — what problem does it address?\n"
            f"2. **Methodology** — what approach/method is used?\n"
            f"3. **Dataset** — what data is used?\n"
            f"4. **Key Results** — main findings\n"
            f"5. **Limitations** — weaknesses or gaps\n"
            f"6. **Relevance** — how it might relate to my thesis\n"
            f"7. **Brief Summary** (3-4 sentences)"
        )
        response = ai.chat(prompt)
        _last_responses[uid] = response
        if conv_id:
            _append_chat(uid, conv_id, f"\ud83d\udcc4 Uploaded: {file.filename}", response)
        return jsonify({"response": response})
    except Exception as exc:
        return jsonify({"error": f"Failed to process PDF: {exc}"}), 500
    finally:
        # Clean up temp file
        try:
            os.remove(filepath)
        except OSError:
            pass


# ── Export Endpoints ─────────────────────────────────────────────

@app.route("/api/export/word", methods=["POST"])
def export_word():
    uid = _get_user_id()
    data = request.get_json(force=True)
    content = data.get("content", "") or _last_responses.get(uid, "")
    title = data.get("title", "Thesis Draft")

    if not content:
        return jsonify({"error": "No content to export"}), 400

    try:
        filepath = export_to_word(content, title=title)
        return send_file(filepath, as_attachment=True,
                         download_name=os.path.basename(filepath))
    except Exception as exc:
        return jsonify({"error": f"Export failed: {exc}"}), 500


@app.route("/api/export/latex", methods=["POST"])
def export_latex():
    uid = _get_user_id()
    data = request.get_json(force=True)
    content = data.get("content", "") or _last_responses.get(uid, "")
    title = data.get("title", "Thesis Draft")
    author = data.get("author", "Student Name")

    if not content:
        return jsonify({"error": "No content to export"}), 400

    try:
        filepath = export_to_latex(content, title=title, author=author)
        return send_file(filepath, as_attachment=True,
                         download_name=os.path.basename(filepath))
    except Exception as exc:
        return jsonify({"error": f"Export failed: {exc}"}), 500


@app.route("/api/export/markdown", methods=["POST"])
def export_markdown():
    uid = _get_user_id()
    data = request.get_json(force=True)
    content = data.get("content", "") or _last_responses.get(uid, "")
    filename = data.get("filename", "")

    if not content:
        return jsonify({"error": "No content to export"}), 400

    try:
        drafts_dir = _user_drafts_dir(uid)
        filepath = save_draft_markdown(content, filename, drafts_dir=drafts_dir)
        return send_file(filepath, as_attachment=True,
                         download_name=os.path.basename(filepath))
    except Exception as exc:
        return jsonify({"error": f"Export failed: {exc}"}), 500


@app.route("/api/drafts", methods=["GET"])
def list_drafts():
    """List all saved drafts with metadata."""
    uid = _get_user_id()
    drafts_dir = _user_drafts_dir(uid)
    files = []
    for f in sorted(os.listdir(drafts_dir)):
        path = os.path.join(drafts_dir, f)
        if os.path.isfile(path):
            stat = os.stat(path)
            files.append({
                "name": f,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return jsonify({"drafts": files})


@app.route("/api/drafts/<filename>", methods=["GET"])
def download_draft(filename):
    """Download a saved draft."""
    uid = _get_user_id()
    drafts_dir = _user_drafts_dir(uid)
    return send_from_directory(drafts_dir, filename, as_attachment=True)


@app.route("/api/drafts/<filename>/preview", methods=["GET"])
def preview_draft(filename):
    """Return the text content of a draft for in-browser preview."""
    uid = _get_user_id()
    drafts_dir = _user_drafts_dir(uid)
    filepath = os.path.join(drafts_dir, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "File not found"}), 404
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"name": filename, "content": content})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/drafts/<filename>", methods=["DELETE"])
def delete_draft(filename):
    """Delete a saved draft."""
    uid = _get_user_id()
    drafts_dir = _user_drafts_dir(uid)
    filepath = os.path.join(drafts_dir, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "File not found"}), 404
    try:
        os.remove(filepath)
        return jsonify({"status": "ok"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/drafts/<filename>/rename", methods=["POST"])
def rename_draft(filename):
    """Rename a saved draft."""
    uid = _get_user_id()
    drafts_dir = _user_drafts_dir(uid)
    data = request.get_json(force=True)
    new_name = data.get("name", "").strip()
    if not new_name:
        return jsonify({"error": "New name required"}), 400
    old_path = os.path.join(drafts_dir, filename)
    new_path = os.path.join(drafts_dir, new_name)
    if not os.path.isfile(old_path):
        return jsonify({"error": "File not found"}), 404
    if os.path.exists(new_path):
        return jsonify({"error": "A file with that name already exists"}), 409
    try:
        os.rename(old_path, new_path)
        return jsonify({"status": "ok", "name": new_name})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Memory & Reset ───────────────────────────────────────────────

@app.route("/api/memory", methods=["GET"])
def memory():
    uid = _get_user_id()
    ai = get_agent(uid)
    return jsonify({"memory": ai.memory.render_context()})


@app.route("/api/memory/full", methods=["GET"])
def memory_full():
    """Return full structured memory data for the UI panel."""
    uid = _get_user_id()
    ai = get_agent(uid)
    return jsonify(ai.memory.get_full_data())


@app.route("/api/memory/field", methods=["PUT"])
def memory_update_field():
    """Update a single memory field."""
    uid = _get_user_id()
    ai = get_agent(uid)
    data = request.get_json(force=True)
    field = data.get("field", "")
    value = data.get("value", "")
    if not field:
        return jsonify({"error": "Field name required"}), 400
    ai.memory.set_field(field, value)
    ai._rebuild_system_message()
    return jsonify({"status": "ok"})


@app.route("/api/memory/field", methods=["DELETE"])
def memory_clear_field():
    """Clear a memory field."""
    uid = _get_user_id()
    ai = get_agent(uid)
    data = request.get_json(force=True)
    field = data.get("field", "")
    if not field:
        return jsonify({"error": "Field name required"}), 400
    ai.memory.clear_field(field)
    ai._rebuild_system_message()
    return jsonify({"status": "ok"})


@app.route("/api/memory/item", methods=["DELETE"])
def memory_delete_item():
    """Delete a specific item from a list field by index."""
    uid = _get_user_id()
    ai = get_agent(uid)
    data = request.get_json(force=True)
    list_name = data.get("list", "")
    index = data.get("index", -1)
    if not list_name or index < 0:
        return jsonify({"error": "List name and valid index required"}), 400
    ok = ai.memory.remove_item(list_name, index)
    if ok:
        ai._rebuild_system_message()
        return jsonify({"status": "ok"})
    return jsonify({"error": "Item not found"}), 404


@app.route("/api/memory/add", methods=["POST"])
def memory_add_item():
    """Add an item to a list field (notes, decisions, progress)."""
    uid = _get_user_id()
    ai = get_agent(uid)
    data = request.get_json(force=True)
    list_name = data.get("list", "")
    value = data.get("value", "").strip()
    if not list_name or not value:
        return jsonify({"error": "List name and value required"}), 400
    if list_name == "custom_notes":
        ai.memory.add_note(value)
    elif list_name == "key_decisions":
        ai.memory.add_decision(value)
    elif list_name == "progress_log":
        ai.memory.add_progress(value)
    elif list_name == "discussed_papers":
        ai.memory.add_paper(value)
    else:
        return jsonify({"error": f"Unknown list: {list_name}"}), 400
    ai._rebuild_system_message()
    return jsonify({"status": "ok"})


@app.route("/api/reset", methods=["POST"])
def reset():
    uid = _get_user_id()
    ai = get_agent(uid)
    ai.reset()
    return jsonify({"status": "ok", "message": "Conversation cleared. Memory retained."})


# ── Conversations CRUD ───────────────────────────────────────────

@app.route("/api/conversations", methods=["GET"])
def list_convs():
    """Return all conversations (id, title, created, updated, message_count)."""
    uid = _get_user_id()
    return jsonify({"conversations": _list_conversations(uid)})


@app.route("/api/conversations", methods=["POST"])
def create_conv():
    """Create a new conversation and return it."""
    uid = _get_user_id()
    data = request.get_json(force=True) if request.data else {}
    title = data.get("title", "New Chat")
    conv = _create_conversation(uid, title)
    return jsonify(conv)


@app.route("/api/conversations/<conv_id>", methods=["GET"])
def get_conv(conv_id):
    """Return full conversation with messages."""
    uid = _get_user_id()
    conv = _load_conversation(uid, conv_id)
    if conv is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(conv)


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
def delete_conv(conv_id):
    """Delete a conversation."""
    uid = _get_user_id()
    path = _conv_path(uid, conv_id)
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    try:
        os.remove(path)
        return jsonify({"status": "ok"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/conversations/<conv_id>/rename", methods=["POST"])
def rename_conv(conv_id):
    """Rename a conversation."""
    uid = _get_user_id()
    data = request.get_json(force=True)
    new_title = data.get("title", "").strip()
    if not new_title:
        return jsonify({"error": "Title required"}), 400
    conv = _load_conversation(uid, conv_id)
    if conv is None:
        return jsonify({"error": "Not found"}), 404
    conv["title"] = new_title
    _save_conversation(uid, conv)
    return jsonify({"status": "ok"})


@app.route("/api/history", methods=["GET"])
def get_history():
    """Legacy endpoint — returns empty for backwards compat."""
    return jsonify({"history": []})


# ── Command Handler ──────────────────────────────────────────────

def _handle_command(cmd: str, ai: ThesisAI, user_id: str = "") -> str:
    parts = cmd.strip().split(maxsplit=1)
    keyword = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if keyword == "/help":
        return (
            "**Commands:**\n"
            "- `/topic <topic>` — Set thesis topic\n"
            "- `/area <area>` — Set research area\n"
            "- `/method <method>` — Set methodology\n"
            "- `/outline` — Generate a full thesis outline\n"
            "- `/write <chapter>` — Draft a chapter (e.g. `/write Literature Review`)\n"
            "- `/abstract` — Generate a thesis abstract\n"
            "- `/references [style]` — Generate bibliography (apa/ieee/harvard)\n"
            "- `/timeline` — Generate a research timeline\n"
            "- `/paraphrase` — Paraphrase your last message or pasted text\n"
            "- `/viva` — Generate viva/defense practice questions\n"
            "- `/progress` — View your research progress dashboard\n"
            "- `/memory` — View stored context\n"
            "- `/reset` — Clear conversation (memory persists)\n"
            "- `/help` — Show this help\n\n"
            "**Other features:**\n"
            "- **Upload PDF** — Click 📎 to upload and analyze a research paper\n"
            "- **Multi-PDF** — Upload several PDFs at once for batch analysis\n"
            "- **Export** — Click ⬇ on any AI response to download as Word, LaTeX, or Markdown\n"
            "- **Export Conversation** — Download the full conversation as a document\n"
            "- **Drafts auto-save** — Chapter drafts from `/write` are saved to the `drafts/` folder"
        )
    if keyword == "/memory":
        return f"**Memory:**\n\n{ai.memory.render_context()}"
    if keyword == "/reset":
        ai.reset()
        return "Conversation cleared. Memory retained."
    if keyword == "/topic":
        if not arg:
            return "Usage: `/topic <your thesis topic>`"
        ai.memory.set_thesis_topic(arg)
        return f"Thesis topic set to: **{arg}**"
    if keyword == "/area":
        if not arg:
            return "Usage: `/area <research area>`"
        ai.memory.set_research_area(arg)
        return f"Research area set to: **{arg}**"
    if keyword == "/method":
        if not arg:
            return "Usage: `/method <methodology>`"
        ai.memory.set_methodology(arg)
        return f"Methodology set to: **{arg}**"

    # /outline and /write are routed through the AI agent for rich responses
    if keyword == "/outline":
        topic = ai.memory.data.get("thesis_topic", "")
        if not topic and not arg:
            return "Set your topic first with `/topic <topic>`, or use `/outline <topic>`."
        return None  # signal to route through AI

    if keyword == "/write":
        topic = ai.memory.data.get("thesis_topic", "")
        if not topic:
            return "Set your topic first with `/topic <topic>`."
        if not arg:
            return (
                "Usage: `/write <chapter name>`\n\n"
                "Examples:\n"
                "- `/write Introduction`\n"
                "- `/write Literature Review`\n"
                "- `/write Methodology`\n"
                "- `/write Results and Discussion`\n"
                "- `/write Conclusion`"
            )
        return None  # signal to route through AI

    if keyword == "/abstract":
        topic = ai.memory.data.get("thesis_topic", "")
        if not topic and not arg:
            return "Set your topic first with `/topic <topic>`, or use `/abstract <topic>`."
        return None  # route through AI

    if keyword == "/references" or keyword == "/bibliography":
        papers = ai.memory.data.get("discussed_papers", [])
        if not papers and not arg:
            return (
                "No papers in memory yet. Discuss some papers first, or use:\n"
                "- `/references apa` — APA style\n"
                "- `/references ieee` — IEEE style\n"
                "- `/references harvard` — Harvard style"
            )
        return None  # route through AI

    if keyword == "/timeline" or keyword == "/schedule":
        topic = ai.memory.data.get("thesis_topic", "")
        deadline = ai.memory.data.get("deadline", "")
        if not topic:
            return "Set your topic first with `/topic <topic>`."
        if not deadline and not arg:
            return "Set your deadline first with `/deadline <date>` or use `/timeline <deadline>`."
        return None  # route through AI

    if keyword == "/paraphrase":
        if not arg:
            return "Usage: `/paraphrase <text to paraphrase>`\n\nPaste the text you want rewritten in academic style."
        return None  # route through AI

    if keyword == "/viva" or keyword == "/defense":
        topic = ai.memory.data.get("thesis_topic", "")
        if not topic:
            return "Set your topic first with `/topic <topic>`."
        return None  # route through AI

    if keyword == "/progress" or keyword == "/dashboard":
        return _build_progress_dashboard(ai, user_id)

    if keyword == "/deadline":
        if not arg:
            return "Usage: `/deadline <date>` — e.g. `/deadline June 2026`"
        ai.memory.set_field("deadline", arg)
        return f"Deadline set to: **{arg}**"

    if keyword == "/supervisor":
        if not arg:
            return "Usage: `/supervisor <name>`"
        ai.memory.set_field("supervisor", arg)
        return f"Supervisor set to: **{arg}**"

    if keyword == "/university":
        if not arg:
            return "Usage: `/university <name>`"
        ai.memory.set_field("university", arg)
        return f"University set to: **{arg}**"

    return f"Unknown command: `{keyword}`. Type `/help` for available commands."


def _build_progress_dashboard(ai: ThesisAI, user_id: str) -> str:
    """Build a text-based progress dashboard from memory and drafts."""
    mem = ai.memory.data
    lines = ["## Research Progress Dashboard\n"]

    # Thesis info
    lines.append("### Thesis Overview")
    topic = mem.get("thesis_topic") or "_Not set_"
    area = mem.get("research_area") or "_Not set_"
    method = mem.get("methodology") or "_Not set_"
    supervisor = mem.get("supervisor") or "_Not set_"
    university = mem.get("university") or "_Not set_"
    deadline = mem.get("deadline") or "_Not set_"
    lines.append(f"- **Topic:** {topic}")
    lines.append(f"- **Area:** {area}")
    lines.append(f"- **Methodology:** {method}")
    lines.append(f"- **Supervisor:** {supervisor}")
    lines.append(f"- **University:** {university}")
    lines.append(f"- **Deadline:** {deadline}")

    # Deadline countdown
    if mem.get("deadline"):
        from dateutil import parser as dateparser
        try:
            dl = dateparser.parse(mem["deadline"])
            if dl:
                days_left = (dl - datetime.now()).days
                if days_left > 0:
                    lines.append(f"- **Days remaining:** {days_left}")
                elif days_left == 0:
                    lines.append("- **Deadline is TODAY!**")
                else:
                    lines.append(f"- **Overdue by:** {abs(days_left)} days")
        except Exception:
            pass

    # Papers
    papers = mem.get("discussed_papers", [])
    lines.append(f"\n### Papers Reviewed ({len(papers)})")
    if papers:
        for p in papers[-10:]:
            lines.append(f"- {p.get('title', 'Untitled')}")
    else:
        lines.append("_No papers reviewed yet._")

    # Drafts
    drafts_dir = _user_drafts_dir(user_id)
    os.makedirs(drafts_dir, exist_ok=True)
    draft_files = []
    try:
        draft_files = [f for f in os.listdir(drafts_dir) if os.path.isfile(os.path.join(drafts_dir, f))]
    except Exception:
        pass
    lines.append(f"\n### Drafts Written ({len(draft_files)})")
    if draft_files:
        for df in sorted(draft_files):
            size_kb = os.path.getsize(os.path.join(drafts_dir, df)) / 1024
            lines.append(f"- {df} ({size_kb:.1f} KB)")
    else:
        lines.append("_No drafts yet. Use `/write <chapter>` to start._")

    # Decisions
    decisions = mem.get("key_decisions", [])
    lines.append(f"\n### Key Decisions ({len(decisions)})")
    if decisions:
        for d in decisions[-5:]:
            lines.append(f"- {d.get('decision', '')}")
    else:
        lines.append("_No decisions recorded._")

    # Progress log
    progress = mem.get("progress_log", [])
    lines.append(f"\n### Progress Log ({len(progress)})")
    if progress:
        for p in progress[-5:]:
            date_str = p.get("date", "")
            if date_str:
                try:
                    date_str = datetime.fromisoformat(date_str).strftime("%b %d")
                except Exception:
                    pass
            lines.append(f"- [{date_str}] {p.get('milestone', '')}")
    else:
        lines.append("_No milestones logged yet._")

    # Notes
    notes = mem.get("custom_notes", [])
    lines.append(f"\n### Notes ({len(notes)})")
    if notes:
        for n in notes[-5:]:
            lines.append(f"- {n.get('note', '')}")
    else:
        lines.append("_No notes._")

    # Completeness checklist
    lines.append("\n### Checklist")
    checks = [
        ("Topic defined", bool(mem.get("thesis_topic"))),
        ("Research area set", bool(mem.get("research_area"))),
        ("Methodology chosen", bool(mem.get("methodology"))),
        ("Deadline set", bool(mem.get("deadline"))),
        ("Papers reviewed (3+)", len(papers) >= 3),
        ("Outline created", any("outline" in f.lower() for f in draft_files)),
        ("Introduction drafted", any("intro" in f.lower() for f in draft_files)),
        ("Literature review drafted", any("literature" in f.lower() or "lit_review" in f.lower() for f in draft_files)),
        ("Methodology drafted", any("method" in f.lower() for f in draft_files)),
        ("Abstract written", any("abstract" in f.lower() for f in draft_files)),
        ("References generated", any("reference" in f.lower() or "biblio" in f.lower() for f in draft_files)),
    ]
    for label, done in checks:
        mark = "[x]" if done else "[ ]"
        lines.append(f"- {mark} {label}")

    return "\n".join(lines)


# ── Conversation Export ──────────────────────────────────────────

@app.route("/api/conversations/<conv_id>/export/<fmt>", methods=["GET"])
def export_conversation_route(conv_id, fmt):
    """Export a full conversation as Word, Markdown, or LaTeX."""
    uid = _get_user_id()
    conv = _load_conversation(uid, conv_id)
    if conv is None:
        return jsonify({"error": "Conversation not found"}), 404

    if fmt not in ("word", "markdown", "latex"):
        return jsonify({"error": "Format must be word, markdown, or latex"}), 400

    try:
        filepath = export_conversation(conv, fmt)
        ext = {"word": "docx", "markdown": "md", "latex": "tex"}[fmt]
        return send_file(filepath, as_attachment=True,
                         download_name=f"conversation_{conv_id}.{ext}")
    except Exception as exc:
        return jsonify({"error": f"Export failed: {exc}"}), 500


# ── Multi-PDF Upload ─────────────────────────────────────────────

@app.route("/api/upload-pdfs", methods=["POST"])
def upload_multiple_pdfs():
    """Upload and analyze multiple PDFs at once."""
    uid = _get_user_id()
    files = request.files.getlist("files")
    conv_id = request.form.get("conversation_id", "").strip()

    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    ai = get_agent(uid)
    upload_dir = os.path.join(_BASE_DATA_DIR, "user_data", uid, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    results = []
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            results.append({"file": file.filename or "unknown", "error": "Not a PDF file"})
            continue

        filepath = os.path.join(upload_dir, file.filename)
        file.save(filepath)

        try:
            text = extract_pdf_text(filepath)
            if not text.strip():
                results.append({"file": file.filename, "error": "Could not extract text"})
                continue

            prompt = (
                f"I've uploaded a research paper titled \"{file.filename}\". "
                f"Here is the extracted text:\n\n---\n{text[:8000]}\n---\n\n"
                f"Please provide a brief structured analysis:\n"
                f"1. **Title & Authors** (if identifiable)\n"
                f"2. **Problem** — what does it address?\n"
                f"3. **Method** — approach used?\n"
                f"4. **Key Results**\n"
                f"5. **Relevance** — how it relates to my thesis\n"
                f"6. **One-paragraph summary**"
            )
            response = ai.chat(prompt)
            results.append({"file": file.filename, "analysis": response})
        except Exception as exc:
            results.append({"file": file.filename, "error": str(exc)})
        finally:
            try:
                os.remove(filepath)
            except OSError:
                pass

    # Combine results into a single response
    combined = []
    for r in results:
        if "analysis" in r:
            combined.append(f"## {r['file']}\n\n{r['analysis']}")
        else:
            combined.append(f"## {r['file']}\n\n**Error:** {r['error']}")

    full_response = "\n\n---\n\n".join(combined)
    _last_responses[uid] = full_response
    if conv_id:
        file_names = ", ".join(f.filename for f in files if f.filename)
        _append_chat(uid, conv_id, f"Uploaded {len(files)} PDFs: {file_names}", full_response)

    return jsonify({"response": full_response, "count": len(results)})


# ── Bibliography Export ──────────────────────────────────────────

@app.route("/api/bibliography/<style>", methods=["GET"])
def get_bibliography(style):
    """Generate a bibliography file from memory papers."""
    uid = _get_user_id()
    ai = get_agent(uid)
    papers = ai.memory.data.get("discussed_papers", [])
    if not papers:
        return jsonify({"error": "No papers in memory"}), 400
    if style not in ("apa", "ieee", "harvard"):
        return jsonify({"error": "Style must be apa, ieee, or harvard"}), 400

    try:
        filepath = generate_bibliography_file(papers, style)
        return send_file(filepath, as_attachment=True,
                         download_name=f"bibliography_{style}.md")
    except Exception as exc:
        return jsonify({"error": f"Failed: {exc}"}), 500


# ── Main ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not config.GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN not set.")
        print("Get a token at: https://github.com/settings/tokens")
        print("Then add it to your .env file.")
        exit(1)

    print("\n  ThesisAI is running!")
    print("  Open http://localhost:5000 in your browser.\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
