# Ten public OpenAPI descriptions

What `pact-import --as openapi` is tested on
(`adapters/python/tests/test_an_openapi_description_imports_as_reviewed_tool_files.py`):
each one imports into a tree whose every tool file `pact check` accepts, with every
operation that does not declare its effect marked *Needs a look*, and nothing
left out of the report.

Each file is the publisher's own, unedited, fetched on 12 October 2026. The
licence of each was checked before it was copied here, and is kept beside it
(`LICENSE`) where it asks to be.

| Folder | Description | Source (commit) | Operations | Licence |
|---|---|---|---|---|
| `swagger-petstore` | Swagger Petstore, OpenAPI 3.0 | `swagger-api/swagger-petstore`, `src/main/resources/openapi.yaml` (`d57941e8fe95`) | 19 | Apache-2.0 |
| `petstore-expanded` | Swagger Petstore (expanded) | `OAI/learn.openapis.org`, `examples/v3.0/petstore-expanded.yaml` (`be248e49bd09`) | 4 | CC-BY-4.0 (the repository); the description says Apache-2.0 |
| `uspto` | USPTO Data Set API | `OAI/learn.openapis.org`, `examples/v3.0/uspto.yaml` (`bda51648af38`) | 3 | CC-BY-4.0 |
| `redocly-museum` | Redocly Museum API | `Redocly/museum-openapi-example`, `openapi.yaml` (`2770b2b2e598`) | 8 | MIT |
| `twilio-lookups` | Twilio Lookups v2 | `twilio/twilio-oai`, `spec/yaml/twilio_lookups_v2.yaml` (`591755b56283`) | 10 | MIT (the repository); the description says Apache-2.0 |
| `xero-identity` | Xero OAuth 2 Identity Service API | `XeroAPI/Xero-OpenAPI`, `xero-identity.yaml` (`fd9d44b04bf4`) | 2 | MIT |
| `adyen-bin-lookup` | Adyen BinLookup API v54 | `Adyen/adyen-openapi`, `json/BinLookupService-v54.json` (`c1fcb98be2ac`) | 2 | MIT |
| `weather-gov` | weather.gov API (US National Weather Service) | `https://api.weather.gov/openapi.json` | 69 | Public domain: a work of the US Government (17 U.S.C. § 105) |
| `ory-kratos` | Ory Identities API (Kratos) | `ory/kratos`, `spec/api.json` (`377702a41fa4`) | 60 | Apache-2.0 |
| `ory-hydra` | Ory Hydra API | `ory/hydra`, `spec/api.json` (`62a247644f5b`) | 52 | Apache-2.0 |

Looked at and left out: the Bump.sh *Train Travel API* (CC-BY-NC-SA-4.0, which
does not allow commercial use) and Ably's platform API (no licence published).

None of these folders is a PACT tree: there is no `workspace.yaml` here. The test
imports each description into a new tree of its own.
