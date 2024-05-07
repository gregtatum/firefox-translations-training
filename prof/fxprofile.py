import http.server
import json
import os
import pdb
import sys
import urllib
import pstats
from typing import Any, Generator, Iterator, Literal, Optional
import socket
import webbrowser

stats = pstats.Stats("test_mtdata.prof")

FuncKeyTuple = tuple[
    # path, e.g. "/path/to/script.py
    str,
    # line_number
    int,
    # name, e.g. "humanize_size", "iter_content", "__setitem__", "<lambda>"
    str,
]
FuncInfoTuple = tuple[
    # Calls count
    int,
    # Primitive calls count
    int,
    # Self time
    float,
    # Total time
    float,
]
CallersDict = dict[FuncKeyTuple, FuncInfoTuple]
FuncStatsTupleWithCallers = tuple[int, int, float, float, CallersDict]
StatsDict = dict[FuncKeyTuple, FuncStatsTupleWithCallers]
CallKey = tuple[FuncKeyTuple, FuncKeyTuple]


root_key = ("root", 0, "root")

def stringify_keys(data):
    if isinstance(data, dict):
        # Convert tuple keys to strings and recursively apply to values
        return {str(key): stringify_keys(value) for key, value in data.items()}
    elif isinstance(data, list):
        # Recursively apply to each item in the list
        return [stringify_keys(item) for item in data]
    elif isinstance(data, tuple):
        # Convert tuples to lists and recursively apply to each element
        return [stringify_keys(item) for item in data]
    else:
        # Return the item as is if it's neither a dict nor a list
        return data

data = stringify_keys(stats.stats)

# with open("cprofile.json", 'w') as file:
#     json.dump(data, file)
# sys.exit()

class FuncKey:
    def __init__(self, tuple: FuncKeyTuple) -> None:
        # e.g. "/path/to/script.py
        self.path: str = tuple[0]
        self.line_number: int = tuple[1]
        # e.g. "humanize_size"
        self.name: str = tuple[2]
        self.tuple = tuple


class FuncInfo:
    def __init__(self, tuple: FuncStatsTupleWithCallers) -> None:
        self.calls_count: int = tuple[0]
        # Non-recursive calls into the function
        self.primitive_calls_count: int = tuple[1]

        self.self_time: float = tuple[2]
        self.total_time: float = tuple[3]

        self.callers: CallersDict = tuple[4]
        self.tuple: FuncStatsTupleWithCallers = tuple


class Stats:
    def __init__(self, stats_dict: StatsDict):
        self.dict = stats_dict

    def items(self) -> Iterator[tuple[FuncKey, FuncInfo]]:
        for k, v in self.dict.items():
            yield (FuncKey(k), FuncInfo(v))


def get_stats_dict() -> StatsDict:
    """Coerce the type"""
    return stats.stats  # type: ignore


def get_empty_profile():
    return {
        "meta": {
            "interval": 1,
            "startTime": 0,
            "abi": "",
            "misc": "",
            "oscpu": "",
            "platform": "",
            "processType": 0,
            "extensions": {"id": [], "name": [], "baseURL": [], "length": 0},
            "categories": [
                {"name": "Other", "color": "grey", "subcategories": ["Other"]},
                {"name": "Idle", "color": "transparent", "subcategories": ["Other"]},
                {"name": "Layout", "color": "purple", "subcategories": ["Other"]},
                {"name": "JavaScript", "color": "yellow", "subcategories": ["Other"]},
                {"name": "GC / CC", "color": "orange", "subcategories": ["Other"]},
                {"name": "Network", "color": "lightblue", "subcategories": ["Other"]},
                {"name": "Graphics", "color": "green", "subcategories": ["Other"]},
                {"name": "DOM", "color": "blue", "subcategories": ["Other"]},
            ],
            "product": "Python",
            "stackwalk": 0,
            "toolkit": "",
            "version": 29,
            "preprocessedProfileVersion": 48,
            "appBuildID": "",
            "sourceURL": "",
            "physicalCPUs": 0,
            "logicalCPUs": 0,
            "CPUName": "",
            "symbolicated": True,
            "markerSchema": [],
        },
        "libs": [],
        "pages": [],
        "threads": [],
    }


def get_empty_thread():
    return {
        "processType": "default",
        "processStartupTime": 0,
        "processShutdownTime": None,
        "registerTime": 0,
        "unregisterTime": None,
        "pausedRanges": [],
        "name": "Empty",
        "isMainThread": True,
        "pid": "0",
        "tid": 0,
        "samples": {
            "weightType": "tracing-ms",
            "weight": [],
            "stack": [],
            "time": [],
            "length": 0,
        },
        "markers": {
            "data": [],
            "name": [],
            "startTime": [],
            "endTime": [],
            "phase": [],
            "category": [],
            "length": 0,
        },
        "stackTable": {"frame": [], "prefix": [], "category": [], "subcategory": [], "length": 0},
        "frameTable": {
            "address": [],
            "inlineDepth": [],
            "category": [],
            "subcategory": [],
            "func": [],
            "nativeSymbol": [],
            "innerWindowID": [],
            "implementation": [],
            "line": [],
            "column": [],
            "length": 0,
        },
        "stringArray": [],
        "funcTable": {
            "isJS": [],
            "relevantForJS": [],
            "name": [],
            "resource": [],
            "fileName": [],
            "lineNumber": [],
            "columnNumber": [],
            "length": 0,
        },
        "resourceTable": {"lib": [], "name": [], "host": [], "type": [], "length": 0},
        "nativeSymbols": {
            "libIndex": [],
            "address": [],
            "name": [],
            "functionSize": [],
            "length": 0,
        },
    }


def get_free_port() -> int:
    # https://stackoverflow.com/questions/1365265/on-localhost-how-do-i-pick-a-free-port-number
    sock = socket.socket()
    sock.bind(("", 0))
    return sock.getsockname()[1]


waiting_for_request = True

def build_profile(stats_dict: StatsDict):
    roots: list[FuncKeyTuple] = []
    funcs: dict[FuncKeyTuple, dict[str, Any]] = {}
    calls: dict[tuple[FuncKeyTuple, FuncKeyTuple], FuncInfoTuple] = {}

    # Compute the roots, and populate the FuncClass dict.
    for func_key, func_info in stats_dict.items():
        funcs[func_key] = {
            "calls": [],
            "called": [],
            "info": func_info,
        }
        children_func_keys = func_info[4]
        if len(children_func_keys) == 0:
            # This is a root function.
            roots.append(func_key)
            # Add the calls without the caller information.
            calls[(root_key, func_key)] = (func_info[0], func_info[1], func_info[2], func_info[3])

    for parent_func_key, (_, _, _, _, children_func_keys) in stats_dict.items():
        for child_func_key, func_info_tuple in children_func_keys.items():
            call_key = (parent_func_key, child_func_key)
            assert call_key not in calls
            funcs[child_func_key]["calls"].append(parent_func_key)
            funcs[parent_func_key]["called"].append(child_func_key)
            calls[call_key] = func_info_tuple

    profile = get_empty_profile()
    thread = get_empty_thread()
    profile["threads"].append(thread)

    func_table = thread["funcTable"]
    string_array: list[str] = thread["stringArray"]
    frame_table = thread["frameTable"]
    stack_table = thread["stackTable"]
    samples = thread["samples"]
    resource_table = thread["resourceTable"]
    func_key_to_index: dict[tuple[str, str], int] = {}
    frame_key_to_index: dict[tuple[str, int, str], int] = {}

    def get_string_index(string: str) -> int:
        try:
            return string_array.index(string)
        except ValueError:
            string_index = len(string_array)
            string_array.append(string)
            return string_index

    # Build out the resources, frame table, and func table
    for func_key, func_info in stats_dict.items():
        path, line_number, name = func_key

        # print(f"{name}:{line_number} - {int(func_info[2] * 1000)} - {int(func_info[3] * 1000)}")

        # Make sure the file is added to the resource table.
        path_index = get_string_index(path)
        try:
            resource_index = resource_table["name"].index(path_index)
        except ValueError:
            resource_index = resource_table["length"]
            resource_table["name"].append(resource_index)
            resource_table["length"] += 1

        try:
            func_index = func_key_to_index[(path, name)]
        except KeyError:
            func_index = func_table["length"]
            func_table["isJS"].append(False)
            func_table["relevantForJS"].append(False)
            func_table["name"].append(get_string_index(name))
            func_table["resource"].append(resource_index)
            func_table["fileName"].append(get_string_index(path))
            func_table["lineNumber"].append(line_number)
            func_table["columnNumber"].append(None)
            func_table["length"] += 1

        frame_table["address"].append(-1)
        frame_table["inlineDepth"].append(0)
        frame_table["category"].append(0) # Other
        frame_table["subcategory"].append(0) # Other
        frame_table["func"].append(func_index)
        frame_table["nativeSymbol"].append(None)
        frame_table["innerWindowID"].append(None)
        frame_table["implementation"].append(None)
        frame_table["line"].append(line_number)
        frame_table["column"].append(None)
        frame_key_to_index[func_key] = frame_table["length"]
        frame_table["length"] += 1

    for (parent_func_key, child_func_key), func_info in calls.items():
        _, _, self_time, total_time = func_info
        parent_frame_index = frame_key_to_index.get(parent_func_key)
        child_frame_index = frame_key_to_index.get(child_func_key)

        stack_table["frame"].append(child_frame_index)
        stack_table["category"].append(0)
        stack_table["subcategory"].append(0)
        stack_table["prefix"].append(parent_frame_index)
        stack_index = stack_table["length"]
        stack_table["length"] += 1

        samples["weight"].append(total_time * 1000)
        samples["stack"].append(stack_index)
        samples["time"].append(0)
        samples["length"] += 1

    profile_path = "fxprofile.json"
    # print("Profile path", profile_path)
    with open("fxprofile.json", 'w') as file:
        json.dump(profile, file)

    port = get_free_port()
    json_url = f"http://localhost:{port}"

    webbrowser.open("https://profiler.firefox.com/from-url/" + urllib.parse.quote(json_url, safe=''))
    server = http.server.HTTPServer(("", port), ServeFile)

    while waiting_for_request:
        server.handle_request()

# def build_profile(stats_dict: StatsDict):
#     for func_key, func_info in stats_dict.items():
#         path, line_number, name = func_key
#         total_time = func_info[3]
#         if name.startswith("test_"):
#             print(f"{name}\t{func_info[3]}")


class ServeFile(http.server.BaseHTTPRequestHandler):
    """Creates a one-time server that just serves one file."""

    def _set_headers(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def log_message(self, *args):
        # Disable server logging.
        pass

    def do_HEAD(self):
        self._set_headers()

    def do_GET(self):
        self._set_headers()
        profile_path = os.path.join("fxprofile.json")
        try:
            with open(profile_path, "rb") as file:
                self.wfile.write(file.read())
        except Exception as exception:
            print("Failed to serve the file", exception)
            pass
        global waiting_for_request
        waiting_for_request = False



def build_profile2(stats_dict: StatsDict):
    test_mtdata_key = None
    for func_key in stats_dict:
        if func_key[2] == 'test_mtdata':
            test_mtdata_key = func_key
            break

    # print(test_mtdata_key)

    # return


    # for func_key, func_info in stats_dict.items():
    #     print(func_key, func_info)
    #     for other_key, other_info in stats_dict.items():
    #         callers_dict = other_info[4]
    #         caller_info = callers_dict.get(func_key)
    #         if caller_info:
    #             print("   ", other_key, caller_info)


    child_to_parent = {}
    for child_key, child_func_info in stats_dict.items():
        parents = child_func_info[4]
        for parent_key in parents:
            child_to_parent[child_key] = parent_key

    next_key = test_mtdata_key
    while True:
        print(next_key)
        next_key = child_to_parent[next_key]


def calc_callers(stats_dict: StatsDict):
    # https://github.com/baverman/flameprof/blob/master/flameprof.py
    roots = []
    funcs = {}
    calls = {}
    for func, (cc, nc, tt, ct, clist) in stats.items():
        funcs[func] = {'calls': [], 'called': [], 'stat': (cc, nc, tt, ct)}
        if not clist:
            roots.append(func)
            calls[('root', func)] = funcs[func]['stat']

    for func, (_, _, _, _, clist) in stats.items():
        for cfunc, t in clist.items():
            assert (cfunc, func) not in calls
            funcs[cfunc]['calls'].append(func)
            funcs[func]['called'].append(cfunc)
            calls[(cfunc, func)] = t

    total = sum(funcs[r]['stat'][3] for r in roots)
    ttotal = sum(funcs[r]['stat'][2] for r in funcs)

    if not (0.8 < total / ttotal < 1.2):
        eprint('Warning: flameprof can\'t find proper roots, root cumtime is {} but sum tottime is {}'.format(total, ttotal))

    # Try to find suitable root
    newroot = max((r for r in funcs if r not in roots), key=lambda r: funcs[r]['stat'][3])
    nstat = funcs[newroot]['stat']
    ntotal = total + nstat[3]
    if 0.8 < ntotal / ttotal < 1.2:
        roots.append(newroot)
        calls[('root', newroot)] = nstat
        total = ntotal
    else:
        total = ttotal

    funcs['root'] = {'calls': roots,
                     'called': [],
                     'stat': (1, 1, 0, total)}

    return funcs, calls


build_profile2(stats.stats)