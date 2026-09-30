#!/usr/bin/env python3
"""The interface a generator offers the shop.

A generator is a Python module, not a command line. `generate(out, **params)`
builds the part and returns the report; `main()` is an argparse wrapper for
the times a shell is genuinely what you want. The shop imports and calls.

`namespace` is what lets that conversion leave a generator's body alone. The
work in these scripts reads its settings off the argparse namespace as `a.x`,
and several of them also use a bare `a` as an ordinary local -- gen_knot and
gen_bolted go further and have an argument actually named `--a`. Rewriting
`a.x` to `x` across seventeen files would be seventeen chances to rename
something that only looked like a setting. So the namespace is rebuilt
instead, and the body never changes.

Defaults and types come from the parser, which is the one place they are
already written down. Nothing is formatted into a string and parsed back:
the parser's own `type` callable does the coercion, so `--freq` is an int
here for the same reason it is an int on the command line.
"""
import argparse


def namespace(parser, out=None, **kw):
    """A typed argument namespace built from keywords.

    Unknown keywords are ignored rather than raising: a card may carry a
    dial the generator has stopped reading, and refusing to build at all
    is a worse answer than building what was asked for.
    """
    ns = argparse.Namespace()
    actions = [a for a in parser._actions
               if not isinstance(a, argparse._HelpAction)]
    for act in actions:
        setattr(ns, act.dest, act.default)
    # Keyed on the OPTION as well as the dest. `--len` is declared with
    # dest="length" because `len` is a builtin, so a card sending len=19
    # matched nothing and the generator got None -- silently, because a
    # missing keyword is indistinguishable from one that was not sent.
    by_name = {}
    for act in actions:
        by_name[act.dest] = act
        for opt in act.option_strings:
            by_name[opt.lstrip("-").replace("-", "_")] = act

    for key, value in kw.items():
        act = by_name.get(key.replace("-", "_"))
        if act is None:
            continue
        if value is not None and not isinstance(value, bool) \
                and act.type is not None:
            value = act.type(value)
        setattr(ns, act.dest, value)

    if out is not None and "out" in by_name:
        ns.out = out

    # argparse refuses a missing required argument; called as a function
    # nothing did, so a card that failed to send one handed the generator
    # a None and it surfaced hundreds of lines later as
    # "unsupported operand type(s) for -: 'NoneType' and 'float'".
    # Say which setting is missing, at the point it is missing.
    missing = [a.option_strings[0] if a.option_strings else a.dest
               for a in actions
               if a.required and getattr(ns, a.dest, None) is None]
    if missing:
        raise ValueError("missing required setting(s): " + ", ".join(missing))
    return ns


def cli(parser, generate):
    """Run `generate` from the command line and print its report."""
    import json
    a = parser.parse_args()
    rep = generate(**vars(a))
    print(json.dumps(rep))
    return 0 if rep.get("ok") else 1
