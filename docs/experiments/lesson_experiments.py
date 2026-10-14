"""Engineer A: the small UNRELATED experiments from Lessons A-D.
Run:  python docs/experiments/lesson_experiments.py
Predict each output BEFORE you run it, then paste the real output into
docs/ai-learning-log.md as your evidence."""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone


def lesson_a_utc():
    start = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    print("A1 +60 min:", (start + timedelta(minutes=60)).isoformat())
    naive = datetime(2026, 1, 1, 9, 0)
    try:
        print(naive < start)
    except TypeError as e:                       # naive vs aware cannot be compared
        print("A2 naive vs aware ->", type(e).__name__, "-", e)
    # datetime.now() differs on every call, so a test cannot assert an exact value;
    # an injected `now` makes the same call return the same answer every time.


_calls = {"n": 0}


def lesson_b_idempotent_counter(key, seen):
    if key in seen:                              # repeat -> no new side effect
        return False
    seen.add(key)
    _calls["n"] += 1
    return True


def lesson_b():
    seen = set()
    results = [lesson_b_idempotent_counter("loan-1", seen) for _ in range(3)]
    print("B results:", results, "counter:", _calls["n"])


def lesson_c():
    loan = {"book": "Dune", "status": "available"}
    log = []

    def lend(loan, who):
        if loan["status"] != "available":
            raise ValueError("already lent")     # rejected: nothing logged
        before = loan["status"]
        loan["status"] = "lent"
        log.append({"who": who, "before": before, "after": loan["status"]})  # AFTER success

    lend(loan, "ada")
    try:
        lend(loan, "bob")
    except ValueError as e:
        print("C rejected:", e)
    print("C log entries:", len(log), log)


def lesson_d():
    state = {"items": [1, 2, 3]}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "copy.json")
        with open(path, "w") as f:
            json.dump(state, f)
        with open(path, "w") as f:               # corrupt the COPY only
            f.write('{"items": [1, 2,')
        try:
            with open(path) as f:
                loaded = json.load(f)
            state = loaded
        except json.JSONDecodeError as e:
            print("D load rejected:", e)
    print("D in-memory state still:", state)


if __name__ == "__main__":
    for fn in (lesson_a_utc, lesson_b, lesson_c, lesson_d):
        fn()
        print()
