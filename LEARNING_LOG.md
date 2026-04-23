# Learning Log - Gemini Vision Sprint

## Hours Spent

- **Day 1**: 5 hours (9AM - 2AM)
- **Day 2**: 6 hours (9AM - 3PM)
- **Total**: ~11 hours

## What I Got Stuck On & How I Got Unstuck

### Free API Key Limitations
- Gemini free tier hits quota (429/503) very quickly
- **Stuck**: Single API key caused frequent failures
- **Unstuck**: Implemented exponential backoff + key rotation. Multiple keys rotate automatically on rate limit errors

### SSE Integration
- **Stuck**: Tried to use SSE format with streamGenerateContent, but response was pretty-printed JSON split across lines
- **Stuck**: Parsing each line as separate JSON failed - buffer had partial objects
- **Unstuck**: Tracked brace depth ({}) to detect complete JSON objects, skipped empty lines/brackets/commas
- **Stuck**: UI didn't stream - showed nothing until complete
- **Unstuck**: Used `httpx.AsyncClient.stream()` for true streaming instead of regular request

## AI Coding Tools Used

- **Claude (Anthropic)**: Initial project planning and architecture decisions
- **ChatGPT (OpenAI) and Gemini (Google) **: Reference for alternative coding styles when Opencode struggled
- **Opencode (MiniMax 2.5 Free)**: Main coding tool - acted as orchestrator and wrote most of the code

## How I Validated AI-Generated Code

- Used Opencode's MCP tools for syntax checking before committing
- Ran local Python syntax validation (`py_compile`)
- Checked JS syntax with Node.js parser
- Tested on Render after push to catch runtime issues

## Decisions & Trade-offs

| Decision | Trade-off |
|----------|-----------|
| FastAPI over Go/Fiber | Faster prototyping, but less performant for high concurrency |
| Render over Cloud Run | Free tier limitations, but simpler setup |
| Vanilla HTML/JS | No build step, but less maintainable for complex UI |
| In-memory sessions | Simple but lost on restart; Redis would be better for production |

**Why FastAPI?** Its my most familiar tool for rapid prototyping. Would try Go + Cloud Run next time.

## What I Would Do Differently

1. **Test with ChatGPT's approach** - Got stuck on SSE because I trusted Opencode with just the official docs. Should have asked other AI tools for implementation patterns
2. **Use Go + Cloud Run** - Industry standard for production, better concurrency
3. **Add Redis earlier** - In-memory sessions are fine for demo but not production
4. **Test SSE on multiple AI models** - Each has different streaming behavior

## Technical Learnings

### SSE Streaming Evolution
- **Attempt 1**: `generateContent` - waited for full response, then chunked (fake streaming)
- **Attempt 2**: `streamGenerateContent` with regular HTTP - still got all data at once
- **Solution**: `httpx.AsyncClient.stream()` + brace-depth parsing for true streaming

### Key Files Created/Modified

```
app/
├── main.py          # All endpoints + streaming logic
├── gemini_client.py # API key rotation
├── middleware.py    # Request ID extraction
├── logger.py        # Structured JSON logging 
├── sessions.py      # Multi-turn sessions 
static/
└── index.html       # Frontend with SSE + thinking cards
```

## Summary

Built an AI image analyzer with Gemini API, FastAPI, and vanilla JS. Implemented real-time SSE streaming, multi-turn conversations, structured logging with request_id, and automatic key rotation for rate limits. Main challenge was SSE parsing - required custom JSON extraction from pretty-printed response.