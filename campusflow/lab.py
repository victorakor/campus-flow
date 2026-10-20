"""Engineering Knowledge Lab: 10 scenario questions, auto-scored A/B/C/D answers,
free-text explanations (never auto-graded) and a saved JSON session record.
This module never receives or changes ticket data."""

import json
import os

from .logic import ask, now

CHOICES = ("A", "B", "C", "D")
MIN_EXPLANATIONS, MIN_CHARS = 3, 15

# (id, topic, scenario, options, correct, what to explain, why)
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


def score(choices):
    """{question_id: letter} -> (score out of 10, topics to revise)."""
    revise = [q[1] for q in QUESTIONS if choices.get(q[0]) != q[4]]
    return len(QUESTIONS) - len(revise), revise


def run_lab(sessions_dir, input_fn=None, output_fn=None, when=None):
    """Run the quiz, print the results and save the session. Returns the record."""
    out = output_fn or print
    total = len(QUESTIONS)

    def pick(options, label):                          # exact capital letters only
        def clean(raw):
            if raw not in options:
                raise ValueError(f"Enter exactly {label}.")
            return raw
        return clean

    out("\n===== Engineering Knowledge Lab =====")
    who = ask("Participant [A/B]: ", pick(("A", "B"), "A or B (capital letter)"), input_fn, out)
    choices, explanations = {}, {}
    for i, (qid, _topic, scenario, options, _ok, prompt, _why) in enumerate(QUESTIONS, 1):
        out(f"\n{qid} ({i}/{total}) {scenario}")
        for letter, text in zip(CHOICES, options):
            out(f"  {letter}) {text}")
        choices[qid] = ask("Your answer [A/B/C/D]: ", pick(CHOICES, "A, B, C or D (capital letter)"),
                           input_fn, out)
        # An explanation becomes compulsory once skipping would make 3 impossible.
        required = MIN_EXPLANATIONS - len(explanations) >= total - i + 1

        def explain(raw):
            text = " ".join(raw.split())
            if not text and not required:
                return ""
            if len(text) < MIN_CHARS:
                raise ValueError(f"Write at least {MIN_CHARS} characters"
                                 + ("." if required else ", or press Enter to skip."))
            return text

        label = "required" if required else "optional, Enter to skip"
        text = ask(f"{prompt} ({label}): ", explain, input_fn, out)
        if text:
            explanations[qid] = text

    points, revise = score(choices)
    out(f"\nScore: {points}/{total}")
    out("Topics to revise: " + (", ".join(revise) if revise else "none"))
    for qid, topic, _s, _o, ok, _p, why in QUESTIONS:
        out(f"{qid} {topic}: you chose {choices[qid]} - "
            + ("correct" if choices[qid] == ok else f"incorrect (correct: {ok})"))
        if choices[qid] != ok:
            out(f"    Why: {why}")
        if qid in explanations:
            out(f"    Your explanation: {explanations[qid]}")

    when = when or now()
    record = {"participant": who, "timestamp": when.isoformat(), "choices": choices,
              "score": points, "revision_topics": revise, "explanations": explanations}
    os.makedirs(sessions_dir, exist_ok=True)
    path = os.path.join(sessions_dir, f"session_{who}_{when.strftime('%Y%m%dT%H%M%S_%fZ')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    out(f"\nSession saved to {path}")
    return record
