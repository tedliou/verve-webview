use std::collections::BTreeMap;
use std::ffi::c_void;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::slice;
use std::sync::{Mutex, OnceLock};

use verve_webview_core::{
    BackendCompletion, CommandOutcome, CompletionEvent, Core, InstanceHandle, OperationHandle,
    OperationKind, PublicErrorCode, SurfaceGeometry, MAX_DIAGNOSTIC_BYTES, MAX_OPTIONS_BYTES,
    MAX_URL_BYTES,
};

const ABI_VERSION: u32 = 1;
const CAPABILITIES: u64 = 7;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct BytesView {
    data: *const u8,
    length: u32,
}

#[repr(C)]
pub struct AbiInfo {
    struct_size: u32,
    abi_version: u32,
    capabilities: u64,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Geometry {
    x: f64,
    y: f64,
    width: f64,
    height: f64,
}

#[repr(C)]
pub struct BackendRequest {
    struct_size: u32,
    operation_kind: u32,
    instance: u64,
    operation: u64,
    generation: u32,
    has_geometry: u32,
    payload: BytesView,
    geometry: Geometry,
}

#[repr(C)]
pub struct Completion {
    struct_size: u32,
    code: u32,
    instance: u64,
    operation: u64,
    generation: u32,
    reserved: u32,
    diagnostic_detail: BytesView,
}

#[repr(C)]
pub struct ResultEnvelope {
    code: u32,
    diagnostic_detail: BytesView,
}

#[repr(C)]
pub struct CompletionEventEnvelope {
    struct_size: u32,
    operation_kind: u32,
    instance: u64,
    operation: u64,
    result: ResultEnvelope,
}

type BackendSink = extern "C" fn(*mut c_void, *const BackendRequest);
type EventSink = extern "C" fn(*mut c_void, *const CompletionEventEnvelope);
type DiagnosticSink = extern "C" fn(*mut c_void, u64, u64, BytesView);

#[repr(C)]
pub struct InstanceConfig {
    struct_size: u32,
    abi_version: u32,
    required_capabilities: u64,
    user_data: *mut c_void,
    backend_command_sink: Option<BackendSink>,
    completion_event_sink: Option<EventSink>,
    diagnostic_sink: Option<DiagnosticSink>,
}

#[derive(Clone, Copy)]
struct Callbacks {
    user_data: usize,
    backend: BackendSink,
    event: EventSink,
    diagnostic: Option<DiagnosticSink>,
}

fn core() -> &'static Core {
    static CORE: OnceLock<Core> = OnceLock::new();
    CORE.get_or_init(Core::new)
}

fn callbacks() -> &'static Mutex<BTreeMap<InstanceHandle, Callbacks>> {
    static CALLBACKS: OnceLock<Mutex<BTreeMap<InstanceHandle, Callbacks>>> = OnceLock::new();
    CALLBACKS.get_or_init(|| Mutex::new(BTreeMap::new()))
}

fn guarded(function: impl FnOnce() -> u32) -> u32 {
    catch_unwind(AssertUnwindSafe(function)).unwrap_or(PublicErrorCode::InternalFailure as u32)
}

fn copied_bytes(view: BytesView, maximum: usize) -> Option<Vec<u8>> {
    let length = view.length as usize;
    if length > maximum || (length != 0 && view.data.is_null()) {
        return None;
    }
    if length == 0 {
        return Some(Vec::new());
    }
    // SAFETY: The C ABI requires a non-null input buffer valid for the duration
    // of this call. The length is bounded above before constructing the slice.
    Some(unsafe { slice::from_raw_parts(view.data, length) }.to_vec())
}

fn callback_for(instance: InstanceHandle) -> Option<Callbacks> {
    callbacks()
        .lock()
        .unwrap_or_else(|error| error.into_inner())
        .get(&instance)
        .copied()
}

fn operation_number(kind: OperationKind) -> u32 {
    match kind {
        OperationKind::Initialize => 1,
        OperationKind::Open => 2,
        OperationKind::Close => 3,
        OperationKind::Dispose => 4,
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

fn dispatch(outcome: CommandOutcome, out_operation: *mut u64) -> u32 {
    if out_operation.is_null() {
        return PublicErrorCode::AbiMismatch as u32;
    }
    // SAFETY: Null was rejected and the ABI requires a writable output pointer.
    unsafe { out_operation.write(0) };
    let Some(command) = outcome.command else {
        return outcome.code as u32;
    };
    // SAFETY: Null was rejected and the ABI requires a writable output pointer.
    unsafe { out_operation.write(command.operation.0) };
    let Some(callback) = callback_for(command.instance) else {
        return PublicErrorCode::InternalFailure as u32;
    };
    let geometry = command.geometry.unwrap_or_default();
    let request = BackendRequest {
        struct_size: std::mem::size_of::<BackendRequest>() as u32,
        operation_kind: operation_number(command.kind),
        instance: command.instance.0,
        operation: command.operation.0,
        generation: command.generation,
        has_geometry: u32::from(command.geometry.is_some()),
        payload: BytesView {
            data: command.payload.as_ptr(),
            length: command.payload.len() as u32,
        },
        geometry: Geometry {
            x: geometry.x,
            y: geometry.y,
            width: geometry.width,
            height: geometry.height,
        },
    };
    (callback.backend)(callback.user_data as *mut c_void, &request);
    PublicErrorCode::Ok as u32
}

fn emit_event(event: CompletionEvent) {
    let Some(callback) = callback_for(event.instance) else {
        return;
    };
    let detail = event.diagnostic_detail.unwrap_or_default();
    let envelope = CompletionEventEnvelope {
        struct_size: std::mem::size_of::<CompletionEventEnvelope>() as u32,
        operation_kind: operation_number(event.kind),
        instance: event.instance.0,
        operation: event.operation.0,
        result: ResultEnvelope {
            code: event.code as u32,
            diagnostic_detail: BytesView {
                data: detail.as_ptr(),
                length: detail.len() as u32,
            },
        },
    };
    (callback.event)(callback.user_data as *mut c_void, &envelope);
    if event.kind == OperationKind::Dispose {
        callbacks()
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .remove(&event.instance);
    }
}

fn emit_diagnostics(instance: InstanceHandle, operation: OperationHandle) {
    let Some(callback) = callback_for(instance) else {
        core().drain_diagnostics();
        return;
    };
    let Some(sink) = callback.diagnostic else {
        core().drain_diagnostics();
        return;
    };
    for detail in core().drain_diagnostics() {
        let view = BytesView {
            data: detail.as_ptr(),
            length: detail.len() as u32,
        };
        sink(
            callback.user_data as *mut c_void,
            instance.0,
            operation.0,
            view,
        );
    }
}

#[no_mangle]
pub extern "C" fn verve_webview_get_abi_info(out_info: *mut AbiInfo) -> u32 {
    guarded(|| {
        if out_info.is_null() {
            return PublicErrorCode::AbiMismatch as u32;
        }
        // SAFETY: Null was rejected and the ABI requires a writable output pointer.
        unsafe {
            out_info.write(AbiInfo {
                struct_size: std::mem::size_of::<AbiInfo>() as u32,
                abi_version: ABI_VERSION,
                capabilities: CAPABILITIES,
            })
        };
        PublicErrorCode::Ok as u32
    })
}

#[no_mangle]
pub extern "C" fn verve_webview_create_instance(
    config: *const InstanceConfig,
    out_instance: *mut u64,
) -> u32 {
    guarded(|| {
        if config.is_null() || out_instance.is_null() {
            return PublicErrorCode::AbiMismatch as u32;
        }
        // SAFETY: Both pointers are non-null and required to be valid for this call.
        let config = unsafe { &*config };
        if config.struct_size < std::mem::size_of::<InstanceConfig>() as u32
            || config.abi_version != ABI_VERSION
            || config.required_capabilities & !CAPABILITIES != 0
        {
            return PublicErrorCode::AbiMismatch as u32;
        }
        let (Some(backend), Some(event)) =
            (config.backend_command_sink, config.completion_event_sink)
        else {
            return PublicErrorCode::InvalidOptions as u32;
        };
        let instance = core().create_instance();
        callbacks()
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .insert(
                instance,
                Callbacks {
                    user_data: config.user_data as usize,
                    backend,
                    event,
                    diagnostic: config.diagnostic_sink,
                },
            );
        // SAFETY: Null was rejected and the ABI requires a writable output pointer.
        unsafe { out_instance.write(instance.0) };
        PublicErrorCode::Ok as u32
    })
}

#[no_mangle]
pub extern "C" fn verve_webview_initialize(
    instance: u64,
    options: BytesView,
    out_operation: *mut u64,
) -> u32 {
    guarded(|| {
        if out_operation.is_null() {
            return PublicErrorCode::AbiMismatch as u32;
        }
        let Some(options) = copied_bytes(options, MAX_OPTIONS_BYTES) else {
            return PublicErrorCode::InvalidOptions as u32;
        };
        dispatch(
            core().initialize(InstanceHandle(instance), &options),
            out_operation,
        )
    })
}

#[no_mangle]
pub extern "C" fn verve_webview_open(
    instance: u64,
    url: BytesView,
    geometry: *const Geometry,
    out_operation: *mut u64,
) -> u32 {
    guarded(|| {
        if out_operation.is_null() {
            return PublicErrorCode::AbiMismatch as u32;
        }
        let Some(url) = copied_bytes(url, MAX_URL_BYTES) else {
            return PublicErrorCode::InvalidUrl as u32;
        };
        let geometry = if geometry.is_null() {
            None
        } else {
            // SAFETY: Non-null geometry must remain valid for this call.
            let value = unsafe { *geometry };
            Some(SurfaceGeometry {
                x: value.x,
                y: value.y,
                width: value.width,
                height: value.height,
            })
        };
        dispatch(
            core().open(InstanceHandle(instance), &url, geometry),
            out_operation,
        )
    })
}

#[no_mangle]
pub extern "C" fn verve_webview_close(instance: u64, out_operation: *mut u64) -> u32 {
    guarded(|| {
        if out_operation.is_null() {
            return PublicErrorCode::AbiMismatch as u32;
        }
        dispatch(core().close(InstanceHandle(instance)), out_operation)
    })
}

#[no_mangle]
pub extern "C" fn verve_webview_dispose(instance: u64, out_operation: *mut u64) -> u32 {
    guarded(|| {
        if out_operation.is_null() {
            return PublicErrorCode::AbiMismatch as u32;
        }
        dispatch(core().dispose(InstanceHandle(instance)), out_operation)
    })
}

#[no_mangle]
pub extern "C" fn verve_webview_complete(completion: *const Completion) -> u32 {
    guarded(|| {
        if completion.is_null() {
            return PublicErrorCode::AbiMismatch as u32;
        }
        // SAFETY: Non-null completion must remain valid for this call.
        let completion = unsafe { &*completion };
        if completion.struct_size < std::mem::size_of::<Completion>() as u32 {
            return PublicErrorCode::AbiMismatch as u32;
        }
        let (code, detail) = match (
            public_code(completion.code),
            copied_bytes(completion.diagnostic_detail, MAX_DIAGNOSTIC_BYTES)
                .and_then(|detail| String::from_utf8(detail).ok()),
        ) {
            (Some(code), Some(detail)) if detail.is_empty() => (code, None),
            (Some(code), Some(detail)) => (code, Some(detail)),
            _ => (
                PublicErrorCode::AbiMismatch,
                Some("malformed backend completion envelope".to_owned()),
            ),
        };
        let instance = InstanceHandle(completion.instance);
        let operation = OperationHandle(completion.operation);
        if let Some(event) = core().complete(BackendCompletion {
            instance,
            operation,
            generation: completion.generation,
            code,
            diagnostic_detail: detail,
        }) {
            emit_event(event);
        }
        emit_diagnostics(instance, operation);
        PublicErrorCode::Ok as u32
    })
}

#[no_mangle]
pub extern "C" fn verve_webview_report_host_lost(instance: u64) -> u32 {
    guarded(|| {
        core().report_host_lost(InstanceHandle(instance));
        emit_diagnostics(InstanceHandle(instance), OperationHandle(0));
        PublicErrorCode::Ok as u32
    })
}
