//! PROTOTYPE ONLY: minimum browser Core state needed to probe engine transport.

use std::cell::RefCell;
use std::collections::BTreeMap;
use wasm_bindgen::prelude::*;

#[derive(Clone, Copy, PartialEq)]
enum InstanceState {
    Ready,
    Open,
    Closed,
    Disposed,
}

thread_local! {
    static INSTANCES: RefCell<BTreeMap<u32, InstanceState>> = RefCell::new(BTreeMap::new());
    static NEXT_HANDLE: RefCell<u32> = const { RefCell::new(1) };
}

fn result(ok: bool, code: &str, handle: u32, generation: u32) -> String {
    format!(
        "{{\"ok\":{},\"code\":\"{}\",\"handle\":{},\"generation\":{}}}",
        ok, code, handle, generation
    )
}

#[wasm_bindgen]
pub fn create_instance() -> u32 {
    let handle = NEXT_HANDLE.with(|next| {
        let handle = *next.borrow();
        *next.borrow_mut() = handle.checked_add(1).expect("prototype handle overflow");
        handle
    });
    INSTANCES.with(|instances| {
        instances.borrow_mut().insert(handle, InstanceState::Ready);
    });
    handle
}

#[wasm_bindgen]
pub fn request(handle: u32, operation: &str, generation: u32) -> String {
    INSTANCES.with(|instances| {
        let mut instances = instances.borrow_mut();
        let Some(state) = instances.get_mut(&handle) else {
            return result(false, "invalid_handle", handle, generation);
        };

        if *state == InstanceState::Disposed {
            return result(false, "disposed_instance", handle, generation);
        }

        match operation {
            "open" if matches!(*state, InstanceState::Ready | InstanceState::Closed) => {
                *state = InstanceState::Open;
                result(true, "accepted", handle, generation)
            }
            "close" if *state == InstanceState::Open => {
                *state = InstanceState::Closed;
                result(true, "accepted", handle, generation)
            }
            "dispose" => {
                *state = InstanceState::Disposed;
                result(true, "disposed", handle, generation)
            }
            "open" | "close" => result(false, "invalid_state", handle, generation),
            _ => result(false, "unknown_operation", handle, generation),
        }
    })
}

#[wasm_bindgen]
pub fn prototype_trap() {
    panic!("intentional prototype trap");
}
