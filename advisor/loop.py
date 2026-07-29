"""A hand-rolled tool-use loop, not the Anthropic SDK's beta tool runner.
Deliberately: this project's whole point is being able to explain exactly
how the agentic loop works in an interview, and a manual loop is more
transparent than a beta helper that hides the request/execute/continue
cycle. It also avoids a beta SDK dependency for three tools this small."""
import json


def run_advisor_turn(client, model, system_prompt, tools, tool_dispatch, messages, max_iterations=6):
    """Send `messages` to Claude with `tools` declared. Whenever Claude asks
    for a tool call, execute it via `tool_dispatch(name, input) -> dict` and
    feed the result back, looping until Claude stops calling tools or
    `max_iterations` is hit.

    Returns (reply_text, transcript) -- `transcript` is `messages` plus every
    assistant/tool_result turn generated during the loop, in case the caller
    wants to inspect which tools were actually called. Persisting that
    transcript across turns is the caller's choice, not this function's --
    app.py keeps only the final reply_text in its chat history, so the next
    turn starts from plain conversation text rather than replaying stale
    tool_use/tool_result blocks."""
    working = list(messages)

    for _ in range(max_iterations):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=system_prompt,
            tools=tools,
            messages=working,
        )

        if response.stop_reason != "tool_use":
            reply = "".join(block.text for block in response.content if block.type == "text")
            return reply, working

        working.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = tool_dispatch(block.name, block.input)
            except Exception as exc:
                result = {"error": str(exc)}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })
        working.append({"role": "user", "content": tool_results})

    return (
        "I wasn't able to reach a final answer within this turn's tool-call "
        "budget — try asking a narrower question.",
        working,
    )
