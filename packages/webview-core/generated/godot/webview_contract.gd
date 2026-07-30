# @generated from api-contract.yaml; do not edit.
class_name WebViewResult
extends RefCounted

enum ErrorCode {
  OK = 0,
  INVALID_OPTIONS = 100,
  INVALID_URL = 101,
  INVALID_GEOMETRY = 102,
  NOT_INITIALIZED = 200,
  ALREADY_INITIALIZED = 201,
  OPERATION_IN_PROGRESS = 202,
  DISPOSED = 203,
  SURFACE_NOT_OPEN = 204,
  SURFACE_IN_USE = 205,
  HOST_UNAVAILABLE = 300,
  HOST_LOST = 301,
  BACKEND_FAILURE = 302,
  CLEANUP_FAILED = 303,
  CORE_LOAD_FAILED = 400,
  ABI_MISMATCH = 401,
  RUNTIME_UNAVAILABLE = 402,
  UNSUPPORTED_ENVIRONMENT = 403,
  DISTRIBUTION_INVALID = 404,
  INTERNAL_FAILURE = 500,
}

var _code: ErrorCode
var _diagnostic_detail: String

var code: ErrorCode:
  get: return _code
  set(_value): push_error("WebViewResult.code is read-only.")
var diagnostic_detail: String:
  get: return _diagnostic_detail
  set(_value): push_error("WebViewResult.diagnostic_detail is read-only.")
var is_success: bool:
  get: return _code == ErrorCode.OK
  set(_value): push_error("WebViewResult.is_success is read-only.")

func _init(value: ErrorCode, detail: String = ""):
  _code = value
  _diagnostic_detail = detail
