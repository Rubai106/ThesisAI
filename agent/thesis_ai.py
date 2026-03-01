"""Core ThesisAI agent — manages the conversation loop, tool dispatch, and
streaming output via the OpenAI chat-completions API with function calling.
"""

import json
from typing import Any

from openai import OpenAI

import config
from agent.memory import MemoryManager
from agent.prompts import build_system_prompt
from agent.tools import TOOL_SCHEMAS, execute_tool


class ThesisAI:
    """Autonomous research-assistant agent with tool-use and persistent memory."""

    def __init__(
        self,
        memory_file: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.client = OpenAI(
            api_key=api_key or config.GITHUB_TOKEN,
            base_url=base_url or config.GITHUB_BASE_URL,
            timeout=55.0,        # avoid Vercel 60s timeout
            max_retries=2,       # auto-retry on transient errors
        )
        self.model = model or config.GITHUB_MODEL
        self._api_key = api_key or config.GITHUB_TOKEN
        self._base_url = base_url or config.GITHUB_BASE_URL
        self.memory = MemoryManager(filepath=memory_file)
        self.conversation: list[dict[str, Any]] = []
        self._rebuild_system_message()

    def update_client(self, api_key: str, base_url: str | None = None, model: str | None = None) -> None:
        """Swap out the OpenAI client for a new key/base_url without losing conversation."""
        self._api_key = api_key
        if base_url:
            self._base_url = base_url
        if model:
            self.model = model
        self.client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=55.0,
            max_retries=2,
        )

    # ── helpers ──────────────────────────────────────────────────

    def _rebuild_system_message(self) -> None:
        """Refresh the system message with the latest memory context."""
        ctx = self.memory.render_context()
        sys_msg = {"role": "system", "content": build_system_prompt(ctx)}
        if self.conversation and self.conversation[0]["role"] == "system":
            self.conversation[0] = sys_msg
        else:
            self.conversation.insert(0, sys_msg)

    def _trim_history(self) -> None:
        """Keep conversation history within limits."""
        max_msgs = config.MAX_CONVERSATION_HISTORY
        # Always keep system message at index 0
        if len(self.conversation) > max_msgs + 1:
            self.conversation = [self.conversation[0]] + self.conversation[-(max_msgs):]

    # ── main chat ────────────────────────────────────────────────

    def chat(self, user_message: str) -> str:
        """Send a user message and run the full agent loop.

        Returns the final assistant text response.
        """
        self._rebuild_system_message()
        self.conversation.append({"role": "user", "content": user_message})
        self._trim_history()

        for _ in range(config.MAX_AGENT_ITERATIONS):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.3,
            )

            choice = response.choices[0]
            message = choice.message

            # Append the assistant message (may contain tool_calls)
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if message.content:
                assistant_msg["content"] = message.content
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
            self.conversation.append(assistant_msg)

            # If no tool calls, we're done
            if not message.tool_calls:
                return message.content or ""

            # Execute every tool call and append results
            for tc in message.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                try:
                    result = execute_tool(fn_name, fn_args, memory_manager=self.memory)
                except Exception as exc:
                    result = json.dumps({"error": f"Tool execution failed: {exc}"})

                self.conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                )

        # Fallback after max iterations
        return (
            "I've reached the maximum number of reasoning steps. "
            "Here's what I have so far:\n\n" + (message.content or "")
        )

    def reset(self) -> None:
        """Clear conversation history (memory persists on disk)."""
        self.conversation.clear()
        self._rebuild_system_message()
