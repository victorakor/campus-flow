"""Engineering Knowledge Lab: 10 scenario questions, auto-scored choices,
free-text explanations (never auto-graded), and a saved JSON session record.
This module never touches ticket or event data."""

import json
import os
import tempfile

from clock import to_iso, utc_now
from config import LAB_SESSIONS_DIR

PARTICIPANTS = ("A", "B")
VALID_CHOICES = ("A", "B", "C", "D")
MIN_EXPLANATIONS = 3
MIN_EXPLANATION_CHARS = 15

# (id, topic, scenario, options, correct, what to explain, rationale)
QUESTIONS = [
    ("Q1", "SLA boundaries",
     "A critical ticket is created at 10:00 UTC. At 11:00 UTC, is it overdue?",
     ["Yes", "No, only strictly after 11:00", "Only if assigned", "Only if reopened"], "B",
     "Explain the difference between 'due' and 'overdue'.",
     "Due at 11:00 means the deadline instant; overdue needs now STRICTLY later than due_at."),
    ("Q2", "Priority rules",
     "urgency=low and affected_users=10. What priority?",
     ["Critical", "High", "Medium", "Low"], "B",
     "Explain which rule applies first.",
     "Critical needs high urgency AND 10+ users; 'high urgency OR 10+ users' matches next, so high."),
    ("Q3", "Invariants and rejected operations",
     "An unassigned open ticket moves directly to in_progress. What should happen?",
     ["Transition succeeds", "Status changes but history stays",
      "Reject without changing ticket or events", "Delete the ticket"], "C",
     "Explain the invariant.",
     "Invalid actions must leave ticket status, timestamps and event history untouched."),
    ("Q4", "SLA cycles and reopening",
     "A resolved high-priority ticket is reopened. Which SLA behavior is correct?",
     ["Keep old due_at always", "Start a fresh SLA cycle while preserving created_at",
      "Reset created_at to today's date", "Delete previous events"], "B",
     "Explain why.",
     "Reopening starts a new cycle (new due_at) but history and created_at stay intact."),
    ("Q5", "Idempotent escalation",
     "An overdue ticket is checked three times within one SLA cycle. How many new ESCALATE events?",
     ["Three", "Two", "One", "Zero"], "C",
     "Explain idempotency.",
     "Repeating the operation must not repeat side effects: one escalation per cycle."),
    ("Q6", "Defensive JSON loading",
     "The saved file has invalid JSON. What is the safest action?",
     ["Replace data with empty list", "Use eval()", "Ignore and keep running with partial data",
      "Reject load and preserve existing valid state"], "D",
     "Explain your choice.",
     "Validate before replacing state; never overwrite good data or use eval()."),
    ("Q7", "Code review and testing",
     "A PR changes SLA calculations but adds no boundary tests. What should a reviewer do?",
     ["Approve because it runs locally", "Request focused tests and explanation",
      "Merge and test next week", "Ask AI to approve automatically"], "B",
     "Explain your reasoning.",
     "Boundary logic is where SLA bugs hide; reviewers ask for evidence, not trust."),
    ("Q8", "Verifying AI suggestions",
     "An assistant says 'use eval() to parse stored JSON'. What should you do?",
     ["Copy it", "Disable tests", "Reject and use JSON parsing with validation",
      "Share the whole file publicly"], "C",
     "Explain how you verified.",
     "eval() executes arbitrary code; json.load plus schema validation is safe."),
    ("Q9", "Duplicate warnings",
     "Titles ' Wi-Fi   Down ' and 'wi-fi down' share a category, both unresolved. What should the CLI do?",
     ["Silently delete original", "Warn and require confirmation", "Silently block forever",
      "Ignore normalization"], "B",
     "Explain the trade-off.",
     "Warn, don't block: repeat reports can be legitimate, but silent duplicates add noise."),
    ("Q10", "Audit log integrity",
     "An invalid return/status operation is rejected. What should happen to event count?",
     ["Increase by one", "Increase twice", "Reset to zero", "Stay unchanged"], "D",
     "Explain the reason.",
     "Events record SUCCESSFUL changes only; a rejected action changed nothing to record."),
]


def validate_choice(raw):
    """Only exact A/B/C/D is valid (no lowercase, blank, or E)."""
    if raw not in VALID_CHOICES:
        raise ValueError("Enter exactly A, B, C or D (capital letter).")
    return raw


def validate_participant(raw):
    if raw not in PARTICIPANTS:
        raise ValueError("Participant must be exactly A or B.")
    return raw


def score_answers(choices):
    """choices: {question_id: letter} -> (score out of 10, topics to revise)."""
    score, revise = 0, []
    for qid, topic, _s, _o, correct, _e, _r in QUESTIONS:
        if choices.get(qid) == correct:
            score += 1
        else:
            revise.append(topic)
    return score, revise


def explanation_required(explained_so_far, index, total=len(QUESTIONS)):
    """True when skipping would make it impossible to reach MIN_EXPLANATIONS."""
    return MIN_EXPLANATIONS - explained_so_far >= total - index + 1


def clean_explanation(raw, required):
    text = " ".join(str(raw).split())
    if not text and not required:
        return ""
    if len(text) < MIN_EXPLANATION_CHARS:
        raise ValueError(f"Write a short explanation (at least {MIN_EXPLANATION_CHARS} "
                         "characters)." if required else
                         "Press Enter to skip, or write at least "
                         f"{MIN_EXPLANATION_CHARS} characters.")
    return text


def save_session(record, sessions_dir=LAB_SESSIONS_DIR):
    """Atomic write of one session file. Returns the path."""
    os.makedirs(sessions_dir, exist_ok=True)
    stamp = record["timestamp"].replace(":", "").replace("-", "").replace("+0000", "Z")
    stamp = stamp.replace("+", "").replace(".", "_")
    path = os.path.join(sessions_dir, f"session_{record['participant']}_{stamp}.json")
    fd, tmp = tempfile.mkstemp(dir=sessions_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return path


def run_lab(input_fn=None, output_fn=None, sessions_dir=LAB_SESSIONS_DIR, now=None):
    """Interactive quiz. Takes NO ticket data, so it cannot modify tickets."""
    input_fn = input_fn or input          # looked up at call time (patchable in tests)
    output_fn = output_fn or print
    def ask(prompt, cleaner):
        while True:
            try:
                return cleaner(input_fn(prompt))
            except ValueError as e:
                output_fn(f"  Error: {e}")

    output_fn("\n===== Engineering Knowledge Lab =====")
    participant = ask("Participant [A/B]: ", validate_participant)
    choices, explanations = {}, {}
    total = len(QUESTIONS)
    for i, (qid, topic, scenario, options, _c, prompt, _r) in enumerate(QUESTIONS, 1):
        output_fn(f"\n{qid} ({i}/{total}) {scenario}")
        for letter, text in zip(VALID_CHOICES, options):
            output_fn(f"  {letter}) {text}")
        choices[qid] = ask("Your answer [A/B/C/D]: ", validate_choice)
        required = explanation_required(len(explanations), i, total)
        label = "required" if required else "optional, Enter to skip"
        text = ask(f"{prompt} ({label}): ", lambda v: clean_explanation(v, required))
        if text:
            explanations[qid] = text

    score, revise = score_answers(choices)
    output_fn(f"\nScore: {score}/{total}")
    output_fn("Topics to revise: " + (", ".join(revise) if revise else "none"))
    for qid, topic, _s, options, correct, _e, rationale in QUESTIONS:
        mark = "correct" if choices[qid] == correct else f"incorrect (correct: {correct})"
        output_fn(f"{qid} {topic}: you chose {choices[qid]} - {mark}")
        if choices[qid] != correct:
            output_fn(f"    Why: {rationale}")
        if qid in explanations:
            output_fn(f"    Your explanation: {explanations[qid]}")

    record = {"participant": participant, "timestamp": to_iso(now or utc_now()),
              "choices": choices, "score": score, "revision_topics": revise,
              "explanations": explanations}
    path = save_session(record, sessions_dir)
    output_fn(f"\nSession saved to {path}")
    return record
