# Glossary

**Question this document answers:** What do the key domain and system terms mean?

Terms are defined once here and used consistently everywhere else in this
knowledge base. If a document needs to explain a term rather than link here,
that's a signal the term is missing from this list — add it instead.

## How to Use This Document

- Alphabetical order.
- One definition per term. If a term means different things in different
  contexts, note both under the same entry rather than creating duplicates.
- Link to this file (`[term](../glossary.md#term)`) instead of re-explaining
  a term inline.

## Terms

### Agent
The LangGraph ReAct loop that decides which tools to call and composes the final response. Full detail: [architecture/overview.md](architecture/overview.md).

### ASR
Automatic speech recognition — faster-whisper turns Telegram voice notes (and optionally terminal audio) into text.

### LangGraph
The framework providing the agent graph: nodes, the tool-calling loop, and per-thread state.

### Long-term memory
Persistent facts about the owner stored under `data/memory/`, refreshed into the agent's context per query. See `src/memory/long_term_memory.py`.

### Ollama
Local model server. Hosts the default text model (`OLLAMA_MODEL`) and the local vision fallback.

### Phase
One of the five completed build stages of Tsuzi: agent, memory, Telegram, PC control, vision. See [product/roadmap.md](product/roadmap.md).

### ReAct
Reason-then-act: the model alternates reasoning and tool calls until it can produce a final answer.

### Safe smoke
The deterministic pytest marker that gates CI and PRs — no desktop automation, network, credentials, or Ollama calls inside it. See [standards/testing.md](standards/testing.md).

### Side-effect test
A test marked `side_effect`: may open apps, mutate desktop state, use network, or need credentials. Never runs in CI.

### Thread
One conversation in LangGraph state; Telegram chats and terminal sessions map to thread ids used for short-term memory.

### Trace
The JSONL record per query in `logs/agent_traces/`: query source, thread id, tool calls, results, final response, duration, errors.

### Tsuzi
This project — a local-first Windows desktop assistant with memory, Telegram control, PC automation, and screen vision.

### TTS
Text-to-speech — Kokoro, KittenTTS, and QwenTTS engines speak responses locally.

### Vision provider
The backend for screen understanding: `nvidia`, `ollama`, or `auto` (NVIDIA when `NVIDIA_API_KEY` is set, otherwise local Ollama).

### Wrapped tool
A capability the agent can call, registered in `src/tools/wrapped_tools.py` with a docstring the model reads as its description.

## Adding a Term

1. Confirm it isn't already covered under a different name.
2. Add it alphabetically.
3. Keep the definition to 1-2 sentences; link elsewhere for depth.

## Related Documents

- Architecture overview: [architecture/overview.md](architecture/overview.md)
- Coding standards: [standards/coding.md](standards/coding.md)
