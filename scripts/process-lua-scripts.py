#!/usr/bin/env python3
import sys
import argparse
import pathlib
import json
import logging
import itertools
import hashlib
import operator
from collections import defaultdict


BASE = pathlib.Path(__file__).parent.parent
LUA = BASE / "lua"
assert(LUA.exists())

SAVEGAMES = pathlib.Path("~/.local/share/Tabletop Simulator/Saves/").expanduser()
IGNORED_SAVE_GAMES = ["SaveFileInfos.json", "TS_AutoSave.json"]
INCLUDE_PATH = LUA / "include"
SAVED_OBJECTS_PATH = LUA / "saved-objects"

ATOM_INCLUDE_PATH = pathlib.Path("~/Documents/Tabletop Simulator/").expanduser()
ATOM_SCRIPT_PATH = pathlib.Path("/tmp/TabletopSimulator/Tabletop Simulator Lua")

by_name = operator.attrgetter("name")


def fix_line_ending(line):
    return line.rstrip("\n").rstrip("\r") + "\r\n"


def save(path, content):
    dir_ = path.parent
    dir_.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as outf:
        outf.write("".join(fix_line_ending(line) for line in content).encode("utf-8"))


def take(data, path):
    for part in path[:-1]:
        data = data[part]
    return data[path[-1]]


def consistent(scripted_objects):
    scripted_objects = sorted(scripted_objects, key=by_name)
    consistent = True
    for kind, objects in itertools.groupby(
            scripted_objects, key=by_name):
        a, b = itertools.tee(objects)
        md5 = next(a).md5
        consistent &= all(o.md5 == md5 for o in b)
    return consistent


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
                    res[key].append(f"#include {candidate}\r\n")
                else:
                    key = candidate
            else:
                res[key].append(line + "\n")
        return res

    @property
    def guid(self):
        return take(self._full_document, self.path[:-1] + ("GUID",))

    @property
    def name(self):
        return take(self._full_document, self.path[:-1] + ("Nickname",))

    @property
    def md5(self):
        m = hashlib.md5()
        for script in self._parts.values():
            m.update("".join(script).encode("utf-8"))
        return m.hexdigest()

    @property
    def includes(self):
        for key, value in self._parts.items():
            if key != self.MAIN:
                yield INCLUDE_PATH / key, value

    @property
    def main(self):
        return (
            SAVED_OBJECTS_PATH / f"{self.name}.ttslua",
            self._parts[self.MAIN]
        )

    def update_from_repository(self):
        for key in self._parts:
            if key == self.MAIN:
                path = SAVED_OBJECTS_PATH / f"{self.name}.ttslua"
            else:
                path = INCLUDE_PATH / key
            with path.open("r") as inf:
                self._parts[key] = inf.readlines()

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


def load_scripts_from_savegame(savegame):
    with savegame.open() as inf:
        data = json.load(inf)

    scripts = []
    for path, script in jpath(data, "LuaScript"):
        if script:
            scripts.append(Script(path, script, data))
    return scripts


def pull(args):
    savegame = pathlib.Path(args.savegame)
    scripts = load_scripts_from_savegame(savegame)

    if consistent(scripts):
        logging.info("All scripts consistent, placing them into the repository")
        # we only need one object of all kinds, as they are consistent
        for _, scripts in itertools.groupby(sorted(scripts, key=by_name)):
            script = next(scripts)
            for path, content in script.includes:
                save(path, content)
            save(*script.main)
            with (LUA / "game.json").open("w") as outf, savegame.open("r") as inf:
                outf.write(inf.read())

    else:
        logging.warning("The scripts are inconsistent, please fix this!")


def publish_to_atom(args):
    scripts = load_scripts_from_savegame(LUA / "game.json")
    # In theory we should have a consistent state in the
    # scripts, but I pull them from the repository
    # nonetheless.
    for script in scripts:
        script.update_from_repository()

    ATOM_INCLUDE_PATH.mkdir(parents=True, exist_ok=True)

    for script in scripts:
        # includes are written many times over. So mote it be
        for path, content in script.includes:
            part = path.relative_to(INCLUDE_PATH)
            full = ATOM_INCLUDE_PATH / part
            full.parent.mkdir(parents=True, exist_ok=True)
            save(full, content)
        main_path = ATOM_SCRIPT_PATH / f"{script.name}.{script.guid}.ttslua"
        save(main_path, script.main[1])


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

    parser_pull = subparsers.add_parser(
        "publish-to-atom",
        help="Takes the current state of the game in the repository "
             "and uses it to populate the Atom save locations as "
             "expected by the TTS Lua plugin."
    )
    parser_pull.set_defaults(func=publish_to_atom)

    args = parser.parse_args()
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
    )
    try:
        func = args.func
    except AttributeError:
        print("Please specifiy subcommand. Use -h to see the available ones")
        sys.exit(1)
    else:
        func(args)


if __name__ == '__main__':
    main()
