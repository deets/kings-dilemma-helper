#!/usr/bin/env python3
import sys
import argparse
import pathlib
import json
from collections import defaultdict


BASE = pathlib.Path(__file__).parent
LUA = BASE / "lua"
SAVEGAMES = pathlib.Path("~/.local/share/Tabletop Simulator/Saves/").expanduser()
IGNORED_SAVE_GAMES = ["SaveFileInfos.json", "TS_AutoSave.json"]


def take(data, path):
    for part in path[:-1]:
        data = data[part]
    return data[path[-1]]


class Script:

    MAIN = "__main__"

    def __init__(self, path, content, full_document):
        self.path = path
        self._full_document = full_document
        self._parts = self._process(content)

    def _process(self, content):
        res = defaultdict(list)
        key = self.MAIN

        for line in content.split("\n"):
            if line.startswith("----#include"):
                candidate = line.split(" ", 1)[1].strip()
                if key == candidate:
                    key = self.MAIN
                    res[key].append(f"#include {candidate}")
                else:
                    key = candidate
            else:
                res[key].append(line)
        return res

    @property
    def guid(self):
        return take(self._full_document, self.path[:-1] + ("GUID",))

    @property
    def name(self):
        return take(self._full_document, self.path[:-1] + ("Nickname",))

    def __repr__(self):
        return f"{self.name}:{self.guid}: {self._parts.keys()}"


def jpath(data, filter_, path=()):
    if len(path) > 1 and path[-1] == filter_:
        yield (path, data)

    elif isinstance(data, dict):
        for key, value in data.items():
            yield from jpath(value, filter_, path + (key,))
    elif isinstance(data, list):
        for i, value in enumerate(data):
            yield from jpath(value, filter_, path + (i,))
    elif isinstance(data, (str, float, int)):
        pass
    else:
        raise Exception("Unknown Type", path, data)


def pull(args):
    with pathlib.Path(args.savegame).open() as inf:
        data = json.load(inf)

    scripts = []
    for path, script in jpath(data, "LuaScript"):
        if script:
            scripts.append(Script(path, script, data))

    print(scripts)

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
