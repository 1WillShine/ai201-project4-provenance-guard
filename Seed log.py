"""
seed_log.py — Generates realistic sample audit log entries for README documentation.
Run once to populate audit_log.json with 3+ entries including an appeal.
Does NOT call the Groq API — uses pre-computed scores for documentation purposes.
"""
import json
import uuid

ENTRIES = [
    {
        "content_id": "3f7a2b1e-84cc-4a19-a23b-9d12f6e00a11",
        "creator_id": "user-poet-42",
        "timestamp": "2025-06-20T10:14:32.441Z",
        "attribution": "likely_ai",
        "confidence": 0.8312,
        "llm_score": 0.87,
        "style_score": 0.77,
        "status": "classified",
        "appeal_reasoning": None,
        "appeal_timestamp": None,
    },
    {
        "content_id": "7c91d3fa-1b5e-4c77-be4a-0f233a8d9122",
        "creator_id": "user-journal-88",
        "timestamp": "2025-06-20T10:22:05.881Z",
        "attribution": "likely_human",
        "confidence": 0.2104,
        "llm_score": 0.19,
        "style_score": 0.24,
        "status": "classified",
        "appeal_reasoning": None,
        "appeal_timestamp": None,
    },
    {
        "content_id": "a4e58bcd-c721-4d90-9c3b-2b8173fa6433",
        "creator_id": "user-writer-17",
        "timestamp": "2025-06-20T10:35:49.002Z",
        "attribution": "uncertain",
        "confidence": 0.5540,
        "llm_score": 0.51,
        "style_score": 0.61,
        "status": "under_review",
        "appeal_reasoning": (
            "I wrote this myself from personal experience studying abroad. "
            "I am a non-native English speaker and my writing may appear more "
            "formal than a native speaker's informal prose."
        ),
        "appeal_timestamp": "2025-06-20T11:02:17.334Z",
    },
    {
        "content_id": "d9821cfa-0e3b-4f11-ab27-7e43010bc544",
        "creator_id": "user-blogger-55",
        "timestamp": "2025-06-20T14:08:22.119Z",
        "attribution": "likely_human",
        "confidence": 0.1887,
        "llm_score": 0.16,
        "style_score": 0.23,
        "status": "classified",
        "appeal_reasoning": None,
        "appeal_timestamp": None,
    },
]

with open("audit_log.json", "w") as f:
    json.dump(ENTRIES, f, indent=2)

print(f"Seeded audit_log.json with {len(ENTRIES)} entries.")
