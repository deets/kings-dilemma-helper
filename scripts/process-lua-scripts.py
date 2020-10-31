#!/usr/bin/env python3
import sys
import argparse
import pathlib
import json
import logging
import itertools
import hashlib
import operator
import os
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
TMP = pathlib.Path("/tmp")

by_name = operator.attrgetter("name")


def stripped_lines(lines):
    return [line.rstrip() for line in lines]


def fix_line_ending(line):
    return line.rstrip() + os.linesep


def save(path, content):
    dir_ = path.parent
    dir_.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as outf:
        outf.write(os.linesep.join(line for line in content))


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


def inconsintency_report(scripted_objects, write_to_temp=False):
    clusters = defaultdict(list)
    for script in scripted_objects:
        clusters[script.md5].append(script)
        if write_to_temp:
            main_path = TMP / f"{script.name}.{script.guid}.ttslua"
            xml_path = TMP / f"{script.name}.{script.guid}.xml"
            main_path.write_bytes(script.lua.encode("utf-8"))
            xml_path.write_bytes(script.raw_xml.encode("utf-8"))

    for cluster in clusters.values():
        logging.warning(f"{cluster[0].name}: {', '.join(s.guid for s in cluster)}")


def normalize_lines(lines):
    while lines[-1] == "":
        lines[:] = lines[:-1]
    lines.append("")


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


class Script:

    MAIN = "__main__"

    def __init__(self, path, content, full_document):
        self.path = path
        self._full_document = full_document
        self._parts = self._process(content)
        self.xml = self._process_xml()

    def _process(self, content):
        res = defaultdict(list)
        key = self.MAIN
        for line in content.split("\n"):
            line = line.rstrip()
            if line.startswith("----#include"):
                candidate = line.split(" ", 1)[1].strip()
                if key == candidate:
                    key = self.MAIN
                    res[key].append(f"#include {candidate}")
                else:
                    key = candidate
            else:
                res[key].append(line)
        # we normalize the last lines of the file
        # this can lead to inconsistencies
        for lines in res.values():
            normalize_lines(lines)
        return res

    def _process_xml(self):
        xml_path = SAVED_OBJECTS_PATH / f"{self.name}.xml"
        xml_lines = take(self._full_document, self.path[:-1] + ("XmlUI",)).split("\n")
        xml_lines = [line.rstrip() for line in xml_lines]
        normalize_lines(xml_lines)
        return xml_path, xml_lines

    @property
    def guid(self):
        return take(self._full_document, self.path[:-1] + ("GUID",))

    @property
    def name(self):
        return take(self._full_document, self.path[:-1] + ("Nickname",))

    @property
    def lua(self):
        lines = []
        for line in self._parts[self.MAIN]:
            if line.startswith("#include"):
                candidate = line.split(" ", 1)[1]
                assert candidate in self._parts
                lines.append(f"----#include {candidate}")
                lines.extend(self._parts[candidate])
                lines.append(f"----#include {candidate}")
            else:
                lines.append(line)
        return os.linesep.join(lines)

    @property
    def raw_xml(self):
        return take(self._full_document, self.path[:-1] + ("XmlUI",))

    @property
    def md5(self):
        m = hashlib.md5()
        for script in self._parts.values():
            m.update("\n".join(script).encode("utf-8"))
        m.update("\n".join(self.xml[1]).encode("utf-8"))
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
            with path.open("r", encoding="utf-8") as inf:
                self._parts[key] = stripped_lines(inf.readlines())
        path = SAVED_OBJECTS_PATH / f"{self.name}.xml"
        with path.open("r", encoding="utf-8") as inf:
            self.xml = (self.xml[0], stripped_lines(inf.readlines()))

    def __repr__(self):
        return f"{self.name}:{self.guid}: {self._parts.keys()}"


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
            save(*script.xml)

        with (LUA / "game.json").open("w") as outf, savegame.open("r") as inf:
            outf.write(inf.read())


    else:
        logging.warning("The scripts are inconsistent, please fix this!")
        inconsintency_report(scripts, args.write_to_temp)


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
        xml_path = ATOM_SCRIPT_PATH / f"{script.name}.{script.guid}.xml"
        save(main_path, script.main[1])
        save(xml_path, script.xml[1])


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
    parser_pull.add_argument(
        "-w", "--write-to-temp",
        action="store_true",
        help="Write the parsed Lua and XML files to tmp",
    )

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
