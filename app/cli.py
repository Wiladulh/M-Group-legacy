import argparse

from app.core.config import get_settings
from app.core.db import Database


def main():
    parser = argparse.ArgumentParser(prog="nvm")
    parser.add_argument("command", nargs="?", choices=["init"])
    args = parser.parse_args()

    if args.command == "init":
        settings = get_settings()
        Database(settings.db_path).migrate()
        print(settings.db_path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
