"""The operations of one OpenAPI description, each read into one PACT tool file
(`openapi.py` says what each becomes; `openapi_shapes.py` reads their schemas)."""

from __future__ import annotations

import re
from typing import Any, Mapping

import yaml

from .openapi_shapes import Shapes, kebab

__all__ = ["READS_ONLY", "Operations", "TOP"]

#: The extension that declares an operation's effect.
READS_ONLY = "x-pact-reads-only"
_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
_PACT_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
_IN_THE_QUERY = frozenset({"get", "delete"})
TOP: Mapping[str, tuple[str, str]] = {
    "openapi": ("mapped", "read as the version of OpenAPI it is written in"),
    "info": ("mapped", "the API's name, which `url:` begins with, and each tool file's first line"),
    "servers": ("mapped", "the address the host binds the API's name to (the report says which)"),
    "paths": ("mapped", "one tool file per operation"),
    "components": ("mapped", "the shapes, parameters, bodies, answers and credentials the operations refer to"),
    "security": ("mapped", "each tool file's *Auth* comment"),
    "tags": ("not_portable", "how the description's pages are grouped; a tool file stands on its own"),
    "externalDocs": ("not_portable", "where people read more; nothing a run uses"),
    "jsonSchemaDialect": ("not_portable", "which JSON Schema the shapes are written in; PACT reads them into its own"),
    "webhooks": ("unmapped", "calls the API makes to you, not calls you make; a port receives those"),
}
_OPERATION: Mapping[str, tuple[str, str]] = {
    "operationId": ("mapped", "the tool file's name"),
    "summary": ("mapped", "the tool's `description:`"),
    "description": ("mapped", "the action's `description:`"),
    "parameters": ("mapped", "`takes:`, one line each (each parameter says what it became)"),
    "requestBody": ("mapped", "`takes:`, one line per part of the body (the body says what it became)"),
    "responses": ("mapped", "`answers-with:` from the success answer (each answer says what it became)"),
    "security": ("mapped", "the file's *Auth* comment"),
    "deprecated": ("mapped", "the file's *Deprecated* comment"),
    READS_ONLY: ("mapped", "`reads-only:`"),
    "tags": ("not_portable", "how the description's pages are grouped; a tool file stands on its own"),
    "externalDocs": ("not_portable", "where people read more; nothing a run uses"),
    "servers": ("not_portable", "an address for this operation alone; the host binds one address per API name"),
    "callbacks": ("unmapped", "calls the API makes back to you later; a port receives those"),
}
_PARAMETER: Mapping[str, tuple[str, str]] = {
    "name": ("mapped", "the argument's name, as the server spells it"),
    "in": ("mapped", "where the argument goes"),
    "required": ("mapped", "a line with no `, optional`"),
    "schema": ("mapped", "the argument's shape"),
    "content": ("mapped", "the argument's shape"),
    "description": ("mapped", "the action's `description:`, which names each argument"),
    "deprecated": ("not_portable", "written for a person reading the description"),
    "example": ("not_portable", "written for a person reading the description"),
    "examples": ("not_portable", "written for a person reading the description"),
    "style": ("mapped", "how the value is spelled in the address (the parameter says what it became)"),
    "explode": ("mapped", "how a list is spelled in the address (the parameter says what it became)"),
    "allowReserved": ("not_portable", "whether `/`, `?` and the like go unescaped; the runtime escapes them, which a server reads the same"),
    "allowEmptyValue": ("not_portable", "whether an empty value may be sent, which OpenAPI deprecates; the runtime sends what the call gives"),
}
#: How a value in the address is spelled when the description says nothing, which is how a `url:`
#: tool sends one: a list as one pair per item in the query (`tags=a&tags=b`), its items joined
#: by `,` in the path (`style`, and `explode` true for `form` only).
_DEFAULT_STYLE = {"query": "form", "path": "simple"}
#: A query list written as one value, its items joined by this (`explode: false`).
_JOINED = {"form": ",", "spaceDelimited": " ", "pipeDelimited": "|"}


class Operations:
    """The operations of one description, each read into one tool file."""

    def __init__(self, document: Mapping[str, Any], shapes: Shapes, api: str, title: str) -> None:
        self.document, self.shapes, self.api, self.title = document, shapes, api, title
        self.files: dict[str, str] = {}
        self.lines: list[str] = []  # every shape line written, so only shapes in use are kept
        self.needs_a_look: list[str] = []
        self.owed: list[str] = []
        self.credentials: list[str] = []
        self.how: dict[str, str] = {}

    def schemes(self) -> None:
        components = self.document.get("components") or {}
        for name, scheme in (components.get("securitySchemes") or {}).items():
            found, _ = self.shapes.deref(scheme, f"components.securitySchemes.{name}")
            self.how[str(name)] = _how(found if isinstance(found, Mapping) else {})
            self.shapes.mapped(
                f"components.securitySchemes.{name}",
                f"sent by the client the host binds `{self.api}` to ({self.how[str(name)]})",
            )

    def path(self, path: str, item: Any) -> None:
        item, _ = self.shapes.deref(item, path)
        if not isinstance(item, Mapping):
            return
        shared = item.get("parameters") or []
        for key in item:
            where = f"{path} {key}"
            if key in _METHODS:
                self.operation(key, path, item[key], shared)
            elif key == "parameters":
                self.shapes.mapped(where, "the parameters of every operation on this path")
            elif key in ("summary", "description", "servers"):
                self.shapes.not_portable(where, "said of the path; each operation's own words and address are used")
            else:
                self.shapes.unmapped(where, f"`{key}`, which this importer does not read")

    def operation(self, method: str, path: str, op: Any, shared: list[Any]) -> None:
        where = f"{method.upper()} {path}"
        if method not in _PACT_METHODS:
            self.shapes.not_portable(where, f"a `{method}` call; PACT's `method:` is get, post, put, patch or delete")
            return
        if not isinstance(op, Mapping):
            self.shapes.unmapped(where, "an operation that is not a set of keys")
            return
        name = self._name(op, method, path)
        file = f"tools/{name}.yaml"
        self.shapes.mapped(where, file)
        for key in op:
            bucket, what = _OPERATION.get(key, ("unmapped", f"`{key}`, which this importer does not read"))
            getattr(self.shapes, bucket)(f"{where} {key}", what)
        takes, notes, query = self._parameters(where, method, op, shared, name)
        for blank in re.findall(r"\{([^{}]+)\}", path):
            if blank not in takes:  # a part of the path no parameter declares is still the call's
                takes[blank] = "text"
                self.shapes.unmapped(f"{where} path {{{blank}}}", "a part of the path no parameter declares; written `text`")
        self._body(where, method, op, name, takes)
        answers = self._answer(where, op, name)
        action: dict[str, Any] = {}
        summary = " ".join(str(op.get("summary") or "").split())
        long = str(op.get("description") or "").strip()
        words = long if long and long != summary else ""
        if notes:
            words = (words + "\n\n" if words else "") + "Arguments:\n" + "\n".join(f"- {n}" for n in notes)
        if words:
            action["description"] = words
        if takes:
            action["takes"] = takes
        if answers:
            action["answers-with"] = answers
        self.lines += [*takes.values(), *answers.values()]
        comments = [f"{where} in {self.title}, imported from its OpenAPI description."]
        declared = op.get(READS_ONLY)
        if isinstance(declared, bool):
            action["reads-only"] = declared
        else:
            self.needs_a_look.append(name)
            comments.append(
                "Needs a look: the description does not say whether this only looks things up. Until "
                f"a person writes `reads-only: yes` or `reads-only: no` under `{method}:`, it is a write "
                "that cannot be undone."
            )
            self.owed.append(f"{file}: say whether it only reads (`reads-only: yes`) or changes something")
        comments += self._auth(op)
        if op.get("deprecated") is True:
            comments.append("Deprecated: the API says this operation is going away.")
        tool = {
            "description": summary or _first_line(long) or f"{where} in {self.title}.",
            "url": f"{self.api}{path}" + ("?" + "&".join(f"{a}={{{a}}}" for a in query) if query else ""),
            "method": method,
            "actions": {method: action},
        }
        body = yaml.dump(tool, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)
        self.files[file] = "".join(f"# {c}\n" for c in _wrapped(comments)) + "\n" + body

    def _name(self, op: Mapping[str, Any], method: str, path: str) -> str:
        name = kebab(str(op.get("operationId") or "")) or kebab(f"{method} {path}") or method
        # A model is offered `<tool>_<method>`, and a provider takes a tool name of 64 at most.
        name = name[:56].rstrip("-")
        taken = {f[len("tools/"):-len(".yaml")] for f in self.files}
        if name in taken:
            n = 2
            while f"{name}-{n}" in taken:
                n += 1
            name = f"{name}-{n}"
        return name

    def _parameters(
        self, where: str, method: str, op: Mapping[str, Any], shared: list[Any], name: str
    ) -> tuple[dict[str, str], list[str], list[str]]:
        found: dict[tuple[str, str], tuple[Mapping[str, Any], str]] = {}
        for i, written in enumerate([*shared, *(op.get("parameters") or [])]):
            param, at = self.shapes.deref(written, f"{where} parameters[{i}]")
            if isinstance(param, Mapping):
                found[(str(param.get("name")), str(param.get("in")))] = (param, at)
        takes: dict[str, str] = {}
        notes: list[str] = []
        query: list[str] = []
        for (arg, place), (param, at) in found.items():
            key = f"{where} parameter {arg}"
            for k in param:
                bucket, what = _PARAMETER.get(k, ("unmapped", f"`{k}`, which this importer does not read"))
                getattr(self.shapes, bucket)(f"{at} {k}", what)
            required = place == "path" or param.get("required") is True
            if place in ("header", "cookie"):
                self.shapes.not_portable(key, f"a {place} value; the client the host binds sets those, not the model")
                continue
            if place not in ("path", "query"):
                self.shapes.unmapped(key, f"a value sent `in: {place}`, which OpenAPI does not define")
                continue
            line = self.shapes.line(_schema_of(param), f"{at} schema", f"{name}-{kebab(arg)}")
            # A value in the address is text on the wire, so one whose shape PACT cannot say
            # (a `oneOf` of three kinds of id) is still offered, as `text`: the server holds it.
            written = "text" if line is None else line.written
            if not required and not written.endswith(", optional"):
                written += ", optional"
            written, joined, cannot = self._spelling(param, place, written)
            takes[arg] = written
            if joined:
                notes.append(f"`{arg}`: the values joined by `{joined}`")
            if cannot:
                self.shapes.unmapped(key, f"`takes: {arg}: {written}`, but it is {cannot}")
                self.owed.append(f"tools/{name}.yaml: `{arg}` is {cannot}; write how the server reads it")
            elif place == "query" and method not in _IN_THE_QUERY:
                query.append(arg)  # a body goes with it, so it is named in the address
                self.shapes.mapped(key, f"`takes: {arg}: {written}`, and `{arg}={{{arg}}}` in the address's query")
            elif joined:
                self.shapes.mapped(key, f"`takes: {arg}: {written}`: a list the server reads as one value, its items joined by `{joined}`")
            elif line is None:
                self.shapes.mapped(key, f"`takes: {arg}: text`: its shape is one PACT cannot say (its schema says why), and a value in the address is text")
            else:
                self.shapes.mapped(key, f"`takes: {arg}: {written}`")
            if said := " ".join(str(param.get("description") or "").split()):
                notes.append(f"`{arg}`: {said}")
        return takes, notes, query

    def _spelling(self, param: Mapping[str, Any], place: str, written: str) -> tuple[str, str, str]:
        """A value in the address as a `url:` tool sends it (`_DEFAULT_STYLE`): `written` as it is;
        a query list the server reads as one value as `text`, and what joins its items; or, when
        the tool cannot spell the value as the description does, what the description wants."""
        style = str(param.get("style", _DEFAULT_STYLE[place]))
        explode = param.get("explode", style == "form") is True
        base = written.removesuffix(", optional")
        listed = base.startswith("list of ")
        if base.removeprefix("list of ") in self.shapes.named:
            return written, "", f"an object in the address, which a server reads part by part (`style: {style}`) and a `url:` tool sends as its JSON text"
        if not listed:
            plain = style == _DEFAULT_STYLE[place] or (place == "query" and style in _JOINED)
            return written, "", "" if plain else f"spelled `style: {style}`, which a `url:` tool does not write"
        if style == _DEFAULT_STYLE[place] and (explode or place == "path"):  # `simple`: `,` either way
            return written, "", ""
        if place == "query" and not explode and style in _JOINED:
            return "text" + (", optional" if written.endswith(", optional") else ""), _JOINED[style], ""
        return written, "", f"a list spelled `style: {style}, explode: {str(explode).lower()}`, which a `url:` tool does not write"

    def _body(self, where: str, method: str, op: Mapping[str, Any], name: str, takes: dict[str, str]) -> None:
        if "requestBody" not in op:
            return
        key = f"{where} body"
        body, at = self.shapes.deref(op["requestBody"], key)
        if not isinstance(body, Mapping):
            return
        for k in body:
            if k not in ("content", "required", "description"):
                self.shapes.unmapped(f"{at} {k}", f"`{k}`, which this importer does not read")
        if "required" in body:
            self.shapes.mapped(f"{at} required", "whether the parts keep their `, optional`")
        if "description" in body:
            self.shapes.not_portable(f"{at} description", "written for a person reading the description")
        content = body.get("content") or {}
        media = _json(content)
        self.shapes.seen.setdefault(f"{at} content")
        if method in _IN_THE_QUERY or media is None:
            why = (
                f"a body on a `{method}`, whose arguments a `url:` tool sends in the query"
                if media is not None
                else f"a body sent as {', '.join(content) or 'nothing'}, and a `url:` tool sends JSON"
            )
            self.shapes.unmapped(f"{at} content", why)
            self.owed.append(f"tools/{name}.yaml: the body ({why}) is not carried; write its arguments by hand")
            return
        self._media(f"{at} content", content, media)
        self.shapes.mapped(f"{at} content", f"`takes:`, one line per part of the {media} body")
        schema, place = self.shapes.deref((content[media] or {}).get("schema"), f"{at} content {media} schema")
        named = _component_name(content[media] or {}) or name
        obj = self.shapes.merged(schema, place) if isinstance(schema, Mapping) and "allOf" in schema else schema
        if not (isinstance(obj, Mapping) and (obj.get("type") == "object" or "properties" in obj)):
            self.shapes.unmapped(key, "a body that is not an object with parts; `takes:` names each argument")
            self.owed.append(f"tools/{name}.yaml: the body is not an object with parts; write its arguments by hand")
            return
        parts, _ = self.shapes.parts(obj, place, named)
        for part, line in parts.items():
            if part in takes:
                self.shapes.unmapped(f"{key} {part}", "a part with the name of a parameter, so it cannot be an argument too")
                continue
            if body.get("required") is not True and not line.endswith(", optional"):
                line += ", optional"
            takes[part] = line
        self.shapes.mapped(key, f"`takes:`, {len(parts)} line(s)")

    def _answer(self, where: str, op: Mapping[str, Any], name: str) -> dict[str, str]:
        responses = op.get("responses") if isinstance(op.get("responses"), Mapping) else {}
        success = sorted(str(c) for c in responses if str(c).startswith("2"))
        for code in responses:
            if str(code) not in success[:1]:
                self.shapes.not_portable(
                    f"{where} answer {code}", "what the server says when the call does not succeed; the model is shown its words"
                )
        if not success:
            return {}
        key = f"{where} answer {success[0]}"
        found = responses.get(success[0], responses.get(int(success[0]) if success[0].isdigit() else success[0]))
        answer, at = self.shapes.deref(found, key)
        answer = answer if isinstance(answer, Mapping) else {}
        for k in answer:
            if k == "description":
                self.shapes.not_portable(f"{at} {k}", "written for a person reading the description")
            elif k == "headers":
                self.shapes.not_portable(f"{at} {k}", "what the server sends beside its answer; the model is shown the answer")
            elif k != "content":
                self.shapes.unmapped(f"{at} {k}", f"`{k}`, which this importer does not read")
        content = answer.get("content") or {}
        media = _json(content)
        self._media(f"{at} content", content, media)
        if media is None:
            said = f"answers as {', '.join(content)}" if content else "answers with nothing"
            self.shapes.mapped(key, f"no `answers-with:`: it {said}, so there is nothing to hold it to")
            return {}
        schema, place = self.shapes.deref((content[media] or {}).get("schema"), f"{at} {media} schema")
        named = _component_name(content[media] or {}) or f"{name}-answer"
        obj = self.shapes.merged(schema, place) if isinstance(schema, Mapping) and "allOf" in schema else schema
        if not (isinstance(obj, Mapping) and (obj.get("type") == "object" or "properties" in obj)):
            self.shapes.line(schema, place, named)  # its keywords, accounted
            self.shapes.unmapped(key, "an answer that is not an object with parts, which `answers-with:` names; it is not checked")
            return {}
        parts, whole = self.shapes.parts(obj, place, named)
        if not whole or not parts:
            self.shapes.unmapped(
                key,
                "an answer PACT cannot say whole (it may carry parts the description does not name, or "
                "parts PACT cannot say), so no `answers-with:` holds it; write one by hand once you know every part",
            )
            return {}
        self.shapes.mapped(key, "`answers-with:`")
        return parts

    def _media(self, where: str, content: Mapping[str, Any], media: str | None) -> None:
        """The other ways a body or an answer is written, and what the JSON one says beside its
        schema, accounted for."""
        for other, said in content.items():
            if other != media:
                self.shapes.not_portable(f"{where} {other}", f"the same thing written as {other}; JSON is what a `url:` tool sends and reads")
                continue
            for k in said or {}:
                if k != "schema":
                    self.shapes.not_portable(f"{where} {other} {k}", "examples and encodings, written for a person reading the description")

    def _auth(self, op: Mapping[str, Any]) -> list[str]:
        needed = op.get("security", self.document.get("security")) or []
        names = sorted({str(n) for req in needed if isinstance(req, Mapping) for n in req})
        if not names:
            return []
        said = "; or ".join(f"{n} ({self.how.get(n, 'a scheme the description does not define')})" for n in names)
        for n in names:
            needed = f"give the client bound to `{self.api}` the `{n}` credential: {self.how.get(n, '?')}"
            if needed not in self.credentials:
                self.credentials.append(needed)
        return [f"Auth: {said}, sent by the client the host binds `{self.api}` to; no secret is in this file."]


def _how(scheme: Mapping[str, Any]) -> str:
    kind = scheme.get("type")
    if kind == "apiKey":
        return f"an API key in the {scheme.get('in', '?')} value `{scheme.get('name', '?')}`"
    if kind == "http":
        return f"HTTP `{scheme.get('scheme', '?')}` authentication"
    if kind == "oauth2":
        return f"an OAuth 2 token, from its {' or '.join(scheme.get('flows') or {}) or 'unnamed'} flow"
    if kind == "openIdConnect":
        return "an OpenID Connect token"
    return f"a `{kind}` credential"


class _Dumper(yaml.SafeDumper):
    """YAML as a person reads it: a description of several lines as a block of lines."""


_Dumper.add_representer(
    str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None)
)


def _schema_of(param: Mapping[str, Any]) -> Any:
    if "schema" in param:
        return param["schema"]
    content = param.get("content") or {}
    first = next(iter(content.values()), None) if isinstance(content, Mapping) else None
    return (first or {}).get("schema") if isinstance(first, Mapping) else None


def _json(content: Any) -> str | None:
    if not isinstance(content, Mapping):
        return None
    for media in content:
        base = str(media).split(";")[0].strip().lower()
        if base == "application/json" or base.endswith("+json") or base == "*/*":
            return str(media)
    return None


def _component_name(media: Mapping[str, Any]) -> str | None:
    ref = (media.get("schema") or {}).get("$ref") if isinstance(media.get("schema"), Mapping) else None
    return ref.rsplit("/", 1)[-1] if isinstance(ref, str) and ref.startswith("#/components/schemas/") else None


def _first_line(text: str) -> str:
    first = text.strip().split("\n\n", 1)[0]
    return " ".join(first.split())[:200]


def _wrapped(lines: list[str], width: int = 96) -> list[str]:
    out: list[str] = []
    for line in lines:
        words, now = line.split(), ""
        for w in words:
            if now and len(now) + 1 + len(w) > width:
                out.append(now)
                now = w
            else:
                now = f"{now} {w}" if now else w
        out.append(now)
    return out


