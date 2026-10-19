"""DairyManager — milk collection manager for dairies & collection centers.

Entry point: initializes the database (creating it on first run) and
starts the CustomTkinter desktop UI.
"""

import db
import ui


def main():
    db.init_db()
    ui.main()


if __name__ == "__main__":
    main()
