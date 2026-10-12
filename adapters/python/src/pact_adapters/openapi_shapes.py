"""OpenAPI's schemas as PACT answer shapes, and every keyword accounted for.

`openapi.py` reads an OpenAPI description into one tool file per operation;
this module is the half that reads a JSON Schema into the lines of `takes:`
and `answers-with:`. It maps what PACT's shape grammar can say and NAMES the
rest (S1: no silent drops):

* `boolean`, `integer`, `number`, `string` → `yes-or-no`, `whole-number`,
  `number`, `text`; a string of format `date`, `date-time` or `time` → `date`,
  `date-and-time`, `time`; `enum` (or `const`) → `one of ...`;
* `array` → `list of <its items>`;
* an object with properties → a named shape under `workspace.yaml`'s
  `shapes:`, one per component schema (`#/components/schemas/Pet` → `pet`) or
  per place an object is written inline; `allOf` merges its parts;
* `nullable: true`, a `type` list holding `"null"`, a `oneOf`/`anyOf` of one
  shape and `null`, a property left out of `required`, and a property the
  server only reads or only writes → `, optional`.

Each schema keyword lands in one of the report's three buckets, keyed by where
it was written (`#/components/schemas/Pet.maxLength`, or
`POST /pet body name.pattern`), so a keyword this module never heard of is a
silent drop the report finds by itself. What PACT has no home for is
`not_portable` with the reason: a value's limits (`pattern`, `maximum`, ...),
its examples and defaults, its description below an action's own arguments.
What it cannot say at all — a `oneOf` of several shapes, a free-form object, a
schema that refers to itself — is `unmapped`, and the line is left out where a
shape was needed: an argument the model is never offered, never one offered
as the wrong shape.

**An answer is said only when it is said whole.** PACT's shapes are closed (a
part a shape does not name is refused, `Shape._read_composite`), and an
OpenAPI object allows fields it does not name unless it says
`additionalProperties: false`. `Line.whole` is false when anything below was
left out or any object is open, and `openapi.py` writes `answers-with:` only
from a whole line: a server sending one more field than the description named
would otherwise halt every run as a server that changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .importing import ImportReport
from .questions import Rejected, Shape

__all__ = ["Line", "Shapes", "kebab"]

#: Keywords that say how a value is spelled or bounded, not what it is. The
#: server still holds a value to them; PACT's shapes do not say them.
_LIMITS = frozenset({
    "pattern", "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "multipleOf", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties", "contentEncoding", "contentMediaType",
})
#: Keywords that describe or illustrate a value for a person reading the docs.
_FOR_PEOPLE = frozenset({
    "title", "description", "example", "examples", "default", "deprecated",
    "externalDocs", "xml", "discriminator", "$comment", "$schema", "$id",
})
#: The keywords that make a shape, read below.
_READ = frozenset({
    "type", "format", "enum", "const", "items", "properties", "required",
    "additionalProperties", "unevaluatedProperties", "allOf", "oneOf", "anyOf",
    "nullable", "readOnly", "writeOnly", "$ref",
})
_FORMATS = {"date": "date", "date-time": "date-and-time", "time": "time"}
_SCALARS = {"boolean": "yes-or-no", "integer": "whole-number", "number": "number", "string": "text"}
_COMPONENT = "#/components/schemas/"


def kebab(name: str) -> str:
    """`getPetById` → `get-pet-by-id`; `Pet_Status` → `pet-status`."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", str(name))
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", spaced)
    return "-".join(w for w in re.split(r"[^a-z0-9]+", spaced.lower()) if w)


@dataclass(frozen=True)
class Line:
    """One shape line, and whether it says all of what the schema says."""

    written: str
    whole: bool


class Shapes:
    """The named shapes one import makes, and the report it accounts in.

    `prefix` names a shape whose own name would read as one of PACT's words
    (`File` → `<prefix>-file`, never the plain `file` shape).
    """

    def __init__(self, document: Mapping[str, Any], report: ImportReport, prefix: str) -> None:
        self.document = document
        self.report = report
        self.prefix = prefix
        #: Every key this import saw, in the order seen (the report's `seen`).
        self.seen: dict[str, None] = {}
        #: `{shape name: {part: line}}`, for `workspace.yaml`'s `shapes:`.
        self.named: dict[str, dict[str, str]] = {}
        self._made: dict[str, Line | None] = {}  # by component pointer, or by inline place
        self._names: dict[str, str] = {}  # component pointer → shape name
        self._making: list[str] = []

    # ── the report ─────────────────────────────────────────────────────────────────────────

    def mapped(self, key: str, what: str) -> None:
        self.seen.setdefault(key)
        self.report.mapped[key] = what

    def unmapped(self, key: str, what: str) -> None:
        self.seen.setdefault(key)
        self.report.unmapped[key] = what

    def not_portable(self, key: str, why: str) -> None:
        self.seen.setdefault(key)
        self.report.not_portable[key] = why

    # ── $ref ───────────────────────────────────────────────────────────────────────────────

    def deref(self, node: Any, where: str) -> tuple[Any, str]:
        """`node` with every `$ref` followed inside this document, and where it now is.
        A reference outside the document, or to nothing, is `None` (and unmapped)."""
        for _ in range(64):
            if not (isinstance(node, Mapping) and isinstance(node.get("$ref"), str)):
                return node, where
            ref = node["$ref"]
            target = self._pointer(ref)
            if target is None:
                self.unmapped(f"{where}.$ref", f"`{ref}` is not in this document, and nothing here fetches it")
                return None, where
            node, where = target, ref
        self.unmapped(f"{where}.$ref", "a chain of references that never ends")
        return None, where

    def _pointer(self, ref: str) -> Any:
        if not ref.startswith("#/"):
            return None
        node: Any = self.document
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, Mapping) or part not in node:
                return None
            node = node[part]
        return node

    # ── shapes ─────────────────────────────────────────────────────────────────────────────

    def line(self, schema: Any, where: str, name: str) -> Line | None:
        """The shape line for `schema`, written at `where`; `name` names a shape it makes
        inline. `None`: PACT cannot say it, and the report says why."""
        if isinstance(schema, Mapping) and isinstance(schema.get("$ref"), str):
            ref = schema["$ref"]
            self._account(schema, where, keep={"$ref"})
            if ref.startswith(_COMPONENT) and self._pointer(ref) is not None:
                made = self._component(ref)
                if made is None:
                    self.unmapped(f"{where}.$ref", f"`{ref}`, which PACT cannot say (its own lines say why)")
                else:
                    self.mapped(f"{where}.$ref", f"the shape `{made.written}`")
                return made
            target, at = self.deref(schema, where)
            if target is None:
                return None
            self.mapped(f"{where}.$ref", f"what `{ref}` says")
            return self._line(target, at, name)
        return self._line(schema, where, name)

    def _component(self, ref: str) -> Line | None:
        if ref in self._made:
            return self._made[ref]
        if ref in self._making:
            self.unmapped(f"{ref} (inside itself)", "a shape that contains itself, and a PACT shape is a fixed set of parts")
            return None
        self._making.append(ref)
        made = self._line(self._pointer(ref), ref, ref[len(_COMPONENT):])
        self._making.pop()
        self._made[ref] = made
        return made

    def _line(self, schema: Any, where: str, name: str) -> Line | None:
        if not isinstance(schema, Mapping):
            self.unmapped(where, "a schema that is not a set of keywords")
            return None
        optional, schema = self._nullable(schema, where)
        made = self._plain(schema, where, name)
        if made is None:
            return None
        return Line(made.written + ", optional", made.whole) if optional else made

    def _nullable(self, schema: Mapping[str, Any], where: str) -> tuple[bool, Mapping[str, Any]]:
        """Whether `null` is allowed, and the schema without it."""
        if schema.get("nullable") is True:
            self.mapped(f"{where}.nullable", "`, optional`")
            return True, schema
        said = schema.get("type")
        if isinstance(said, list) and "null" in said and len(said) == 2:
            return True, {**schema, "type": next(t for t in said if t != "null")}
        for key in ("oneOf", "anyOf"):
            options = schema.get(key)
            if isinstance(options, list) and len(options) == 2:
                plain = [o for o in options if not (isinstance(o, Mapping) and o.get("type") == "null")]
                if len(plain) == 1:
                    self.mapped(f"{where}.{key}", "`, optional`: one shape, or nothing")
                    rest = {k: v for k, v in schema.items() if k != key}
                    return True, {**rest, "allOf": [plain[0], *rest.get("allOf", [])]}
        return False, schema

    def _plain(self, schema: Mapping[str, Any], where: str, name: str) -> Line | None:
        for key in ("oneOf", "anyOf"):
            if key in schema and not self._said(f"{where}.{key}"):
                self._account(schema, where, keep={key})
                self.unmapped(
                    f"{where}.{key}",
                    f"one of several shapes ({key}), and a PACT shape is one shape. Write it by hand as "
                    "`text` and say in the description which forms the server takes",
                )
                return None
        all_of = schema.get("allOf")
        if isinstance(all_of, list) and len(all_of) == 1 and not schema.get("properties"):
            self._account(schema, where, keep={"allOf", "type"})
            self.mapped(f"{where}.allOf", "the one shape it names")
            if "type" in schema:
                self.mapped(f"{where}.type", "the type of the one shape it names")
            return self.line(all_of[0], f"{where}.allOf[0]", name)
        if isinstance(all_of, list):
            merged = self.merged(schema, where)
            if merged is None:
                return None
            schema = merged
        said = schema.get("type")
        if isinstance(said, list):
            self._account(schema, where, keep={"type"})
            self.unmapped(f"{where}.type", f"a value of any of {said}, and a PACT shape is one shape")
            return None
        if "enum" in schema or "const" in schema:
            return self._choice(schema, where)
        if said == "array" or "items" in schema:
            return self._list(schema, where, name)
        if said == "object" or "properties" in schema:
            return self._object(schema, where, name)
        if said in _SCALARS:
            self._account(schema, where, keep={"type", "format"})
            plain = _SCALARS[said]
            fmt = schema.get("format")
            if said == "string" and fmt in _FORMATS:
                plain = _FORMATS[fmt]
                self.mapped(f"{where}.format", f"`{plain}`")
            elif fmt is not None:
                self.not_portable(
                    f"{where}.format",
                    f"`{fmt}` is how the value is written, and PACT says only that it is "
                    f"`{plain}`; the server still holds it to `{fmt}`",
                )
            self.mapped(f"{where}.type", f"`{plain}`")
            return Line(plain, True)
        self._account(schema, where)
        self.unmapped(where, "a value the description gives no shape (no `type`), so PACT cannot say what it is")
        return None

    def merged(self, schema: Mapping[str, Any], where: str) -> Mapping[str, Any] | None:
        """`allOf`'s parts as one object: their properties and `required` together."""
        properties: dict[str, Any] = dict(schema.get("properties") or {})
        required = list(schema.get("required") or ())
        closed = schema.get("additionalProperties") is False
        for i, part in enumerate(schema["allOf"]):
            found, at = self.deref(part, f"{where}.allOf[{i}]")
            if found is None:
                return None
            if isinstance(found.get("allOf"), list):
                found = self.merged(found, at)
                if found is None:
                    return None
            if not (found.get("type") == "object" or "properties" in found) or "oneOf" in found or "anyOf" in found:
                self.unmapped(f"{where}.allOf[{i}]", "a part of an `allOf` that is not an object with properties")
                return None
            kept = {"properties", "required", "type", "additionalProperties"}
            self._account(found, at, keep=kept)
            for key in kept & set(found):
                self.mapped(f"{at}.{key}", f"part of the one shape at {where}")
            properties.update(found.get("properties") or {})
            required += list(found.get("required") or ())
            closed = closed or found.get("additionalProperties") is False
        self.mapped(f"{where}.allOf", "one shape with the parts of all of them")
        merged = {k: v for k, v in schema.items() if k != "allOf"}
        merged.update({"type": "object", "properties": properties, "required": required})
        if closed:
            merged["additionalProperties"] = False
        return merged

    def _choice(self, schema: Mapping[str, Any], where: str) -> Line | None:
        key = "enum" if "enum" in schema else "const"
        values = schema["enum"] if key == "enum" else [schema["const"]]
        self._account(schema, where, keep={key, "type"})
        if "type" in schema:
            self.mapped(f"{where}.type", "the kind of its choices")
        values = values if isinstance(values, list) else []
        words = [str(v) for v in values]
        if values and all(isinstance(v, bool) for v in values):
            self.mapped(f"{where}.{key}", "`yes-or-no`")
            return Line("yes-or-no", True)
        if values and all(
            isinstance(v, (str, int, float)) and not isinstance(v, bool) and _a_plain_word(str(v)) for v in values
        ):
            self.mapped(f"{where}.{key}", "`one of ...`")
            return Line("one of " + ", ".join(words), True)
        said = schema.get("type")
        fallback = _SCALARS.get(said, "text") if isinstance(said, str) else "text"
        self.not_portable(
            f"{where}.{key}",
            f"its choices ({', '.join(words[:6])}{', ...' if len(words) > 6 else ''}) are not plain lower-case "
            f"words, which is how PACT reads a choice, so it is written `{fallback}` and the server still "
            "holds it to them",
        )
        return Line(fallback, True)

    def _list(self, schema: Mapping[str, Any], where: str, name: str) -> Line | None:
        self._account(schema, where, keep={"items", "type"})
        if "type" in schema:
            self.mapped(f"{where}.type", "`list of ...`")
        items = schema.get("items")
        if not isinstance(items, Mapping):
            self.unmapped(f"{where}.items", "a list that does not say what is in it")
            return None
        inner = self.line(items, f"{where}.items", f"{name}-item")
        if inner is None:
            self.unmapped(f"{where}.items", "a list of something PACT cannot say")
            return None
        self.mapped(f"{where}.items", "what the list holds")
        return Line("list of " + inner.written.removesuffix(", optional"), inner.whole)

    def _object(self, schema: Mapping[str, Any], where: str, name: str) -> Line | None:
        parts, whole = self.parts(schema, where, name)
        if not parts:
            self.unmapped(where, "an object with no parts PACT can say, so there is no shape to name")
            return None
        shape = self._name_for(where, name)
        self.named[shape] = parts
        return Line(shape, whole)

    def parts(self, schema: Mapping[str, Any], where: str, name: str) -> tuple[dict[str, str], bool]:
        """An object's properties as `{part: line}`, and whether they say it whole."""
        open_ = ("additionalProperties", "unevaluatedProperties")
        self._account(schema, where, keep={"properties", "required", "type", *open_})
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or ())
        whole = any(schema.get(k) is False for k in open_)
        for key in open_:
            if key not in schema:
                continue
            if schema[key] is False:
                self.mapped(f"{where}.{key}", "a closed shape, as every PACT shape is")
            else:
                self.unmapped(f"{where}.{key}", "parts by any name beside the ones it names, which a PACT shape cannot have")
        parts: dict[str, str] = {}
        for prop, sub in properties.items():
            made = self.line(sub, f"{where}.properties.{prop}", f"{name}-{kebab(prop)}")
            if made is None:
                whole = False
                continue
            whole = whole and made.whole
            one_way = isinstance(sub, Mapping) and bool(sub.get("readOnly") or sub.get("writeOnly"))
            line = made.written
            if (prop not in required or one_way) and not line.endswith(", optional"):
                line += ", optional"
            parts[str(prop)] = line
        if "properties" in schema:
            self.mapped(f"{where}.properties", "the shape's parts")
        if "required" in schema:
            self.mapped(f"{where}.required", "the parts with no `, optional`")
        if "type" in schema:
            self.mapped(f"{where}.type", "a shape with parts")
        return parts, whole

    def _name_for(self, where: str, name: str) -> str:
        if where in self._names:
            return self._names[where]
        shape = kebab(name) or "part"
        try:
            Shape.parse(shape)
            a_word = True
        except Rejected:
            a_word = shape.startswith(("list-of", "one-of", "either"))
        if a_word:
            shape = f"{self.prefix}-{shape}"
        if shape in self.named:
            n = 2
            while f"{shape}-{n}" in self.named:
                n += 1
            shape = f"{shape}-{n}"
        self._names[where] = shape
        return shape

    def _said(self, key: str) -> bool:
        r = self.report
        return key in r.mapped or key in r.unmapped or key in r.not_portable

    def _account(self, schema: Mapping[str, Any], where: str, keep: frozenset[str] | set[str] = frozenset()) -> None:
        """Every keyword of `schema` is seen; each the shape does not carry goes in its bucket.
        A kept one is the caller's to account for, and is a silent drop until it does."""
        for key in schema:
            at = f"{where}.{key}"
            self.seen.setdefault(at)
            if key in keep or self._said(at):
                continue
            if key in _LIMITS or key == "format":
                self.not_portable(at, "how the value is bounded or written, which a PACT shape does not say; the server still holds it")
            elif key in _FOR_PEOPLE:
                self.not_portable(at, "written for a person reading the description; a shape line carries none")
            elif key in ("readOnly", "writeOnly"):
                self.mapped(at, "`, optional`: the server sends it or takes it, not both")
            elif key in _READ:
                self.unmapped(at, f"`{key}` beside a shape it does not belong to, so nothing reads it")
            else:
                self.unmapped(at, f"`{key}`, which this importer does not read")


def _a_plain_word(word: str) -> bool:
    """A choice PACT reads back as written: lower case, single spaces, no `,` or ` or `."""
    return bool(word) and word == " ".join(word.lower().split()) and "," not in word and " or " not in f" {word} "
