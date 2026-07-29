//! Engine- and platform-neutral WebView Core lifecycle runtime.

mod contract {
    include!("../generated/rust/api_contract.rs");
}

pub use contract::{
    LifecycleState, OperationKind, PublicErrorCode, WebViewResult, OPERATIONS,
};

use std::collections::BTreeMap;
use std::sync::Mutex;

pub const MAX_OPTIONS_BYTES: usize = 4096;
pub const MAX_URL_BYTES: usize = 8192;
pub const MAX_DIAGNOSTIC_BYTES: usize = 1024;

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct InstanceHandle(pub u64);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct OperationHandle(pub u64);

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SurfaceGeometry {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

impl Default for SurfaceGeometry {
    fn default() -> Self {
        Self {
            x: 0.0,
            y: 0.0,
            width: 1.0,
            height: 1.0,
        }
    }
}

impl SurfaceGeometry {
    fn is_valid(self) -> bool {
        [self.x, self.y, self.width, self.height]
            .iter()
            .all(|value| value.is_finite())
            && (0.0..=1.0).contains(&self.x)
            && (0.0..=1.0).contains(&self.y)
            && self.width > 0.0
            && self.height > 0.0
            && self.width <= 1.0
            && self.height <= 1.0
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct BackendCommand {
    pub instance: InstanceHandle,
    pub operation: OperationHandle,
    pub generation: u32,
    pub kind: OperationKind,
    pub payload: Vec<u8>,
    pub geometry: Option<SurfaceGeometry>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct CommandOutcome {
    pub code: PublicErrorCode,
    pub command: Option<BackendCommand>,
}

impl CommandOutcome {
    fn rejected(code: PublicErrorCode) -> Self {
        Self {
            code,
            command: None,
        }
    }

    fn accepted(command: BackendCommand) -> Self {
        Self {
            code: PublicErrorCode::Ok,
            command: Some(command),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BackendCompletion {
    pub instance: InstanceHandle,
    pub operation: OperationHandle,
    pub generation: u32,
    pub code: PublicErrorCode,
    pub diagnostic_detail: Option<String>,
}

impl BackendCompletion {
    pub fn success(command: &BackendCommand) -> Self {
        Self {
            instance: command.instance,
            operation: command.operation,
            generation: command.generation,
            code: PublicErrorCode::Ok,
            diagnostic_detail: None,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompletionEvent {
    pub instance: InstanceHandle,
    pub operation: OperationHandle,
    pub kind: OperationKind,
    pub code: PublicErrorCode,
    pub diagnostic_detail: Option<String>,
}

#[derive(Clone, Debug)]
struct InFlight {
    operation: OperationHandle,
    generation: u32,
    kind: OperationKind,
    prior_state: LifecycleState,
}

#[derive(Clone, Debug)]
struct Instance {
    generation: u32,
    state: LifecycleState,
    in_flight: Option<InFlight>,
}

#[derive(Default)]
struct Runtime {
    instances: BTreeMap<InstanceHandle, Instance>,
    next_instance: u64,
    next_operation: u64,
    surface_lease: Option<InstanceHandle>,
    diagnostics: Vec<String>,
}

pub struct Core {
    runtime: Mutex<Runtime>,
}

impl Default for Core {
    fn default() -> Self {
        Self::new()
    }
}

impl Core {
    pub fn new() -> Self {
        Self {
            runtime: Mutex::new(Runtime {
                next_instance: 1,
                next_operation: 1,
                ..Runtime::default()
            }),
        }
    }

    pub fn create_instance(&self) -> InstanceHandle {
        let mut runtime = self.runtime.lock().unwrap_or_else(|error| error.into_inner());
        let slot = u32::try_from(runtime.next_instance).expect("instance ID exhausted");
        let handle = InstanceHandle((u64::from(1_u32) << 32) | u64::from(slot));
        runtime.next_instance = runtime.next_instance.checked_add(1).expect("instance ID exhausted");
        runtime.instances.insert(
            handle,
            Instance {
                generation: 1,
                state: LifecycleState::Uninitialized,
                in_flight: None,
            },
        );
        handle
    }

    pub fn lifecycle_state(&self, handle: InstanceHandle) -> Option<LifecycleState> {
        self.runtime
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .instances
            .get(&handle)
            .map(|instance| instance.state)
    }

    pub fn initialize(&self, handle: InstanceHandle, options: &[u8]) -> CommandOutcome {
        let mut runtime = self.runtime.lock().unwrap_or_else(|error| error.into_inner());
        let instance = match runtime.instances.get(&handle) {
            Some(instance) => instance,
            None => return CommandOutcome::rejected(PublicErrorCode::Disposed),
        };
        if let Some(code) = command_gate(instance, OperationKind::Initialize) {
            return CommandOutcome::rejected(code);
        }
        if options.len() > MAX_OPTIONS_BYTES || std::str::from_utf8(options).is_err() {
            return CommandOutcome::rejected(PublicErrorCode::InvalidOptions);
        }
        accept(&mut runtime, handle, OperationKind::Initialize, options.to_vec(), None)
    }

    pub fn open(
        &self,
        handle: InstanceHandle,
        url: &[u8],
        geometry: Option<SurfaceGeometry>,
    ) -> CommandOutcome {
        let mut runtime = self.runtime.lock().unwrap_or_else(|error| error.into_inner());
        let instance = match runtime.instances.get(&handle) {
            Some(instance) => instance,
            None => return CommandOutcome::rejected(PublicErrorCode::Disposed),
        };
        if let Some(code) = command_gate(instance, OperationKind::Open) {
            return CommandOutcome::rejected(code);
        }
        if !valid_url(url) {
            return CommandOutcome::rejected(PublicErrorCode::InvalidUrl);
        }
        if geometry.is_some_and(|value| !value.is_valid()) {
            return CommandOutcome::rejected(PublicErrorCode::InvalidGeometry);
        }
        if instance.state == LifecycleState::InitializedClosed {
            match runtime.surface_lease {
                Some(owner) if owner != handle => {
                    return CommandOutcome::rejected(PublicErrorCode::SurfaceInUse)
                }
                _ => runtime.surface_lease = Some(handle),
            }
        }
        accept(
            &mut runtime,
            handle,
            OperationKind::Open,
            url.to_vec(),
            geometry,
        )
    }

    pub fn close(&self, handle: InstanceHandle) -> CommandOutcome {
        let mut runtime = self.runtime.lock().unwrap_or_else(|error| error.into_inner());
        let instance = match runtime.instances.get(&handle) {
            Some(instance) => instance,
            None => return CommandOutcome::rejected(PublicErrorCode::Disposed),
        };
        if let Some(code) = command_gate(instance, OperationKind::Close) {
            return CommandOutcome::rejected(code);
        }
        accept(&mut runtime, handle, OperationKind::Close, Vec::new(), None)
    }

    pub fn dispose(&self, handle: InstanceHandle) -> CommandOutcome {
        let mut runtime = self.runtime.lock().unwrap_or_else(|error| error.into_inner());
        let instance = match runtime.instances.get_mut(&handle) {
            Some(instance) => instance,
            None => return CommandOutcome::rejected(PublicErrorCode::Disposed),
        };
        if matches!(
            instance.state,
            LifecycleState::Disposing | LifecycleState::Disposed | LifecycleState::Invalidated
        ) {
            return CommandOutcome::rejected(PublicErrorCode::Disposed);
        }
        let prior_state = instance
            .in_flight
            .as_ref()
            .map(|flight| flight.prior_state)
            .unwrap_or(instance.state);
        instance.generation = instance.generation.checked_add(1).expect("generation exhausted");
        instance.in_flight = None;
        instance.state = LifecycleState::Disposing;
        accept_with_prior(
            &mut runtime,
            handle,
            OperationKind::Dispose,
            Vec::new(),
            None,
            prior_state,
        )
    }

    pub fn complete(&self, mut completion: BackendCompletion) -> Option<CompletionEvent> {
        let mut runtime = self.runtime.lock().unwrap_or_else(|error| error.into_inner());
        let flight = runtime
            .instances
            .get(&completion.instance)
            .and_then(|instance| instance.in_flight.clone());
        let Some(flight) = flight else {
            runtime.diagnostics.push(format!(
                "ignored completion for inactive operation {}",
                completion.operation.0
            ));
            return None;
        };
        if flight.operation != completion.operation || flight.generation != completion.generation {
            runtime.diagnostics.push(format!(
                "ignored stale or cross-instance completion for operation {}",
                completion.operation.0
            ));
            return None;
        }

        completion.diagnostic_detail = completion
            .diagnostic_detail
            .as_deref()
            .map(sanitize_diagnostic);
        apply_completion(
            &mut runtime,
            completion.instance,
            &flight,
            completion.code,
        );
        Some(CompletionEvent {
            instance: completion.instance,
            operation: completion.operation,
            kind: flight.kind,
            code: completion.code,
            diagnostic_detail: completion.diagnostic_detail,
        })
    }

    pub fn report_host_lost(&self, handle: InstanceHandle) {
        let mut runtime = self.runtime.lock().unwrap_or_else(|error| error.into_inner());
        let Some(instance) = runtime.instances.get_mut(&handle) else {
            return;
        };
        if instance.in_flight.is_none() && instance.state == LifecycleState::SurfaceOpen {
            instance.state = LifecycleState::InitializedClosed;
            if runtime.surface_lease == Some(handle) {
                runtime.surface_lease = None;
            }
            runtime
                .diagnostics
                .push("host lost between lifecycle operations".to_owned());
        }
    }

    pub fn drain_diagnostics(&self) -> Vec<String> {
        let mut runtime = self.runtime.lock().unwrap_or_else(|error| error.into_inner());
        std::mem::take(&mut runtime.diagnostics)
    }
}

fn command_gate(instance: &Instance, operation: OperationKind) -> Option<PublicErrorCode> {
    if matches!(
        instance.state,
        LifecycleState::Disposing | LifecycleState::Disposed | LifecycleState::Invalidated
    ) {
        return Some(PublicErrorCode::Disposed);
    }
    if instance.in_flight.is_some() {
        return Some(PublicErrorCode::OperationInProgress);
    }
    if contract::is_legal_pre_state(operation, instance.state) {
        return None;
    }
    match (operation, instance.state) {
        (OperationKind::Initialize, _) => Some(PublicErrorCode::AlreadyInitialized),
        (OperationKind::Open, LifecycleState::Uninitialized)
        | (OperationKind::Close, LifecycleState::Uninitialized) => {
            Some(PublicErrorCode::NotInitialized)
        }
        (OperationKind::Close, LifecycleState::InitializedClosed) => {
            Some(PublicErrorCode::SurfaceNotOpen)
        }
        _ => Some(PublicErrorCode::InternalFailure),
    }
}

fn accept(
    runtime: &mut Runtime,
    handle: InstanceHandle,
    kind: OperationKind,
    payload: Vec<u8>,
    geometry: Option<SurfaceGeometry>,
) -> CommandOutcome {
    let prior_state = runtime.instances[&handle].state;
    accept_with_prior(runtime, handle, kind, payload, geometry, prior_state)
}

fn accept_with_prior(
    runtime: &mut Runtime,
    handle: InstanceHandle,
    kind: OperationKind,
    payload: Vec<u8>,
    geometry: Option<SurfaceGeometry>,
    prior_state: LifecycleState,
) -> CommandOutcome {
    let operation_id = u32::try_from(runtime.next_operation).expect("operation ID exhausted");
    let generation = runtime.instances[&handle].generation;
    let operation =
        OperationHandle((u64::from(generation) << 32) | u64::from(operation_id));
    runtime.next_operation = runtime.next_operation.checked_add(1).expect("operation ID exhausted");
    let instance = runtime.instances.get_mut(&handle).expect("validated instance");
    instance.in_flight = Some(InFlight {
        operation,
        generation,
        kind,
        prior_state,
    });
    if kind == OperationKind::Dispose {
        instance.state = LifecycleState::Disposing;
    }
    CommandOutcome::accepted(BackendCommand {
        instance: handle,
        operation,
        generation,
        kind,
        payload,
        geometry,
    })
}

fn apply_completion(
    runtime: &mut Runtime,
    handle: InstanceHandle,
    flight: &InFlight,
    code: PublicErrorCode,
) {
    let instance = runtime.instances.get_mut(&handle).expect("active instance");
    instance.in_flight = None;
    let success = code == PublicErrorCode::Ok;
    instance.state = match flight.kind {
        OperationKind::Initialize => {
            if success {
                LifecycleState::InitializedClosed
            } else {
                LifecycleState::Uninitialized
            }
        }
        OperationKind::Open => {
            if success {
                LifecycleState::SurfaceOpen
            } else if code == PublicErrorCode::HostLost {
                LifecycleState::InitializedClosed
            } else {
                flight.prior_state
            }
        }
        OperationKind::Close => {
            if success || code == PublicErrorCode::HostLost {
                LifecycleState::InitializedClosed
            } else {
                LifecycleState::SurfaceOpen
            }
        }
        OperationKind::Dispose => LifecycleState::Disposed,
    };
    if code == PublicErrorCode::InternalFailure && flight.kind != OperationKind::Dispose {
        instance.state = LifecycleState::Invalidated;
    }
    let release_lease = matches!(
        (flight.kind, instance.state),
        (OperationKind::Open, LifecycleState::InitializedClosed)
            | (OperationKind::Close, LifecycleState::InitializedClosed)
            | (OperationKind::Dispose, LifecycleState::Disposed)
    ) || instance.state == LifecycleState::Invalidated;
    if release_lease && runtime.surface_lease == Some(handle) {
        runtime.surface_lease = None;
    }
}

fn valid_url(bytes: &[u8]) -> bool {
    if bytes.is_empty() || bytes.len() > MAX_URL_BYTES {
        return false;
    }
    let Ok(url) = std::str::from_utf8(bytes) else {
        return false;
    };
    if url.bytes().any(|byte| byte.is_ascii_control() || byte.is_ascii_whitespace()) {
        return false;
    }
    let remainder = url
        .strip_prefix("https://")
        .or_else(|| url.strip_prefix("http://"));
    let Some(remainder) = remainder else {
        return false;
    };
    let authority = remainder
        .split(['/', '?', '#'])
        .next()
        .unwrap_or_default();
    !authority.is_empty() && authority != "." && authority != ".."
}

fn sanitize_diagnostic(value: &str) -> String {
    if value.len() <= MAX_DIAGNOSTIC_BYTES {
        return value.to_owned();
    }
    let mut end = MAX_DIAGNOSTIC_BYTES;
    while !value.is_char_boundary(end) {
        end -= 1;
    }
    value[..end].to_owned()
}
