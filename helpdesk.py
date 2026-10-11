"""CampusFlow - a simple text-based IT help desk ticket tracker.

Run with:  python helpdesk.py
Priority is calculated with plain Python rules (no AI involved).
"""

from config import CATEGORIES, DATA_FILE, FIELDS, URGENCIES
from storage import load_tickets, save_tickets
from ticket_service import (assign_ticket, change_status, create_ticket,
                            find_ticket, report, work_queue)
from validation import clean_choice, clean_title, clean_users

MENU = """
===== CampusFlow Help Desk =====
1. Create ticket
2. List all tickets
3. View one ticket
4. Assign ticket
5. Start work  (open -> in_progress)
6. Resolve     (in_progress -> resolved)
7. Reopen      (resolved -> open)
8. Work queue
9. Reports
0. Exit"""


def ask(prompt, cleaner):
    """Ask until the answer is valid."""
    while True:
        try:
            return cleaner(input(prompt))
        except ValueError as e:
            print(f"  Error: {e}")


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


def main():
    try:
        tickets = load_tickets()
    except ValueError as e:
        print(f"Error: {e}")
        return

    changes_data = {"1", "4", "5", "6", "7"}
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
                t = create_ticket(tickets, title, category, urgency, users)
                print(f"Created {t['id']} with priority '{t['priority']}'.")
            elif choice == "2":
                print_tickets(tickets)
            elif choice == "3":
                t = find_ticket(tickets, input("Ticket ID: "))
                for field in FIELDS:
                    print(f"  {field:<15}: {t[field] if t[field] is not None else '(unassigned)'}")
            elif choice == "4":
                ticket_id = input("Ticket ID: ")
                find_ticket(tickets, ticket_id)          # reject unknown IDs first
                t = assign_ticket(tickets, ticket_id, input("Assign to: "))
                print(f"{t['id']} assigned to {t['assigned_to']}.")
            elif choice in ("5", "6", "7"):
                new_status = {"5": "in_progress", "6": "resolved", "7": "open"}[choice]
                t = change_status(tickets, input("Ticket ID: "), new_status)
                print(f"{t['id']} is now {t['status']}.")
            elif choice == "8":
                print_tickets(work_queue(tickets))
            elif choice == "9":
                r = report(tickets)
                print(f"\nTotal tickets: {r['total']}")
                print("By status:  ", ", ".join(f"{k}: {v}" for k, v in r["status"].items()))
                print("By priority:", ", ".join(f"{k}: {v}" for k, v in r["priority"].items()))
            else:
                print("Invalid choice. Enter a number from the menu.")
                continue

            if choice in changes_data:
                save_tickets(tickets)
        except ValueError as e:
            print(f"Error: {e}")
        except OSError as e:
            print(f"Error: could not save to {DATA_FILE}: {e}")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break


if __name__ == "__main__":
    main()
