"""CampusFlow Pro - a text-based IT help desk with SLAs, escalation and an audit trail.

    python main.py

Priority is calculated by plain Python rules (no AI at runtime).
"""

import os

from campusflow.lab import run_lab
from campusflow.logic import (CATEGORIES, FIELDS, URGENCIES, ask, assign_ticket,
                              change_status, clean_actor, clean_fields, create_ticket,
                              escalate_overdue, find_ticket, is_overdue, now, parse,
                              report, sla_queue, ticket_history, work_queue)
from campusflow.storage import load_state, save_state

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, "data", "tickets.json")
LAB_DIR = os.path.join(ROOT, "lab_sessions")

MENU = """
===== CampusFlow Pro Help Desk =====
1.  Create ticket
2.  Assign ticket
3.  Start / resolve / reopen
4.  Original Open Work Queue
5.  SLA Attention Queue
6.  Ticket history
7.  Check and escalate overdue
8.  Reports
9.  Save / load
10. Engineering Knowledge Lab
11. List all tickets
12. View one ticket
0.  Exit"""

STATUS_FOR = {"1": "in_progress", "2": "resolved", "3": "open"}
CHANGES_DATA = {"1", "2", "3", "7"}                    # saved automatically


def ask_time(prompt="Evaluate at (ISO UTC e.g. 2026-10-14T10:00:00+00:00, Enter = now): "):
    return ask(prompt, lambda v: parse(v) if v.strip() else now())


def show(tickets, when=None):
    """Print a ticket table; pass `when` to add the SLA due/overdue columns."""
    if not tickets:
        print("No tickets to show.")
        return
    extra = f"{'Due (UTC)':<34}State" if when else "Assigned to"
    print(f"{'ID':<6}{'Title':<28}{'Category':<10}{'Urgency':<8}{'Users':>5}  "
          f"{'Priority':<9}{'Status':<12}{extra}")
    for t in tickets:
        end = (f"{t['due_at']:<34}{'** OVERDUE **' if is_overdue(t, when) else 'on time'}"
               if when else t["assigned_to"] or "-")
        print(f"{t['id']:<6}{t['title'][:26]:<28}{t['category']:<10}{t['urgency']:<8}"
              f"{t['affected_users']:>5}  {t['priority']:<9}{t['status']:<12}{end}")


def main(data_file=DATA_FILE, sessions_dir=LAB_DIR):
    try:
        tickets, events = load_state(data_file)
    except ValueError as e:                            # damaged file: stop, never overwrite
        print(f"Error: {e}")
        return
    try:
        actor = ask("Operator label (for the audit trail; not verified identity): ", clean_actor)
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye.")
        return

    while True:
        print(MENU)
        try:
            choice = input("Choose an option: ").strip()
            if choice == "0":
                print("Goodbye.")
                break
            elif choice == "1":
                prompts = ["Title: ", f"Category ({'/'.join(CATEGORIES)}): ",
                           f"Urgency ({'/'.join(URGENCIES)}): ", "Affected users: "]
                answers = ["x", "Other", "low", "1"]    # placeholders, replaced one by one
                for i, prompt in enumerate(prompts):    # re-ask only the invalid field
                    answers[i] = ask(prompt, lambda v, i=i: clean_fields(
                        *answers[:i], v, *answers[i + 1:])[i])
                t = create_ticket(
                    tickets, events, *answers, actor,
                    confirm=lambda ids: input(
                        f"  Warning: unresolved ticket(s) with the same title and category: "
                        f"{', '.join(ids)}\n  Create it anyway? (yes/no): "
                    ).strip().lower() in ("yes", "y"))
                print(f"Created {t['id']} with priority '{t['priority']}', due {t['due_at']}."
                      if t else "Cancelled: no ticket or event was created.")
            elif choice == "2":
                t = find_ticket(tickets, input("Ticket ID: "))
                t = assign_ticket(tickets, events, t["id"], input("Assign to: "), actor)
                print(f"{t['id']} assigned to {t['assigned_to']}.")
            elif choice == "3":
                t = find_ticket(tickets, input("Ticket ID: "))
                action = input("1 Start (open->in_progress)  2 Resolve  3 Reopen: ").strip()
                if action not in STATUS_FOR:
                    print("Invalid action. Enter 1, 2 or 3.")
                    continue
                t = change_status(tickets, events, t["id"], STATUS_FOR[action], actor)
                print(f"{t['id']} is now {t['status']} (due {t['due_at']}).")
            elif choice == "4":
                show(work_queue(tickets))
            elif choice == "5":
                when = ask_time()
                show(sla_queue(tickets, when), when)
            elif choice == "6":
                t = find_ticket(tickets, input("Ticket ID: "))
                lines = ticket_history(events, t["id"])
                for e in lines:
                    print(f"{e['event_id']}  {e['timestamp']}  {e['ticket_id']}  "
                          f"{e['event_type']:<8} {e['before_status'] or '-'} -> "
                          f"{e['after_status']}  by {e['actor']}  {e['details']}")
                if not lines:
                    print(f"No history for {t['id']}.")
            elif choice == "7":
                new, already = escalate_overdue(tickets, events, actor, ask_time())
                print(f"Newly escalated: {len(new)} {new}; already escalated: "
                      f"{len(already)} {already}.")
            elif choice == "8":
                r = report(tickets, events, ask_time("Report time (ISO UTC, Enter = now): "))
                print(f"\nTotal tickets: {r['total']}")
                print("Status:  " + ", ".join(f"{k}: {v}" for k, v in r["status"].items()))
                print("Priority: " + ", ".join(f"{k}: {v}" for k, v in r["priority"].items()))
                print(f"Overdue unresolved: {r['overdue']}, "
                      f"escalated in current cycle: {r['escalated']}")
            elif choice == "9":
                action = input("1 Save now  2 Reload from disk: ").strip()
                if action == "1":
                    save_state(tickets, events, data_file)
                    print(f"Saved to {data_file}.")
                elif action == "2":
                    new_tickets, new_events = load_state(data_file)   # validate first
                    tickets[:], events[:] = new_tickets, new_events
                    print(f"Loaded {len(tickets)} tickets and {len(events)} events.")
                else:
                    print("Invalid action. Enter 1 or 2.")
            elif choice == "10":
                run_lab(sessions_dir)                  # gets no ticket data
            elif choice == "11":
                show(tickets)
            elif choice == "12":
                t = find_ticket(tickets, input("Ticket ID: "))
                for field in FIELDS + ["created_at", "updated_at", "due_at", "escalation_cycle"]:
                    print(f"  {field:<17}: {'(unassigned)' if t[field] is None else t[field]}")
            else:
                print("Invalid choice. Enter a number from the menu.")

            if choice in CHANGES_DATA:
                save_state(tickets, events, data_file)
        except ValueError as e:
            print(f"Error: {e}")
        except OSError as e:
            print(f"Error: could not save to {data_file}: {e}")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break


if __name__ == "__main__":
    main()
