"""Vercel serverless entry point — wraps the Flask app."""

import sys
import os
import traceback

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app import app
except Exception as e:
    # If the main app fails to import, create a minimal Flask app
    # that shows the error for debugging
    from flask import Flask
    app = Flask(__name__)

    error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    @app.route("/")
    def error_page():
        return f"<pre>Import Error:\n{error_msg}</pre>", 500

    @app.route("/<path:p>")
    def error_catch_all(p):
        return f"<pre>Import Error:\n{error_msg}</pre>", 500
