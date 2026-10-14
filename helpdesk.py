"""CampusFlow Pro - a text-based IT help desk ticket tracker with SLAs,
escalation and an audit trail.

Run with:  python helpdesk.py
Priority is calculated with plain Python rules (no AI involved).
"""

from clock import parse_iso, utc_now
from config import CATEGORIES, DATA_FILE, FIELDS, LAB_SESSIONS_DIR, URGENCIES
from history import clean_actor, format_event, ticket_history
from knowledge_lab import run_lab
from reports import sla_attention_queue, sla_metrics
from sla import escalate_overdue, is_overdue
from storage import is_legacy_format, load_state, migrate_legacy, save_state
from ticket_service import find_ticket, report, work_queue
from validation import clean_choice, clean_title, clean_users
from workflow import (assign_ticket_logged, change_status_logged,
                      create_ticket_logged)

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

WORKFLOW_ACTIONS = {"1": "in_progress", "2": "resolved", "3": "open"}
CHANGES_DATA = {"1", "2", "3", "7"}


def ask(prompt, cleaner):
    """Ask until the answer is valid."""
    while True:
        try:
            return cleaner(input(prompt))
        except ValueError as e:
            print(f"  Error: {e}")


def ask_time(prompt="Evaluate at (ISO UTC e.g. 2026-10-14T10:00:00+00:00, Enter = now): "):
    return ask(prompt, lambda v: parse_iso(v) if v.strip() else utc_now())


def confirm_duplicates(ids):
    print(f"  Warning: unresolved ticket(s) with the same title and category: {', '.join(ids)}")
    return input("  Create it anyway? (yes/no): ").strip().lower() in ("yes", "y")


def print_tickets(tickets):
    if not tickets:
        print("No tickets to show.")
        return
    print(f"{'ID':<6}{'Title':<28}{'Category':<10}{'Urgency':<8}{'Users':>5}  "
          f"{'Priority':<9}{'Status':<12}Assigned to")
    for t in tickets:
        print(f"{t['id']:<6}{t['title'][:26]:<28}{t['category']:<10}{t['urgency']:<8}"
              f"{t['affected_users']:>5}  {t['priority']:<9}{t['status']:<12}"
              f"{t['assigned_to'] or '-'}")


def print_sla_queue(tickets, now):
    queue = sla_attention_queue(tickets, now)
    if not queue:
        print("No unresolved tickets.")
        return
    print(f"{'ID':<6}{'Priority':<10}{'Status':<13}{'Due (UTC)':<34}State")
    for t in queue:
        state = "** OVERDUE **" if is_overdue(t, now) else "on time"
        print(f"{t['id']:<6}{t['priority']:<10}{t['status']:<13}{t['due_at']:<34}{state}")


def main(data_file=DATA_FILE, sessions_dir=LAB_SESSIONS_DIR):
    try:
        tickets, events = load_state(data_file)
    except ValueError as e:
        print(f"Error: {e}")
        if is_legacy_format(data_file):
            print("Hint: run  python helpdesk.py --migrate  to convert it "
                  "(your original is backed up first).")
        return

    try:
        actor = ask("Operator label (for the audit trail; not verified identity): ",
                    clean_actor)
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
                title = ask("Title: ", clean_title)
                category = ask(f"Category ({'/'.join(CATEGORIES)}): ",
                               lambda v: clean_choice(v, CATEGORIES, "category"))
                urgency = ask(f"Urgency ({'/'.join(URGENCIES)}): ",
                              lambda v: clean_choice(v, URGENCIES, "urgency"))
                users = ask("Affected users: ", clean_users)
                t = create_ticket_logged(tickets, events, title, category, urgency,
                                         users, actor, confirm_duplicate=confirm_duplicates)
                if t is None:
                    print("Cancelled: no ticket or event was created.")
                    continue
                print(f"Created {t['id']} with priority '{t['priority']}', due {t['due_at']}.")
            elif choice == "2":
                ticket_id = input("Ticket ID: ")
                find_ticket(tickets, ticket_id)          # reject unknown IDs first
                t = assign_ticket_logged(tickets, events, ticket_id,
                                         input("Assign to: "), actor)
                print(f"{t['id']} assigned to {t['assigned_to']}.")
            elif choice == "3":
                ticket_id = input("Ticket ID: ")
                action = input("1 Start (open->in_progress)  2 Resolve  3 Reopen: ").strip()
                if action not in WORKFLOW_ACTIONS:
                    print("Invalid action. Enter 1, 2 or 3.")
                    continue
                t = change_status_logged(tickets, events, ticket_id,
                                         WORKFLOW_ACTIONS[action], actor)
                print(f"{t['id']} is now {t['status']} (due {t['due_at']}).")
            elif choice == "4":
                print_tickets(work_queue(tickets))
            elif choice == "5":
                print_sla_queue(tickets, ask_time())
            elif choice == "6":
                t = find_ticket(tickets, input("Ticket ID: "))
                lines = ticket_history(events, t["id"])
                print("\n".join(format_event(e) for e in lines) if lines
                      else f"No history for {t['id']}.")
            elif choice == "7":
                r = escalate_overdue(tickets, events, ask_time(), actor)
                print(f"Newly escalated: {r['newly_escalated']} {r['new_ids']}; "
                      f"already escalated: {r['already_escalated']} {r['already_ids']}.")
            elif choice == "8":
                now = ask_time("Report time (ISO UTC, Enter = now): ")
                r, m = report(tickets), sla_metrics(tickets, events, now)
                print(f"\nTotal tickets: {r['total']}")
                print(f"Open: {m['open']}, in_progress: {m['in_progress']}, "
                      f"resolved: {m['resolved']}")
                print(f"Overdue unresolved: {m['overdue_unresolved']}, "
                      f"escalated in current cycle: {m['escalated_current_cycle']}")
                print("By priority:", ", ".join(f"{k}: {v}" for k, v in m["by_priority"].items()))
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
                run_lab(sessions_dir=sessions_dir)        # gets no ticket data
                continue
            elif choice == "11":
                print_tickets(tickets)
            elif choice == "12":
                t = find_ticket(tickets, input("Ticket ID: "))
                for field in FIELDS + ["created_at", "updated_at", "due_at",
                                       "escalation_cycle"]:
                    print(f"  {field:<17}: {t[field] if t[field] is not None else '(unassigned)'}")
            else:
                print("Invalid choice. Enter a number from the menu.")
                continue

            if choice in CHANGES_DATA:
                save_state(tickets, events, data_file)
        except ValueError as e:
            print(f"Error: {e}")
        except OSError as e:
            print(f"Error: could not save to {data_file}: {e}")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break


def run_migration(data_file=DATA_FILE):
    """Explicit, user-invoked legacy migration (never runs automatically)."""
    print(f"Migrate '{data_file}' from the old list format to schema version 2.")
    print("The original is copied to a backup first. The old file had no timestamps,")
    print("so created/updated/due times are set to NOW and no history is invented.")
    if input("Continue? (yes/no): ").strip().lower() not in ("yes", "y"):
        print("Cancelled. Nothing was changed.")
        return
    try:
        r = migrate_legacy(data_file)
    except ValueError as e:
        print(f"Error: {e}")
        return
    print(f"Migrated {r['migrated']} ticket(s). Backup: {r['backup']}")


if __name__ == "__main__":
    import sys
    if "--migrate" in sys.argv[1:]:
        run_migration()
    else:
        main()
