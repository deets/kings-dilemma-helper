#!/usr/bin/env python3
import sys
import argparse
import pathlib

BASE = pathlib.Path(__file__).parent
LUA = BASE / "lua"
SAVEGAMES = pathlib.Path("~/.local/share/Tabletop Simulator/Saves/").expanduser()
IGNORED_SAVE_GAMES = ["SaveFileInfos.json", "TS_AutoSave.json"]

def pull(args):
    with pathlib.Path(args.savegame).open() as inf:
        print(inf.read())


def list_savegames(_args):
    for game in SAVEGAMES.glob("*.json"):
        if game.name not in IGNORED_SAVE_GAMES:
            print(f'"{game}"')


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    parser_pull = subparsers.add_parser("pull")
    parser_pull.set_defaults(func=pull)
    parser_pull.add_argument("savegame")

    parser_pull = subparsers.add_parser("list-savegames")
    parser_pull.set_defaults(func=list_savegames)

    args = parser.parse_args()
    try:
        func = args.func
    except AttributeError:
        print("Please specifiy subcommand. Use -h to see the available ones")
        sys.exit(1)
    else:
        func(args)

if __name__ == '__main__':
    main()
