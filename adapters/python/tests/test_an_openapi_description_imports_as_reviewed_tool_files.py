"""`pact-import --as openapi`: an OpenAPI description as one reviewed tool file per
operation (decision P10; `pact_adapters/openapi.py`).

Three things are held here, each on the ten public descriptions under
`tests/trees/openapi/` and on small descriptions written to make one point:

* **every written file passes `pact check`**, in a tree whose one agent uses
  every imported tool, so each tool is checked as something an agent reaches;
* **nothing is guessed about an effect**: an operation whose description does
  not declare it (`x-pact-reads-only`) gets no `reads-only:` and a *Needs a
  look* line, so it stays a write that cannot be undone until a person decides;
* **no silent drops** (S1): every key the import read is mapped, not portable
  or unmapped, and one test breaks the importer to show the count can fail.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import openapi_shapes  # noqa: E402
from pact_adapters.importing import main as pact_import  # noqa: E402
from pact_adapters.openapi import NotImported, from_openapi, write_into  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DESCRIPTIONS = sorted(p for p in (REPO / "tests" / "trees" / "openapi").glob("*/openapi.*"))
PACT_BIN = REPO / "target" / "debug" / "pact"
WORKSPACE = (
    "name: imported\n"
    "workspace-id: 01JC5S8W0G7QK4T2H9RA3XB6ND\n"
    "description: Tools imported from an OpenAPI description.\n"
    "owner: platform\n"
    "# Nothing here talks to anything outside this box.\n"
    "allow-egress: []\n"
)


def _tree(at: Path) -> Path:
    at.mkdir(parents=True, exist_ok=True)
    (at / "workspace.yaml").write_text(WORKSPACE)
    return at


def _check(tree: Path) -> subprocess.CompletedProcess[str]:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    return subprocess.run([str(PACT_BIN), "check", str(tree)], capture_output=True, text=True)


def _api(paths: dict[str, Any], **more: Any) -> dict[str, Any]:
    return {"openapi": "3.1.0", "info": {"title": "Shop", "version": "1"}, "paths": paths, **more}


def _tool(imported: Any, name: str) -> dict[str, Any]:
    return yaml.safe_load(imported.files[f"tools/{name}.yaml"])


# ── the ten public descriptions ──────────────────────────────────────────────────────────────


def test_there_are_ten_descriptions_each_with_its_licence_recorded() -> None:
    assert len(DESCRIPTIONS) == 10, DESCRIPTIONS
    listed = (REPO / "tests" / "trees" / "openapi" / "README.md").read_text()
    for description in DESCRIPTIONS:
        assert f"`{description.parent.name}`" in listed, f"{description.parent.name} has no licence row"


@pytest.mark.parametrize("description", DESCRIPTIONS, ids=lambda p: p.parent.name)
def test_a_public_description_imports_into_files_pact_check_accepts(description: Path, tmp_path: Path) -> None:
    document = yaml.safe_load(description.read_text())
    imported = from_openapi(document)
    report = imported.report
    assert report.silent_drops == (), report.silent_drops[:20]

    operations = [
        f"{m.upper()} {p}" for p, item in document["paths"].items() for m in item
        if m in ("get", "post", "put", "patch", "delete")
    ]  # fmt: skip
    assert len(imported.files) == len(operations)
    assert all(report.mapped.get(op, "").startswith("tools/") for op in operations)

    tree = _tree(tmp_path / "tree")
    written = write_into(tree, imported)
    assert set(imported.files) <= set(written)
    tools = sorted(p.stem for p in (tree / "tools").glob("*.yaml"))
    desk = {"description": "Uses every imported tool.", "instructions": "Answer with the tools.", "uses": tools}
    (tree / "agents" / "desk").mkdir(parents=True)
    (tree / "agents" / "desk" / "agent.yaml").write_text(yaml.safe_dump(desk))
    checked = _check(tree)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "error" not in checked.stdout.lower().split("ok —")[0], checked.stdout

    # Not one of the ten declares its effects, so every operation needs a look.
    assert sorted(imported.needs_a_look) == tools
    for name in tools:
        text = (tree / "tools" / f"{name}.yaml").read_text()
        assert "# Needs a look:" in text, name
        (action,) = yaml.safe_load(text)["actions"].values()
        assert "reads-only" not in action, name

    # Importing again changes nothing and writes nothing.
    assert write_into(tree, from_openapi(document)) == []


# ── effects: declared, or a look ─────────────────────────────────────────────────────────────


def test_a_declared_effect_is_written_and_an_undeclared_one_is_marked() -> None:
    imported = from_openapi(_api({
        "/orders/{id}": {
            "get": {"operationId": "getOrder", "x-pact-reads-only": True,
                    "parameters": [{"name": "id", "in": "path", "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "ok"}}},
            "delete": {"operationId": "cancelOrder", "x-pact-reads-only": False,
                       "parameters": [{"name": "id", "in": "path", "schema": {"type": "string"}}],
                       "responses": {"204": {"description": "gone"}}},
        },
        "/orders": {"get": {"operationId": "listOrders", "responses": {"200": {"description": "ok"}}}},
    }))  # fmt: skip
    assert _tool(imported, "get-order")["actions"]["get"]["reads-only"] is True
    assert _tool(imported, "cancel-order")["actions"]["delete"]["reads-only"] is False
    assert "reads-only" not in (_tool(imported, "list-orders")["actions"]["get"] or {})
    assert imported.needs_a_look == ("list-orders",)
    assert "# Needs a look:" in imported.files["tools/list-orders.yaml"]
    assert "Needs a look" not in imported.files["tools/get-order.yaml"]
    assert any("list-orders.yaml: say whether it only reads" in s for s in imported.report.still_to_write)


# ── where arguments go ───────────────────────────────────────────────────────────────────────


def test_path_query_body_and_header_values_each_go_where_a_url_tool_sends_them() -> None:
    imported = from_openapi(_api({
        "/pets/{petId}": {
            "parameters": [{"name": "petId", "in": "path", "required": True, "schema": {"type": "integer"}}],
            "post": {
                "operationId": "renamePet",
                "parameters": [
                    {"name": "notify", "in": "query", "schema": {"type": "boolean"}},
                    {"name": "X-Trace", "in": "header", "schema": {"type": "string"}},
                ],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object", "required": ["name"],
                    "properties": {"name": {"type": "string", "maxLength": 40}, "born": {"type": "string", "format": "date"}},
                }}}},
                "responses": {"200": {"description": "ok"}},
            },
            "get": {"operationId": "getPet", "parameters": [{"name": "fields", "in": "query", "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "ok"}}},
        },
    }))  # fmt: skip
    rename = _tool(imported, "rename-pet")
    assert rename["url"] == "shop/pets/{petId}?notify={notify}"
    assert rename["actions"]["post"]["takes"] == {
        "petId": "whole-number", "notify": "yes-or-no, optional", "name": "text", "born": "date, optional",
    }  # fmt: skip
    assert "X-Trace" not in rename["actions"]["post"]["takes"]
    assert "header" in imported.report.not_portable["POST /pets/{petId} parameter X-Trace"]
    assert "maxLength" in next(k for k in imported.report.not_portable if k.endswith("name.maxLength"))
    get = _tool(imported, "get-pet")
    assert get["url"] == "shop/pets/{petId}", "a get sends its other arguments in the query by itself"
    assert get["actions"]["get"]["takes"] == {"petId": "whole-number", "fields": "text, optional"}


def test_a_list_in_the_address_is_written_as_the_server_reads_it() -> None:
    """A `url:` tool sends a list as OpenAPI does by default: one pair per item in the query, the
    items joined by `,` in the path. A query list the server reads as one value is `text`, with
    what joins it; a spelling the tool cannot write is reported and owed, never sent wrong silently."""
    listed = {"type": "array", "items": {"type": "string"}}
    imported = from_openapi(_api({
        "/pets/{ids}": {"get": {"operationId": "findPets", "parameters": [
            {"name": "ids", "in": "path", "required": True, "schema": listed},
            {"name": "tags", "in": "query", "schema": listed},
            {"name": "zone", "in": "query", "style": "form", "explode": True, "schema": listed},
            {"name": "status", "in": "query", "explode": False, "schema": listed},
            {"name": "codes", "in": "query", "style": "pipeDelimited", "explode": False, "schema": listed},
            {"name": "filter", "in": "query", "style": "deepObject", "schema": {"type": "object", "properties": {"k": {"type": "string"}}}},
            {"name": "sort", "in": "query", "style": "spaceDelimited", "explode": True, "schema": listed},
        ], "responses": {"200": {"description": "ok"}}}},
        "/at/{when}": {"get": {"operationId": "at", "parameters": [
            {"name": "when", "in": "path", "required": True, "style": "matrix", "schema": {"type": "string"}},
        ], "responses": {"200": {"description": "ok"}}}},
    }))  # fmt: skip
    find = _tool(imported, "find-pets")["actions"]["get"]
    assert find["takes"]["ids"] == "list of text"
    assert find["takes"]["tags"] == find["takes"]["zone"] == "list of text, optional", "repeated keys"
    assert find["takes"]["status"] == find["takes"]["codes"] == "text, optional"
    assert "`status`: the values joined by `,`" in find["description"]
    assert "`codes`: the values joined by `|`" in find["description"]
    unmapped, owed = imported.report.unmapped, imported.report.still_to_write
    for arg in ("filter", "sort"):
        assert f"GET /pets/{{ids}} parameter {arg}" in unmapped, arg
        assert any(f"`{arg}` is" in line for line in owed), arg
    assert "`style: matrix`" in unmapped["GET /at/{when} parameter when"]
    assert "style" not in str(imported.report.not_portable), "a spelling is not something PACT has no home for"
    assert imported.report.silent_drops == ()


def test_a_path_blank_no_parameter_declares_is_still_an_argument_and_a_name_fits_a_provider() -> None:
    long = "a" + "VeryLongName" * 8
    imported = from_openapi(_api({"/pets/{id}": {"delete": {"operationId": long, "responses": {"204": {"description": "gone"}}}}}))
    ((file, text),) = imported.files.items()
    tool = yaml.safe_load(text)
    assert tool["actions"]["delete"]["takes"] == {"id": "text"}
    assert "no parameter declares" in imported.report.unmapped["DELETE /pets/{id} path {id}"]
    name = file.removeprefix("tools/").removesuffix(".yaml")
    assert len(f"{name}_delete") <= 64, name


def test_auth_is_named_never_written_and_left_to_the_host() -> None:
    imported = from_openapi(_api(
        {"/me": {"get": {"operationId": "me", "responses": {"200": {"description": "ok"}}}}},
        security=[{"key": []}],
        components={"securitySchemes": {"key": {"type": "apiKey", "in": "header", "name": "X-Api-Key"}}},
    ))  # fmt: skip
    text = imported.files["tools/me.yaml"]
    assert "# Auth: key (an API key in the header value `X-Api-Key`)" in text
    tool = yaml.safe_load(text)
    assert "auth" not in tool and "X-Api-Key" not in yaml.safe_dump(tool)
    assert imported.report.still_to_write[0].startswith("bind `shop` to the API's address")
    assert any("`key` credential" in s for s in imported.report.still_to_write)


# ── shapes ───────────────────────────────────────────────────────────────────────────────────


def _shapes_of(schema: dict[str, Any], **components: Any) -> tuple[Any, Any]:
    document = _api({}, components={"schemas": components})
    from pact_adapters.importing import ImportReport

    shapes = openapi_shapes.Shapes(document, ImportReport(kind="test"), "shop")
    return shapes.line(schema, "here", "thing"), shapes


def test_json_schema_words_become_pact_shape_words() -> None:
    cases = {
        "date-and-time": {"type": "string", "format": "date-time"},
        "whole-number, optional": {"type": ["integer", "null"]},
        "text, optional": {"type": "string", "nullable": True},
        "one of small, large": {"enum": ["small", "large"]},
        "list of number": {"type": "array", "items": {"type": "number"}},
        "yes-or-no": {"type": "boolean"},
    }
    for line, schema in cases.items():
        made, _ = _shapes_of(schema)
        assert made is not None and made.written == line, (schema, made)


def test_an_object_is_a_named_shape_and_allof_is_one_shape() -> None:
    made, shapes = _shapes_of(
        {"type": "array", "items": {"$ref": "#/components/schemas/Pet"}},
        Pet={"allOf": [{"$ref": "#/components/schemas/Named"}, {"type": "object", "properties": {"age": {"type": "integer"}}}]},
        Named={"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}},
    )  # fmt: skip
    assert made.written == "list of pet"
    assert shapes.named["pet"] == {"name": "text", "age": "whole-number, optional"}


def test_what_pact_cannot_say_is_named_and_left_out_never_flattened() -> None:
    made, shapes = _shapes_of({"oneOf": [{"type": "string"}, {"type": "integer"}]})
    assert made is None
    assert "one of several shapes" in shapes.report.unmapped["here.oneOf"]
    made, shapes = _shapes_of(
        {"$ref": "#/components/schemas/Node"},
        Node={"type": "object", "properties": {"label": {"type": "string"}, "children": {"type": "array", "items": {"$ref": "#/components/schemas/Node"}}}},
    )  # fmt: skip
    assert shapes.named[made.written] == {"label": "text, optional"}, "the part that refers to itself is left out"
    assert any("contains itself" in why for why in shapes.report.unmapped.values())
    made, shapes = _shapes_of({"type": "string", "enum": ["Small", "LARGE"]})
    assert made.written == "text", "choices PACT would read in lower case are not offered as choices"
    assert "lower-case" in shapes.report.not_portable["here.enum"]


def test_a_shape_named_like_one_of_pacts_words_is_given_the_apis_name() -> None:
    made, shapes = _shapes_of({"$ref": "#/components/schemas/File"}, File={"type": "object", "properties": {"id": {"type": "string"}}})
    assert made.written == "shop-file" and "shop-file" in shapes.named


def test_an_answer_is_written_only_when_pact_can_say_all_of_it() -> None:
    def answering(schema: dict[str, Any]) -> dict[str, Any]:
        imported = from_openapi(_api({"/x": {"get": {"operationId": "x", "x-pact-reads-only": True, "responses": {
            "200": {"description": "ok", "content": {"application/json": {"schema": schema}}}}}}}))  # fmt: skip
        return _tool(imported, "x")["actions"]["get"]

    closed = {"type": "object", "additionalProperties": False, "required": ["id"], "properties": {"id": {"type": "string"}}}
    assert answering(closed)["answers-with"] == {"id": "text"}
    opened = {**closed, "additionalProperties": True}
    assert "answers-with" not in answering(opened), "an open object may carry parts a closed shape refuses"
    assert "answers-with" not in answering({"type": "array", "items": closed})


# ── writing into a tree ──────────────────────────────────────────────────────────────────────


def test_named_shapes_are_added_to_workspace_yaml_keeping_every_line_written(tmp_path: Path) -> None:
    tree = _tree(tmp_path / "t")
    (tree / "workspace.yaml").write_text(WORKSPACE + "\nshapes:\n  # kept\n  money-line:\n    amount: money\n")
    imported = from_openapi(_api({"/pets": {"post": {"operationId": "addPet", "requestBody": {"content": {"application/json": {
        "schema": {"type": "object", "properties": {"owner": {"type": "object", "properties": {"name": {"type": "string"}}}}}}}},
        "responses": {"201": {"description": "made"}}}}}))  # fmt: skip
    assert write_into(tree, imported) == ["workspace.yaml", "tools/add-pet.yaml"]
    text = (tree / "workspace.yaml").read_text()
    assert text.startswith(WORKSPACE) and "  # kept\n" in text
    assert yaml.safe_load(text)["shapes"] == {"money-line": {"amount": "money"}, "add-pet-owner": {"name": "text, optional"}}
    assert _check(tree).returncode == 0, _check(tree).stdout


def test_a_file_already_there_with_other_words_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    tree = _tree(tmp_path / "t")
    (tree / "tools").mkdir()
    (tree / "tools" / "me.yaml").write_text("description: Mine.\nsays: Hello.\n")
    imported = from_openapi(_api({"/me": {"get": {"operationId": "me", "responses": {"200": {"description": "ok"}}}}}))
    with pytest.raises(NotImported, match="tools/me.yaml"):
        write_into(tree, imported)
    assert (tree / "tools" / "me.yaml").read_text() == "description: Mine.\nsays: Hello.\n"
    with pytest.raises(NotImported, match="no workspace.yaml"):
        write_into(tmp_path / "nowhere", imported)


def test_a_shape_already_there_with_other_parts_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    tree = _tree(tmp_path / "t")
    mine = WORKSPACE + "shapes:\n  pet:\n    tag: text\n"
    (tree / "workspace.yaml").write_text(mine)
    imported = from_openapi(_api(
        {"/pets": {"post": {"operationId": "addPet", "requestBody": {"content": {"application/json": {
            "schema": {"type": "object", "properties": {"pet": {"$ref": "#/components/schemas/Pet"}}}}}},
            "responses": {"201": {"description": "made"}}}}},
        components={"schemas": {"Pet": {"type": "object", "properties": {"name": {"type": "string"}}}}},
    ))  # fmt: skip
    assert imported.shapes["pet"] == {"name": "text, optional"}, "the import's `pet` is not the tree's"
    with pytest.raises(NotImported, match="workspace.yaml shapes: pet"):
        write_into(tree, imported)
    assert (tree / "workspace.yaml").read_text() == mine and not (tree / "tools").exists()


def test_a_tree_whose_files_do_not_parse_is_refused_with_the_fix(tmp_path: Path) -> None:
    tree = _tree(tmp_path / "t")
    (tree / "workspace.yaml").write_text(WORKSPACE + "description: [oops\n")
    imported = from_openapi(_api({"/me": {"get": {"operationId": "me", "responses": {"200": {"description": "ok"}}}}}))
    with pytest.raises(NotImported, match="could not be read.*Nothing was written. Fix: make workspace.yaml"):
        write_into(tree, imported)
    assert not (tree / "tools").exists()


def test_swagger_two_is_refused_with_the_fix() -> None:
    with pytest.raises(NotImported, match="Swagger 2.0.*convert it to OpenAPI 3"):
        from_openapi({"swagger": "2.0", "info": {"title": "Old"}, "paths": {}})


def test_the_command_writes_into_a_tree_or_prints(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    description = REPO / "tests" / "trees" / "openapi" / "petstore-expanded" / "openapi.yaml"
    assert pact_import([str(description), "--as", "openapi"]) == 0
    printed = capsys.readouterr().out
    assert "--- # tools/find-pets.yaml" in printed and "came across" in printed
    tree = _tree(tmp_path / "t")
    assert pact_import([str(description), "--as", "openapi", "--out", str(tree)]) == 0
    assert (tree / "tools" / "find-pets.yaml").is_file()
    assert pact_import([str(description), "--out", str(tree)]) == 1, "--out goes with --as openapi only"


# ── the count has teeth ──────────────────────────────────────────────────────────────────────


def test_a_keyword_nobody_accounts_for_is_a_silent_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Break the importer: a scalar's `type` is no longer said to be mapped. The count is
    computed from what was seen, so the drop is found without anybody listing it."""
    real = openapi_shapes.Shapes.mapped

    def forgetful(self: Any, key: str, what: str) -> None:
        if not key.endswith(".type"):
            real(self, key, what)

    monkeypatch.setattr(openapi_shapes.Shapes, "mapped", forgetful)
    imported = from_openapi(_api({"/x/{id}": {"get": {"operationId": "x", "parameters": [
        {"name": "id", "in": "path", "schema": {"type": "string"}}], "responses": {"200": {"description": "ok"}}}}}))  # fmt: skip
    assert imported.report.silent_drops == ("GET /x/{id} parameters[0] schema.type",)
