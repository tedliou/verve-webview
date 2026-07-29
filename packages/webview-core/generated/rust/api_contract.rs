// @generated from api-contract.yaml; do not edit.

#[repr(u32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PublicErrorCode {
    Ok = 0,
    InvalidOptions = 100,
    InvalidUrl = 101,
    InvalidGeometry = 102,
    NotInitialized = 200,
    AlreadyInitialized = 201,
    OperationInProgress = 202,
    Disposed = 203,
    SurfaceNotOpen = 204,
    SurfaceInUse = 205,
    HostUnavailable = 300,
    HostLost = 301,
    BackendFailure = 302,
    CleanupFailed = 303,
    CoreLoadFailed = 400,
    AbiMismatch = 401,
    RuntimeUnavailable = 402,
    UnsupportedEnvironment = 403,
    DistributionInvalid = 404,
    InternalFailure = 500,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WebViewResult {
    pub code: PublicErrorCode,
    pub diagnostic_detail: Option<String>,
}

impl WebViewResult {
    pub fn is_success(&self) -> bool { self.code == PublicErrorCode::Ok }
}

pub const OPERATIONS: &[&str] = &["initialize", "open", "close", "dispose"];
