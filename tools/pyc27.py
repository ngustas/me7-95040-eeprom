#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
pyc27.py - inspect Python 2.7 .pyc files from Python 3.

Python 3's marshal and dis cannot read Python 2.7 bytecode. This is a small
standalone reader: enough to walk the code objects in a .pyc, list each
function's constants and names, and disassemble a function.

It was written to recover the logic of 95040tool 0.1, a py2exe app whose
library.zip holds __main__95040tool__.pyc. That is how the authoritative
noCheckSumPages / backupPage lists and the field map were obtained.

Usage:
    pyc27.py tree FILE.pyc            every code object with its int constants
    pyc27.py dis FILE.pyc FUNCTION    disassemble one function by name
"""
import sys

if sys.version_info < (3, 12):
    sys.exit("pyc27.py needs Python 3.12 or newer")

import argparse
import struct
from dataclasses import dataclass, field
from pathlib import Path

PY27_MAGIC = b"\x03\xf3\r\n"


@dataclass
class Code:
    argcount: int
    flags: int
    code: bytes
    consts: list
    names: list[str]
    varnames: list[str]
    filename: str
    name: str
    firstlineno: int
    children: list["Code"] = field(default_factory=list)


class _Null:
    """Marshal TYPE_NULL: terminates a dict."""


NULL = _Null()


def _text(v) -> str:
    return v.decode("latin-1") if isinstance(v, bytes) else str(v)


class Reader:
    def __init__(self, data: bytes) -> None:
        self.d = data
        self.i = 0
        self.interned: list[bytes] = []

    def _take(self, n: int) -> bytes:
        v = self.d[self.i:self.i + n]
        self.i += n
        return v

    def _i32(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

    def load(self):
        t = chr(self._take(1)[0])
        match t:
            case "0":
                return NULL
            case "N":
                return None
            case "F":
                return False
            case "T":
                return True
            case "S":
                return StopIteration
            case ".":
                return Ellipsis
            case "i":
                return self._i32()
            case "I":
                return struct.unpack("<q", self._take(8))[0]
            case "g":
                return struct.unpack("<d", self._take(8))[0]
            case "f":
                return float(self._take(self._take(1)[0]))
            case "y":
                return complex(*struct.unpack("<dd", self._take(16)))
            case "x":
                re_ = float(self._take(self._take(1)[0]))
                im_ = float(self._take(self._take(1)[0]))
                return complex(re_, im_)
            case "l":
                n = self._i32()
                v = 0
                for k in range(abs(n)):
                    v |= struct.unpack("<H", self._take(2))[0] << (15 * k)
                return -v if n < 0 else v
            case "s":
                return self._take(self._i32())
            case "t":
                v = self._take(self._i32())
                self.interned.append(v)
                return v
            case "R":
                return self.interned[self._i32()]
            case "u":
                return self._take(self._i32()).decode("utf-8", "replace")
            case "(" | "[" | "<" | ">":
                return [self.load() for _ in range(self._i32())]
            case "{":
                d = {}
                while (k := self.load()) is not NULL:
                    d[k] = self.load()
                return d
            case "c":
                argcount, _nlocals, _stack, flags = struct.unpack("<4i", self._take(16))
                code = self.load()
                consts = self.load()
                names = [_text(n) for n in self.load()]
                varnames = [_text(n) for n in self.load()]
                self.load()  # freevars
                self.load()  # cellvars
                filename = _text(self.load())
                name = _text(self.load())
                firstlineno = self._i32()
                self.load()  # lnotab
                co = Code(argcount, flags, code, consts, names, varnames,
                          filename, name, firstlineno)
                co.children = [c for c in consts if isinstance(c, Code)]
                return co
            case _:
                raise ValueError(f"unhandled marshal type {t!r} at offset {self.i - 1}")


def load_pyc(path: Path) -> Code:
    data = path.read_bytes()
    if data[:4] != PY27_MAGIC:
        raise SystemExit(f"{path}: not a Python 2.7 .pyc (magic {data[:4].hex()})")
    return Reader(data[8:]).load()


def walk(co: Code, depth: int = 0):
    yield depth, co
    for child in co.children:
        yield from walk(child, depth + 1)


# Python 2.7 opcode table (Lib/opcode.py). Opcodes >= 90 take a 2-byte argument.
HAVE_ARGUMENT = 90
OPNAMES = {
    0: "STOP_CODE", 1: "POP_TOP", 2: "ROT_TWO", 3: "ROT_THREE", 4: "DUP_TOP",
    5: "ROT_FOUR", 9: "NOP", 10: "UNARY_POSITIVE", 11: "UNARY_NEGATIVE",
    12: "UNARY_NOT", 13: "UNARY_CONVERT", 15: "UNARY_INVERT",
    19: "BINARY_POWER", 20: "BINARY_MULTIPLY", 21: "BINARY_DIVIDE",
    22: "BINARY_MODULO", 23: "BINARY_ADD", 24: "BINARY_SUBTRACT",
    25: "BINARY_SUBSCR", 26: "BINARY_FLOOR_DIVIDE", 27: "BINARY_TRUE_DIVIDE",
    28: "INPLACE_FLOOR_DIVIDE", 29: "INPLACE_TRUE_DIVIDE",
    30: "SLICE+0", 31: "SLICE+1", 32: "SLICE+2", 33: "SLICE+3",
    40: "STORE_SLICE+0", 41: "STORE_SLICE+1", 42: "STORE_SLICE+2", 43: "STORE_SLICE+3",
    50: "DELETE_SLICE+0", 51: "DELETE_SLICE+1", 52: "DELETE_SLICE+2", 53: "DELETE_SLICE+3",
    54: "STORE_MAP", 55: "INPLACE_ADD", 56: "INPLACE_SUBTRACT",
    57: "INPLACE_MULTIPLY", 58: "INPLACE_DIVIDE", 59: "INPLACE_MODULO",
    60: "STORE_SUBSCR", 61: "DELETE_SUBSCR", 62: "BINARY_LSHIFT",
    63: "BINARY_RSHIFT", 64: "BINARY_AND", 65: "BINARY_XOR", 66: "BINARY_OR",
    67: "INPLACE_POWER", 68: "GET_ITER", 70: "PRINT_EXPR", 71: "PRINT_ITEM",
    72: "PRINT_NEWLINE", 73: "PRINT_ITEM_TO", 74: "PRINT_NEWLINE_TO",
    75: "INPLACE_LSHIFT", 76: "INPLACE_RSHIFT", 77: "INPLACE_AND",
    78: "INPLACE_XOR", 79: "INPLACE_OR", 80: "BREAK_LOOP", 81: "WITH_CLEANUP",
    82: "LOAD_LOCALS", 83: "RETURN_VALUE", 84: "IMPORT_STAR", 85: "EXEC_STMT",
    86: "YIELD_VALUE", 87: "POP_BLOCK", 88: "END_FINALLY", 89: "BUILD_CLASS",
    90: "STORE_NAME", 91: "DELETE_NAME", 92: "UNPACK_SEQUENCE", 93: "FOR_ITER",
    94: "LIST_APPEND", 95: "STORE_ATTR", 96: "DELETE_ATTR", 97: "STORE_GLOBAL",
    98: "DELETE_GLOBAL", 99: "DUP_TOPX", 100: "LOAD_CONST", 101: "LOAD_NAME",
    102: "BUILD_TUPLE", 103: "BUILD_LIST", 104: "BUILD_SET", 105: "BUILD_MAP",
    106: "LOAD_ATTR", 107: "COMPARE_OP", 108: "IMPORT_NAME", 109: "IMPORT_FROM",
    110: "JUMP_FORWARD", 111: "JUMP_IF_FALSE_OR_POP", 112: "JUMP_IF_TRUE_OR_POP",
    113: "JUMP_ABSOLUTE", 114: "POP_JUMP_IF_FALSE", 115: "POP_JUMP_IF_TRUE",
    116: "LOAD_GLOBAL", 119: "CONTINUE_LOOP", 120: "SETUP_LOOP",
    121: "SETUP_EXCEPT", 122: "SETUP_FINALLY", 124: "LOAD_FAST", 125: "STORE_FAST",
    126: "DELETE_FAST", 130: "RAISE_VARARGS", 131: "CALL_FUNCTION",
    132: "MAKE_FUNCTION", 133: "BUILD_SLICE", 134: "MAKE_CLOSURE",
    135: "LOAD_CLOSURE", 136: "LOAD_DEREF", 137: "STORE_DEREF",
    140: "CALL_FUNCTION_VAR", 141: "CALL_FUNCTION_KW", 142: "CALL_FUNCTION_VAR_KW",
    143: "SETUP_WITH", 145: "EXTENDED_ARG", 146: "SET_ADD", 147: "MAP_ADD",
}
NAME_OPS = {90, 91, 95, 96, 97, 98, 101, 106, 108, 109, 116}
LOCAL_OPS = {124, 125, 126}
COMPARE = ("<", "<=", "==", "!=", ">", ">=", "in", "not in", "is", "is not",
           "exception match", "BAD")


def _const(c) -> str:
    if isinstance(c, Code):
        return f"<code {c.name}>"
    if isinstance(c, bytes):
        return repr(c.decode("latin-1"))
    return repr(c)


def disassemble(co: Code) -> None:
    code, i = co.code, 0
    while i < len(code):
        op, off = code[i], i
        i += 1
        arg = ""
        if op >= HAVE_ARGUMENT:
            a = code[i] | (code[i + 1] << 8)
            i += 2
            if op == 100:
                arg = _const(co.consts[a])
            elif op in NAME_OPS:
                arg = co.names[a] if a < len(co.names) else f"?{a}"
            elif op in LOCAL_OPS:
                arg = co.varnames[a] if a < len(co.varnames) else f"?{a}"
            elif op == 107:
                arg = COMPARE[a] if a < len(COMPARE) else str(a)
            else:
                arg = str(a)
        print(f"  {off:5d} {OPNAMES.get(op, f'OP_{op}'):<22} {arg}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tree", help="list code objects and their int constants")
    t.add_argument("pyc", type=Path)
    d = sub.add_parser("dis", help="disassemble one function")
    d.add_argument("pyc", type=Path)
    d.add_argument("function")
    args = ap.parse_args()

    top = load_pyc(args.pyc)
    if args.cmd == "tree":
        for depth, co in walk(top):
            pad = "  " * depth
            ints = [c for c in co.consts if isinstance(c, int) and not isinstance(c, bool)]
            print(f"{pad}{co.name}()  line {co.firstlineno}")
            if ints:
                print(f"{pad}  ints : {ints}")
            if co.names:
                print(f"{pad}  names: {co.names[:18]}")
        return 0

    for _, co in walk(top):
        if co.name == args.function:
            print(f"=== {co.name}() ===")
            disassemble(co)
            return 0
    print(f"no function named {args.function!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
