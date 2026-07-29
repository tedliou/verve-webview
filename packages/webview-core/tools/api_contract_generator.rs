use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone, Debug)]
enum Json {
    Null,
    Bool(bool),
    Number(u64),
    String(String),
    Array(Vec<Json>),
    Object(BTreeMap<String, Json>),
}

struct Parser<'a> {
    bytes: &'a [u8],
    offset: usize,
}

impl<'a> Parser<'a> {
    fn new(text: &'a str) -> Self {
        Self {
            bytes: text.as_bytes(),
            offset: 0,
        }
    }

    fn parse(mut self) -> Result<Json, String> {
        let value = self.value()?;
        self.whitespace();
        if self.offset != self.bytes.len() {
            return Err(format!("unexpected trailing data at byte {}", self.offset));
        }
        Ok(value)
    }

    fn value(&mut self) -> Result<Json, String> {
        self.whitespace();
        match self.peek() {
            Some(b'{') => self.object(),
            Some(b'[') => self.array(),
            Some(b'"') => self.string().map(Json::String),
            Some(b't') => {
                self.keyword(b"true")?;
                Ok(Json::Bool(true))
            }
            Some(b'f') => {
                self.keyword(b"false")?;
                Ok(Json::Bool(false))
            }
            Some(b'n') => {
                self.keyword(b"null")?;
                Ok(Json::Null)
            }
            Some(b'0'..=b'9') => self.number(),
            other => Err(format!(
                "expected JSON value at byte {}, found {:?}",
                self.offset, other
            )),
        }
    }

    fn object(&mut self) -> Result<Json, String> {
        self.expect(b'{')?;
        let mut fields = BTreeMap::new();
        self.whitespace();
        if self.consume(b'}') {
            return Ok(Json::Object(fields));
        }
        loop {
            self.whitespace();
            let key = self.string()?;
            self.whitespace();
            self.expect(b':')?;
            if fields.insert(key.clone(), self.value()?).is_some() {
                return Err(format!("duplicate object key {key:?}"));
            }
            self.whitespace();
            if self.consume(b'}') {
                break;
            }
            self.expect(b',')?;
        }
        Ok(Json::Object(fields))
    }

    fn array(&mut self) -> Result<Json, String> {
        self.expect(b'[')?;
        let mut values = Vec::new();
        self.whitespace();
        if self.consume(b']') {
            return Ok(Json::Array(values));
        }
        loop {
            values.push(self.value()?);
            self.whitespace();
            if self.consume(b']') {
                break;
            }
            self.expect(b',')?;
        }
        Ok(Json::Array(values))
    }

    fn string(&mut self) -> Result<String, String> {
        self.expect(b'"')?;
        let mut result = String::new();
        while let Some(byte) = self.take() {
            match byte {
                b'"' => return Ok(result),
                b'\\' => {
                    let escaped = self
                        .take()
                        .ok_or_else(|| "unterminated string escape".to_owned())?;
                    match escaped {
                        b'"' => result.push('"'),
                        b'\\' => result.push('\\'),
                        b'/' => result.push('/'),
                        b'b' => result.push('\u{0008}'),
                        b'f' => result.push('\u{000c}'),
                        b'n' => result.push('\n'),
                        b'r' => result.push('\r'),
                        b't' => result.push('\t'),
                        _ => return Err("only simple JSON string escapes are supported".to_owned()),
                    }
                }
                0x00..=0x1f => return Err("control character in JSON string".to_owned()),
                0x20..=0x7f => result.push(byte as char),
                _ => return Err("contract source must encode non-ASCII text with ASCII escapes".to_owned()),
            }
        }
        Err("unterminated JSON string".to_owned())
    }

    fn number(&mut self) -> Result<Json, String> {
        let start = self.offset;
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.offset += 1;
        }
        let text = std::str::from_utf8(&self.bytes[start..self.offset]).unwrap();
        text.parse::<u64>()
            .map(Json::Number)
            .map_err(|error| format!("invalid uint at byte {start}: {error}"))
    }

    fn keyword(&mut self, expected: &[u8]) -> Result<(), String> {
        if self.bytes.get(self.offset..self.offset + expected.len()) == Some(expected) {
            self.offset += expected.len();
            Ok(())
        } else {
            Err(format!("invalid keyword at byte {}", self.offset))
        }
    }

    fn whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\n' | b'\r' | b'\t')) {
            self.offset += 1;
        }
    }

    fn expect(&mut self, expected: u8) -> Result<(), String> {
        if self.consume(expected) {
            Ok(())
        } else {
            Err(format!(
                "expected {:?} at byte {}",
                expected as char, self.offset
            ))
        }
    }

    fn consume(&mut self, expected: u8) -> bool {
        if self.peek() == Some(expected) {
            self.offset += 1;
            true
        } else {
            false
        }
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.offset).copied()
    }

    fn take(&mut self) -> Option<u8> {
        let byte = self.peek()?;
        self.offset += 1;
        Some(byte)
    }
}

impl Json {
    fn object(&self, context: &str) -> Result<&BTreeMap<String, Json>, String> {
        match self {
            Json::Object(value) => Ok(value),
            _ => Err(format!("{context} must be an object")),
        }
    }

    fn array(&self, context: &str) -> Result<&[Json], String> {
        match self {
            Json::Array(value) => Ok(value),
            _ => Err(format!("{context} must be an array")),
        }
    }

    fn string(&self, context: &str) -> Result<&str, String> {
        match self {
            Json::String(value) => Ok(value),
            _ => Err(format!("{context} must be a string")),
        }
    }

    fn number(&self, context: &str) -> Result<u64, String> {
        match self {
            Json::Number(value) => Ok(*value),
            _ => Err(format!("{context} must be an unsigned integer")),
        }
    }
}

fn field<'a>(
    object: &'a BTreeMap<String, Json>,
    name: &str,
    context: &str,
) -> Result<&'a Json, String> {
    object
        .get(name)
        .ok_or_else(|| format!("{context} is missing {name:?}"))
}

#[derive(Clone)]
struct ErrorCode {
    id: u32,
    name: String,
    description: String,
    caller_action: String,
    operations: Vec<String>,
    state_effect: String,
}

struct Operation {
    name: String,
    legal_pre_states: Vec<String>,
}

struct Contract {
    source: Json,
    version: String,
    lifecycle_states: Vec<String>,
    operations: Vec<Operation>,
    errors: Vec<ErrorCode>,
}

fn parse_file(path: &Path) -> Result<Json, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("cannot read {}: {error}", path.display()))?;
    Parser::new(&text)
        .parse()
        .map_err(|error| format!("{}: {error}", path.display()))
}

fn validate_contract(contract_path: &Path, registry_path: &Path) -> Result<Contract, String> {
    let source = parse_file(contract_path)?;
    let root = source.object("API Contract root")?;
    if field(root, "schema_version", "API Contract")?.number("schema_version")? != 1 {
        return Err("schema_version must be 1".to_owned());
    }
    let version = field(root, "contract_version", "API Contract")?
        .string("contract_version")?
        .to_owned();
    if !version.starts_with("1.") {
        return Err("v1 generator only accepts a 1.x contract_version".to_owned());
    }

    let result = field(root, "result", "API Contract")?.object("result")?;
    for required in ["code", "diagnostic_detail", "is_success"] {
        field(result, required, "result")?;
    }
    let diagnostic = field(result, "diagnostic_detail", "result")?
        .object("result.diagnostic_detail")?;
    if field(diagnostic, "maximum_bytes", "diagnostic_detail")?
        .number("maximum_bytes")?
        != 1024
    {
        return Err("diagnostic_detail.maximum_bytes must remain 1024".to_owned());
    }

    let lifecycle = field(root, "lifecycle", "API Contract")?.object("lifecycle")?;
    let lifecycle_states = field(lifecycle, "states", "lifecycle")?
        .array("lifecycle.states")?
        .iter()
        .map(|state| state.string("lifecycle state").map(str::to_owned))
        .collect::<Result<Vec<_>, _>>()?;

    let operations_json = field(root, "operations", "API Contract")?.array("operations")?;
    let mut operations = Vec::new();
    let mut operation_names = BTreeSet::new();
    for (index, operation) in operations_json.iter().enumerate() {
        let object = operation.object(&format!("operations[{index}]"))?;
        let name = field(object, "name", "operation")?
            .string("operation.name")?
            .to_owned();
        for required in ["legal_pre_states", "accepted_state", "success_state"] {
            field(object, required, &format!("operation {name}"))?;
        }
        if !operation_names.insert(name.clone()) {
            return Err(format!("duplicate operation name {name}"));
        }
        let legal_pre_states = field(object, "legal_pre_states", "operation")?
            .array("operation.legal_pre_states")?
            .iter()
            .map(|state| state.string("legal pre-state").map(str::to_owned))
            .collect::<Result<Vec<_>, _>>()?;
        operations.push(Operation {
            name,
            legal_pre_states,
        });
    }
    let required_operations = BTreeSet::from([
        "initialize".to_owned(),
        "open".to_owned(),
        "close".to_owned(),
        "dispose".to_owned(),
    ]);
    if operation_names != required_operations {
        return Err("operations must be exactly initialize/open/close/dispose".to_owned());
    }

    let errors_json = field(root, "public_error_codes", "API Contract")?
        .array("public_error_codes")?;
    let mut ids = BTreeSet::new();
    let mut names = BTreeSet::new();
    let mut errors = Vec::new();
    for (index, error) in errors_json.iter().enumerate() {
        let object = error.object(&format!("public_error_codes[{index}]"))?;
        let raw_id = field(object, "id", "error code")?.number("error code id")?;
        let id = u32::try_from(raw_id).map_err(|_| format!("error ID {raw_id} exceeds uint32"))?;
        let name = field(object, "name", "error code")?
            .string("error code name")?
            .to_owned();
        if !ids.insert(id) {
            return Err(format!("duplicate public error ID {id}"));
        }
        if !names.insert(name.clone()) {
            return Err(format!("duplicate public error name {name}"));
        }
        let applicable = field(object, "operations", "error code")?.array("error operations")?;
        if applicable.is_empty() {
            return Err(format!("{name} has no applicable operations"));
        }
        let mut error_operations = Vec::new();
        for operation in applicable {
            let operation = operation.string("error operation")?.to_owned();
            if !required_operations.contains(&operation) {
                return Err(format!("{name} refers to unknown operation {operation}"));
            }
            error_operations.push(operation);
        }
        errors.push(ErrorCode {
            id,
            name,
            description: field(object, "description", "error code")?
                .string("error description")?
                .to_owned(),
            caller_action: field(object, "caller_action", "error code")?
                .string("error caller_action")?
                .to_owned(),
            operations: error_operations,
            state_effect: field(object, "state_effect", "error code")?
                .string("error state_effect")?
                .to_owned(),
        });
    }
    if errors.len() != 20 || !ids.contains(&0) {
        return Err("the closed v1 catalogue must contain its 20 permanent IDs".to_owned());
    }

    let registry = parse_file(registry_path)?;
    let registry_root = registry.object("error ID registry root")?;
    if field(registry_root, "registry_version", "registry")?.number("registry_version")? != 1 {
        return Err("registry_version must be 1".to_owned());
    }
    let entries = field(registry_root, "ids", "registry")?.array("registry.ids")?;
    let contract_by_id: BTreeMap<u32, &str> =
        errors.iter().map(|error| (error.id, error.name.as_str())).collect();
    let mut registry_ids = BTreeSet::new();
    for (index, entry) in entries.iter().enumerate() {
        let object = entry.object(&format!("registry.ids[{index}]"))?;
        let raw_id = field(object, "id", "registry entry")?.number("registry id")?;
        let id = u32::try_from(raw_id).map_err(|_| format!("registry ID {raw_id} exceeds uint32"))?;
        if !registry_ids.insert(id) {
            return Err(format!("duplicate registry ID {id}"));
        }
        let name = field(object, "name", "registry entry")?.string("registry name")?;
        let status = field(object, "status", "registry entry")?.string("registry status")?;
        match status {
            "active" if contract_by_id.get(&id) == Some(&name) => {}
            "active" => return Err(format!("active registry ID {id} does not match the contract")),
            "reserved" if contract_by_id.contains_key(&id) => {
                return Err(format!("reserved ID {id} was reused by the contract"))
            }
            "reserved" => {}
            _ => return Err(format!("registry ID {id} has invalid status {status:?}")),
        }
    }
    if contract_by_id.keys().copied().collect::<BTreeSet<_>>() !=
        entries
            .iter()
            .filter_map(|entry| {
                let object = entry.object("registry entry").ok()?;
                if object.get("status")?.string("status").ok()? == "active" {
                    u32::try_from(object.get("id")?.number("id").ok()?).ok()
                } else {
                    None
                }
            })
            .collect()
    {
        return Err("active registry entries and contract IDs differ".to_owned());
    }

    Ok(Contract {
        source,
        version,
        lifecycle_states,
        operations,
        errors,
    })
}

fn pascal(name: &str) -> String {
    name.split('_')
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                Some(first) => first.to_ascii_uppercase().to_string() + chars.as_str(),
                None => String::new(),
            }
        })
        .collect()
}

fn json_string(value: &str) -> String {
    let mut result = String::from("\"");
    for character in value.chars() {
        match character {
            '"' => result.push_str("\\\""),
            '\\' => result.push_str("\\\\"),
            '\n' => result.push_str("\\n"),
            '\r' => result.push_str("\\r"),
            '\t' => result.push_str("\\t"),
            other => result.push(other),
        }
    }
    result.push('"');
    result
}

fn write_json(value: &Json, indent: usize, out: &mut String) {
    match value {
        Json::Null => out.push_str("null"),
        Json::Bool(value) => out.push_str(if *value { "true" } else { "false" }),
        Json::Number(value) => out.push_str(&value.to_string()),
        Json::String(value) => out.push_str(&json_string(value)),
        Json::Array(values) => {
            if values.is_empty() {
                out.push_str("[]");
                return;
            }
            out.push_str("[\n");
            for (index, value) in values.iter().enumerate() {
                out.push_str(&" ".repeat(indent + 2));
                write_json(value, indent + 2, out);
                if index + 1 != values.len() {
                    out.push(',');
                }
                out.push('\n');
            }
            out.push_str(&" ".repeat(indent));
            out.push(']');
        }
        Json::Object(fields) => {
            if fields.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push_str("{\n");
            for (index, (name, value)) in fields.iter().enumerate() {
                out.push_str(&" ".repeat(indent + 2));
                out.push_str(&json_string(name));
                out.push_str(": ");
                write_json(value, indent + 2, out);
                if index + 1 != fields.len() {
                    out.push(',');
                }
                out.push('\n');
            }
            out.push_str(&" ".repeat(indent));
            out.push('}');
        }
    }
}

fn render(contract: &Contract) -> BTreeMap<&'static str, String> {
    let mut outputs = BTreeMap::new();

    let mut rust = String::from("// @generated from api-contract.yaml; do not edit.\n\n#[repr(u32)]\n#[derive(Clone, Copy, Debug, Eq, PartialEq)]\npub enum PublicErrorCode {\n");
    for error in &contract.errors {
        rust.push_str(&format!("    {} = {},\n", pascal(&error.name), error.id));
    }
    rust.push_str("}\n\n#[derive(Clone, Copy, Debug, Eq, PartialEq)]\npub enum LifecycleState {\n");
    for state in &contract.lifecycle_states {
        rust.push_str(&format!("    {},\n", pascal(state)));
    }
    rust.push_str("}\n\n#[derive(Clone, Copy, Debug, Eq, PartialEq)]\npub enum OperationKind {\n");
    for operation in &contract.operations {
        rust.push_str(&format!("    {},\n", pascal(&operation.name)));
    }
    rust.push_str("}\n\npub fn is_legal_pre_state(operation: OperationKind, state: LifecycleState) -> bool {\n    matches!((operation, state),\n");
    let stable_states: BTreeSet<&str> =
        contract.lifecycle_states.iter().map(String::as_str).collect();
    let mut first = true;
    for operation in &contract.operations {
        for state in &operation.legal_pre_states {
            if !stable_states.contains(state.as_str()) {
                continue;
            }
            rust.push_str(if first { "        " } else { "        | " });
            rust.push_str(&format!(
                "(OperationKind::{}, LifecycleState::{})\n",
                pascal(&operation.name),
                pascal(state)
            ));
            first = false;
        }
    }
    rust.push_str("    )\n}\n\n#[derive(Clone, Debug, Eq, PartialEq)]\npub struct WebViewResult {\n    pub code: PublicErrorCode,\n    pub diagnostic_detail: Option<String>,\n}\n\nimpl WebViewResult {\n    pub fn is_success(&self) -> bool { self.code == PublicErrorCode::Ok }\n}\n\npub const OPERATIONS: &[&str] = &[");
    for (index, operation) in contract.operations.iter().enumerate() {
        if index > 0 {
            rust.push_str(", ");
        }
        rust.push_str(&json_string(&operation.name));
    }
    rust.push_str("];\n");
    outputs.insert("rust/api_contract.rs", rust);

    let mut native = String::from("/* @generated from api-contract.yaml; do not edit. */\n#ifndef VERVE_WEBVIEW_API_CONTRACT_H\n#define VERVE_WEBVIEW_API_CONTRACT_H\n#include <stdint.h>\n\ntypedef enum verve_webview_error_code {\n");
    for error in &contract.errors {
        native.push_str(&format!(
            "  VERVE_WEBVIEW_{} = {},\n",
            error.name.to_ascii_uppercase(),
            error.id
        ));
    }
    native.push_str("} verve_webview_error_code;\n\ntypedef struct verve_webview_bytes_view {\n  const uint8_t *data;\n  uint32_t length;\n} verve_webview_bytes_view;\n\ntypedef struct verve_webview_result {\n  uint32_t code;\n  verve_webview_bytes_view diagnostic_detail;\n} verve_webview_result;\n\n#endif\n");
    outputs.insert("native/webview_api_contract.h", native);

    let mut native_vectors = String::from("/* @generated from api-contract.yaml; do not edit. */\n#ifndef VERVE_WEBVIEW_LIFECYCLE_CONFORMANCE_H\n#define VERVE_WEBVIEW_LIFECYCLE_CONFORMANCE_H\n#include <stdint.h>\n\ntypedef struct verve_webview_lifecycle_legality_vector {\n  uint32_t operation;\n  uint32_t state;\n  uint32_t is_legal;\n} verve_webview_lifecycle_legality_vector;\n\nstatic const verve_webview_lifecycle_legality_vector VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTORS[] = {\n");
    for (operation_index, operation) in contract.operations.iter().enumerate() {
        for (state_index, state) in contract.lifecycle_states.iter().enumerate() {
            native_vectors.push_str(&format!(
                "  {{{}, {}, {}}},\n",
                operation_index + 1,
                state_index + 1,
                u8::from(operation.legal_pre_states.contains(state))
            ));
        }
    }
    native_vectors.push_str("};\n\n#define VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTOR_COUNT \\\n+  (sizeof(VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTORS) / \\\n+   sizeof(VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTORS[0]))\n\n#endif\n");
    outputs.insert("native/webview_lifecycle_conformance.h", native_vectors);

    let mut web = String::from("// @generated from api-contract.yaml; do not edit.\nexport const PublicErrorCode = Object.freeze({\n");
    for error in &contract.errors {
        web.push_str(&format!("  {}: {},\n", error.name, error.id));
    }
    web.push_str("});\n\nexport const operations = Object.freeze([");
    for (index, operation) in contract.operations.iter().enumerate() {
        if index > 0 {
            web.push_str(", ");
        }
        web.push_str(&json_string(&operation.name));
    }
    web.push_str("]);\n\nexport const isSuccess = result => result.code === PublicErrorCode.ok;\n");
    outputs.insert("web/api-contract.js", web);

    let mut unity = String::from("// <auto-generated />\n#nullable enable\nnamespace Verve.WebView {\n  public enum WebViewErrorCode : uint {\n");
    for error in &contract.errors {
        unity.push_str(&format!("    {} = {},\n", pascal(&error.name), error.id));
    }
    unity.push_str("  }\n\n  public readonly struct WebViewResult {\n    public WebViewErrorCode Code { get; }\n    public string? DiagnosticDetail { get; }\n    public bool IsSuccess => Code == WebViewErrorCode.Ok;\n\n    public WebViewResult(WebViewErrorCode code, string? diagnosticDetail = null) {\n      Code = code;\n      DiagnosticDetail = diagnosticDetail;\n    }\n  }\n}\n");
    outputs.insert("unity/WebViewContract.g.cs", unity);

    let mut godot = String::from("# @generated from api-contract.yaml; do not edit.\nclass_name WebViewResult\nextends RefCounted\n\nenum ErrorCode {\n");
    for error in &contract.errors {
        godot.push_str(&format!("  {} = {},\n", error.name.to_ascii_uppercase(), error.id));
    }
    godot.push_str("}\n\nvar code: ErrorCode\nvar diagnostic_detail: String\nvar is_success: bool:\n  get: return code == ErrorCode.OK\n\nfunc _init(value: ErrorCode, detail: String = \"\"):\n  code = value\n  diagnostic_detail = detail\n");
    outputs.insert("godot/webview_contract.gd", godot);

    let mut docs = format!("# WebView SDK API Contract {}\n\nGenerated from `api-contract.yaml`. Expected failures are returned as WebView Result values.\n\n## Operations\n\n", contract.version);
    for operation in &contract.operations {
        docs.push_str(&format!("- `{}`\n", operation.name));
    }
    docs.push_str("\n## Public Error Codes\n\n| ID | Canonical name | Applicable operations | State effect | Caller action |\n|---:|---|---|---|---|\n");
    for error in &contract.errors {
        docs.push_str(&format!(
            "| {} | `{}` | {} | `{}` | {} {} |\n",
            error.id,
            error.name,
            error.operations.join(", "),
            error.state_effect,
            error.description,
            error.caller_action
        ));
    }
    outputs.insert("docs/api-contract.md", docs);

    let mut conformance = String::new();
    write_json(&contract.source, 0, &mut conformance);
    conformance.push('\n');
    outputs.insert("conformance/api-contract.json", conformance);
    outputs
}

fn generate(contract: &Contract, output_root: &Path) -> Result<(), String> {
    for (relative, content) in render(contract) {
        let path = output_root.join(relative);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)
                .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
        }
        fs::write(&path, content)
            .map_err(|error| format!("cannot write {}: {error}", path.display()))?;
    }
    Ok(())
}

fn verify(contract: &Contract, snapshot_root: &Path, stamp: &Path) -> Result<(), String> {
    for (relative, expected) in render(contract) {
        let path = snapshot_root.join(relative);
        let actual = fs::read_to_string(&path)
            .map_err(|error| format!("cannot read committed snapshot {}: {error}", path.display()))?;
        if actual.as_bytes() != expected.as_bytes() {
            return Err(format!(
                "committed snapshot {} differs; run //packages/webview-core:update_api_contract",
                path.display()
            ));
        }
    }
    fs::write(stamp, format!("api-contract {} verified", contract.version))
        .map_err(|error| format!("cannot write verification stamp {}: {error}", stamp.display()))
}

fn run() -> Result<(), String> {
    let args: Vec<String> = env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("update") if args.len() == 2 => {
            let root = PathBuf::from(
                env::var("BUILD_WORKSPACE_DIRECTORY")
                    .map_err(|_| "update must run through `bazel run`".to_owned())?,
            );
            let contract_path = root.join("packages/webview-core/api-contract.yaml");
            let registry_path = root.join("packages/webview-core/error-id-registry.json");
            let contract = validate_contract(&contract_path, &registry_path)?;
            generate(&contract, &root.join("packages/webview-core/generated"))
        }
        Some("verify") if args.len() == 6 => {
            let contract_path = Path::new(&args[2]);
            let registry_path = Path::new(&args[3]);
            let contract = validate_contract(contract_path, registry_path)?;
            verify(&contract, Path::new(&args[4]), Path::new(&args[5]))
        }
        _ => Err("usage: api_contract_generator update | verify <contract> <registry> <snapshot-root> <stamp>".to_owned()),
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("api_contract_generator: {error}");
        std::process::exit(1);
    }
}
