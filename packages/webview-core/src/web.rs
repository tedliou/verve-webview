//! Browser transport over the shared semantic WebView Core runtime.

use std::cell::RefCell;
use std::collections::BTreeMap;
use verve_webview_core::{
    BackendCommand, BackendCompletion, CommandOutcome, Core, InstanceHandle, OperationKind,
    PublicErrorCode, SurfaceGeometry,
};
use wasm_bindgen::prelude::*;

struct BrowserTransport {
    core: Core,
    instances: BTreeMap<u32, InstanceHandle>,
    operations: BTreeMap<u32, BackendCommand>,
    next_instance: u32,
    next_operation: u32,
}

impl BrowserTransport {
    fn new() -> Self {
        Self {
            core: Core::new(),
            instances: BTreeMap::new(),
            operations: BTreeMap::new(),
            next_instance: 1,
            next_operation: 1,
        }
    }

    fn create_instance(&mut self) -> u32 {
        let public_handle = self.next_instance;
        self.next_instance = self
            .next_instance
            .checked_add(1)
            .expect("browser instance handle exhausted");
        self.instances
            .insert(public_handle, self.core.create_instance());
        public_handle
    }

    fn instance(&self, public_handle: u32) -> InstanceHandle {
        self.instances
            .get(&public_handle)
            .copied()
            .unwrap_or(InstanceHandle(0))
    }

    fn start(&mut self, public_instance: u32, outcome: CommandOutcome) -> String {
        let Some(command) = outcome.command else {
            return format!(
                "{{\"result\":{},\"request\":null}}",
                result_json(outcome.code, None)
            );
        };
        let public_operation = self.next_operation;
        self.next_operation = self
            .next_operation
            .checked_add(1)
            .expect("browser operation handle exhausted");
        let request = request_json(public_instance, public_operation, &command);
        self.operations.insert(public_operation, command);
        format!(
            "{{\"result\":{},\"request\":{request}}}",
            result_json(PublicErrorCode::Ok, None)
        )
    }

    fn complete(
        &mut self,
        public_instance: u32,
        public_operation: u32,
        wire_code: u32,
        diagnostic_detail: &str,
    ) -> String {
        let Some(command) = self.operations.get(&public_operation).cloned() else {
            return "{\"event\":null}".to_owned();
        };
        if self.instance(public_instance) != command.instance {
            return "{\"event\":null}".to_owned();
        }
        let (code, detail) = match public_code(wire_code) {
            Some(code) => (
                code,
                (!diagnostic_detail.is_empty()).then(|| diagnostic_detail.to_owned()),
            ),
            None => (
                PublicErrorCode::AbiMismatch,
                Some(format!("unknown Public Error Code wire ID {wire_code}")),
            ),
        };
        let event = self.core.complete(BackendCompletion {
            instance: command.instance,
            operation: command.operation,
            generation: command.generation,
            code,
            diagnostic_detail: detail,
        });
        self.operations.remove(&public_operation);
        let Some(event) = event else {
            return "{\"event\":null}".to_owned();
        };
        format!(
            "{{\"event\":{{\"instance\":{public_instance},\"operation\":{public_operation},\
             \"kind\":\"{}\",\"result\":{}}}}}",
            kind_name(event.kind),
            result_json(event.code, event.diagnostic_detail.as_deref())
        )
    }
}

thread_local! {
    static TRANSPORT: RefCell<BrowserTransport> = RefCell::new(BrowserTransport::new());
}

#[wasm_bindgen]
pub fn browser_create_instance() -> u32 {
    TRANSPORT.with(|transport| transport.borrow_mut().create_instance())
}

#[wasm_bindgen]
pub fn browser_initialize(public_instance: u32, options: &str) -> String {
    TRANSPORT.with(|transport| {
        let mut transport = transport.borrow_mut();
        let outcome = transport
            .core
            .initialize(transport.instance(public_instance), options.as_bytes());
        transport.start(public_instance, outcome)
    })
}

#[wasm_bindgen]
pub fn browser_open(
    public_instance: u32,
    url: &str,
    has_geometry: bool,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
) -> String {
    TRANSPORT.with(|transport| {
        let mut transport = transport.borrow_mut();
        let geometry = has_geometry.then_some(SurfaceGeometry {
            x,
            y,
            width,
            height,
        });
        let outcome =
            transport
                .core
                .open(transport.instance(public_instance), url.as_bytes(), geometry);
        transport.start(public_instance, outcome)
    })
}

#[wasm_bindgen]
pub fn browser_close(public_instance: u32) -> String {
    TRANSPORT.with(|transport| {
        let mut transport = transport.borrow_mut();
        let outcome = transport.core.close(transport.instance(public_instance));
        transport.start(public_instance, outcome)
    })
}

#[wasm_bindgen]
pub fn browser_dispose(public_instance: u32) -> String {
    TRANSPORT.with(|transport| {
        let mut transport = transport.borrow_mut();
        let outcome = transport.core.dispose(transport.instance(public_instance));
        transport.start(public_instance, outcome)
    })
}

#[wasm_bindgen]
pub fn browser_complete(
    public_instance: u32,
    public_operation: u32,
    code: u32,
    diagnostic_detail: &str,
) -> String {
    TRANSPORT.with(|transport| {
        transport.borrow_mut().complete(
            public_instance,
            public_operation,
            code,
            diagnostic_detail,
        )
    })
}

#[cfg(browser_transport_test)]
#[wasm_bindgen]
pub fn browser_test_trap() {
    panic!("intentional browser Core panic-abort verification trap");
}

fn request_json(
    public_instance: u32,
    public_operation: u32,
    command: &BackendCommand,
) -> String {
    let payload = String::from_utf8(command.payload.clone()).expect("Core validated UTF-8");
    let geometry = command.geometry.map_or_else(
        || "null".to_owned(),
        |value| {
            format!(
                "{{\"x\":{},\"y\":{},\"width\":{},\"height\":{}}}",
                value.x, value.y, value.width, value.height
            )
        },
    );
    format!(
        "{{\"instance\":{public_instance},\"operation\":{public_operation},\
         \"generation\":{},\"kind\":\"{}\",\"payload\":\"{}\",\"geometry\":{geometry}}}",
        command.generation,
        kind_name(command.kind),
        json_escape(&payload)
    )
}

fn result_json(code: PublicErrorCode, diagnostic_detail: Option<&str>) -> String {
    let detail = diagnostic_detail.map_or_else(
        || "null".to_owned(),
        |value| format!("\"{}\"", json_escape(value)),
    );
    format!(
        "{{\"code\":{},\"diagnosticDetail\":{detail},\"isSuccess\":{}}}",
        code as u32,
        if code == PublicErrorCode::Ok {
            "true"
        } else {
            "false"
        }
    )
}

fn kind_name(kind: OperationKind) -> &'static str {
    match kind {
        OperationKind::Initialize => "initialize",
        OperationKind::Open => "open",
        OperationKind::Close => "close",
        OperationKind::Dispose => "dispose",
    }
}

fn public_code(value: u32) -> Option<PublicErrorCode> {
    Some(match value {
        0 => PublicErrorCode::Ok,
        100 => PublicErrorCode::InvalidOptions,
        101 => PublicErrorCode::InvalidUrl,
        102 => PublicErrorCode::InvalidGeometry,
        200 => PublicErrorCode::NotInitialized,
        201 => PublicErrorCode::AlreadyInitialized,
        202 => PublicErrorCode::OperationInProgress,
        203 => PublicErrorCode::Disposed,
        204 => PublicErrorCode::SurfaceNotOpen,
        205 => PublicErrorCode::SurfaceInUse,
        300 => PublicErrorCode::HostUnavailable,
        301 => PublicErrorCode::HostLost,
        302 => PublicErrorCode::BackendFailure,
        303 => PublicErrorCode::CleanupFailed,
        400 => PublicErrorCode::CoreLoadFailed,
        401 => PublicErrorCode::AbiMismatch,
        402 => PublicErrorCode::RuntimeUnavailable,
        403 => PublicErrorCode::UnsupportedEnvironment,
        404 => PublicErrorCode::DistributionInvalid,
        500 => PublicErrorCode::InternalFailure,
        _ => return None,
    })
}

fn json_escape(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());
    for character in value.chars() {
        match character {
            '"' => escaped.push_str("\\\""),
            '\\' => escaped.push_str("\\\\"),
            '\n' => escaped.push_str("\\n"),
            '\r' => escaped.push_str("\\r"),
            '\t' => escaped.push_str("\\t"),
            character if character <= '\u{001f}' => {
                escaped.push_str(&format!("\\u{:04x}", character as u32));
            }
            character => escaped.push(character),
        }
    }
    escaped
}
