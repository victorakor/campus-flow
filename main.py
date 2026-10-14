"""CampusFlow Pro entry point.

    python main.py             start the help desk
    python main.py --migrate   convert an old list-style data file (explicit, backed up)
"""

import sys

from campusflow.cli import main, run_migration

if __name__ == "__main__":
    if "--migrate" in sys.argv[1:]:
        run_migration()
    else:
        main()
