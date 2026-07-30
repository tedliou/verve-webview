use verve_webview_core::{
    BackendCommand, BackendCompletion, Core, InstanceHandle, LifecycleState, OperationKind,
    PublicErrorCode, SurfaceGeometry, MAX_DIAGNOSTIC_BYTES,
};
use std::sync::{Arc, Barrier};
use std::thread;

fn initialize(core: &Core, instance: InstanceHandle) {
    let command = core
        .initialize(instance, b"{}")
        .command
        .expect("initialize accepted");
    assert!(core.complete(BackendCompletion::success(&command)).is_some());
}

fn open(core: &Core, instance: InstanceHandle) -> BackendCommand {
    core.open(instance, b"https://example.com/path", None)
        .command
        .expect("open accepted")
}

fn completion(command: &BackendCommand, code: PublicErrorCode) -> BackendCompletion {
    BackendCompletion {
        instance: command.instance,
        operation: command.operation,
        generation: command.generation,
        code,
        diagnostic_detail: None,
    }
}

#[test]
fn initialize_completes_once_and_enters_initialized_closed() {
    let core = Core::new();
    let instance = core.create_instance();

    let accepted = core.initialize(instance, b"{}");
    assert_eq!(accepted.code, PublicErrorCode::Ok);
    let command = accepted.command.expect("initialize must dispatch backend work");
    assert_eq!(command.kind, OperationKind::Initialize);

    let event = core
        .complete(BackendCompletion::success(&command))
        .expect("accepted operation must complete exactly once");
    assert_eq!(event.code, PublicErrorCode::Ok);
    assert_eq!(
        core.lifecycle_state(instance),
        Some(LifecycleState::InitializedClosed)
    );

    assert!(core.complete(BackendCompletion::success(&command)).is_none());
    assert_eq!(core.drain_diagnostics().len(), 1);
}

#[test]
fn invalid_input_is_rejected_before_backend_work_and_preserves_state() {
    let core = Core::new();
    let instance = core.create_instance();

    assert_eq!(
        core.initialize(instance, &[0xff]).code,
        PublicErrorCode::InvalidOptions
    );
    assert_eq!(
        core.open(instance, b"file:///secret", None).code,
        PublicErrorCode::NotInitialized
    );
    initialize(&core, instance);
    assert_eq!(
        core.open(instance, b"file:///secret", None).code,
        PublicErrorCode::InvalidUrl
    );
    assert_eq!(
        core.open(
            instance,
            b"https://example.com",
            Some(SurfaceGeometry {
                x: 0.0,
                y: 0.0,
                width: f64::NAN,
                height: 1.0,
            }),
        )
        .code,
        PublicErrorCode::InvalidGeometry
    );
    assert_eq!(
        core.lifecycle_state(instance),
        Some(LifecycleState::InitializedClosed)
    );
}

#[test]
fn strict_single_flight_rejects_overlap_without_queueing() {
    let core = Core::new();
    let instance = core.create_instance();
    let initializing = core.initialize(instance, b"{}").command.unwrap();

    assert_eq!(
        core.initialize(instance, b"{}").code,
        PublicErrorCode::OperationInProgress
    );
    assert_eq!(
        core.open(instance, b"https://example.com", None).code,
        PublicErrorCode::OperationInProgress
    );
    assert_eq!(
        core.close(instance).code,
        PublicErrorCode::OperationInProgress
    );
    assert!(core
        .complete(BackendCompletion::success(&initializing))
        .is_some());
}

#[test]
fn close_failure_preserves_surface_and_success_releases_lease() {
    let core = Core::new();
    let first = core.create_instance();
    let second = core.create_instance();
    initialize(&core, first);
    initialize(&core, second);

    let first_open = open(&core, first);
    core.complete(BackendCompletion::success(&first_open));
    let failed_close = core.close(first).command.unwrap();
    core.complete(completion(
        &failed_close,
        PublicErrorCode::BackendFailure,
    ));
    assert_eq!(
        core.lifecycle_state(first),
        Some(LifecycleState::SurfaceOpen)
    );
    assert_eq!(
        core.open(second, b"https://example.com", None).code,
        PublicErrorCode::SurfaceInUse
    );

    let successful_close = core.close(first).command.unwrap();
    core.complete(BackendCompletion::success(&successful_close));
    assert!(core
        .open(second, b"https://example.com", None)
        .command
        .is_some());
}

#[test]
fn dispose_preempts_work_and_stale_completion_cannot_release_lease() {
    let core = Core::new();
    let first = core.create_instance();
    let second = core.create_instance();
    initialize(&core, first);
    initialize(&core, second);
    let opening = open(&core, first);

    let disposing = core.dispose(first).command.expect("dispose accepted");
    assert_eq!(
        core.open(first, b"https://example.com", None).code,
        PublicErrorCode::Disposed
    );
    assert!(core.complete(BackendCompletion::success(&opening)).is_none());
    assert_eq!(
        core.open(second, b"https://example.com", None).code,
        PublicErrorCode::SurfaceInUse
    );

    let dispose_event = core
        .complete(completion(&disposing, PublicErrorCode::CleanupFailed))
        .expect("dispose completes even when cleanup fails");
    assert_eq!(dispose_event.code, PublicErrorCode::CleanupFailed);
    assert_eq!(
        core.lifecycle_state(first),
        Some(LifecycleState::Disposed)
    );
    assert!(core
        .open(second, b"https://example.com", None)
        .command
        .is_some());
}

#[test]
fn competing_concurrent_opens_observe_one_application_surface_lease() {
    let core = Arc::new(Core::new());
    let first = core.create_instance();
    let second = core.create_instance();
    initialize(&core, first);
    initialize(&core, second);
    let barrier = Arc::new(Barrier::new(3));

    let attempts: Vec<_> = [first, second]
        .into_iter()
        .map(|instance| {
            let core = Arc::clone(&core);
            let barrier = Arc::clone(&barrier);
            thread::spawn(move || {
                barrier.wait();
                core.open(instance, b"https://example.com", None).code
            })
        })
        .collect();
    barrier.wait();
    let codes: Vec<_> = attempts
        .into_iter()
        .map(|attempt| attempt.join().unwrap())
        .collect();
    assert_eq!(
        codes
            .iter()
            .filter(|code| **code == PublicErrorCode::Ok)
            .count(),
        1
    );
    assert_eq!(
        codes
            .iter()
            .filter(|code| **code == PublicErrorCode::SurfaceInUse)
            .count(),
        1
    );
}

#[test]
fn diagnostic_detail_is_truncated_at_a_utf8_boundary() {
    let core = Core::new();
    let instance = core.create_instance();
    let command = core.initialize(instance, b"{}").command.unwrap();
    let event = core
        .complete(BackendCompletion {
            instance,
            operation: command.operation,
            generation: command.generation,
            code: PublicErrorCode::BackendFailure,
            diagnostic_detail: Some("é".repeat(MAX_DIAGNOSTIC_BYTES)),
        })
        .unwrap();
    let detail = event.diagnostic_detail.unwrap();
    assert!(detail.len() <= MAX_DIAGNOSTIC_BYTES);
    assert!(detail.is_char_boundary(detail.len()));
}

#[test]
fn host_loss_between_operations_fails_closed_and_releases_lease() {
    let core = Core::new();
    let first = core.create_instance();
    let second = core.create_instance();
    initialize(&core, first);
    initialize(&core, second);
    let command = open(&core, first);
    core.complete(BackendCompletion::success(&command));

    core.report_host_lost(first);
    assert_eq!(
        core.lifecycle_state(first),
        Some(LifecycleState::InitializedClosed)
    );
    assert_eq!(
        core.close(first).code,
        PublicErrorCode::SurfaceNotOpen
    );
    assert!(core
        .open(second, b"https://example.com", None)
        .command
        .is_some());
}
