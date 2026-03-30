# Lessons Learned

This file captures patterns from mistakes and corrections.
Updated after every session. Reviewed at the start of each session.

---

## 2026-03-29

### Lesson 1: numpy int64 is not JSON serializable
**What happened:** `detect_anomalies()` crashed when trying to serialize pandas output.
**Root cause:** pandas returns numpy int64/float64 types — not native Python types.
**Fix:** Explicitly cast to `float()` or `int()` before returning from any tool.
**Rule:** Always cast numeric values from pandas to native Python types in tool return dicts.

### Lesson 2: Windows terminal blocks Unicode/emoji output
**What happened:** Agent responses with emojis crashed with `UnicodeEncodeError` on Windows.
**Root cause:** Windows terminal defaults to cp1252 encoding, not UTF-8.
**Fix:** Add `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")` at the top of any script that prints Claude output.
**Rule:** Always set UTF-8 stdout in entry point scripts on Windows.

### Lesson 3: API key exposed in chat
**What happened:** API key was pasted directly into conversation.
**Root cause:** Key was only shown once after creation — copied incorrectly.
**Fix:** Always store keys immediately in `.env`. Never paste in chat, code, or GitHub.
**Rule:** The only place an API key should ever appear is in `.env`.
