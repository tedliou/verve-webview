# Verve WebView SDK

A cross-engine WebView SDK whose shared behavior is separated from game-engine integration and platform-specific rendering.

## Language

**WebView Core**:
The engine- and platform-neutral SDK contract, state, and lifecycle semantics shared by every supported runtime.
_Avoid_: WebView Web, common WebView, shared WebView

**Engine Adapter**:
An integration boundary that presents WebView Core to a specific game engine and translates engine lifecycle and messaging conventions.
_Avoid_: engine backend, WebView Web Unity, WebView Web Godot

**Platform Backend**:
An implementation boundary that provides WebView behavior for a target operating system or browser environment.
_Avoid_: engine adapter, native module

**Example App**:
A runnable engine project used to demonstrate and verify the SDK without owning reusable SDK behavior.
_Avoid_: SDK module, engine implementation

**Repository Module**:
A top-level reusable SDK unit with its own source, documentation, and Bazel package boundary.
_Avoid_: build target, distribution

**Binding Target**:
A consistently named, platform-specific build unit inside an engine Repository Module that connects an Engine Adapter to one Platform Backend.
_Avoid_: platform module, engine-platform package

**Engine SDK Distribution**:
The single installable SDK delivered for one game engine, aggregating that engine's adapter and all supported platform bindings.
_Avoid_: platform package, binding target

**Release Candidate**:
The immutable, checksummed set of Unity and Godot Engine SDK Distribution artifacts proposed for one SDK version and awaiting complete release evidence.
_Avoid_: release build, staging build, candidate rebuild

**Release Evidence**:
Machine-readable proof that identifies one Release Candidate by artifact digests and records the exact environment and outcome of a required verification gate.
_Avoid_: CI log, test report, release note

**Release Promotion**:
The explicitly authorized transition of a fully verified Release Candidate into the stable public release without rebuilding or changing its artifacts.
_Avoid_: release build, republish, deploy

**Withdrawn Release**:
An immutable published SDK version that remains addressable but is explicitly disqualified from new use after a serious defect or security issue.
_Avoid_: deleted release, rolled-back release, replaced tag

**SDK Instance**:
An independently initialized owner of at most one WebView Surface, remaining reusable after close until it is disposed.
_Avoid_: global WebView, browser process

**WebView Surface**:
A rectangular browser UI layered over the game view, optionally bounded by an engine-provided rectangle and never rendered as a 3D texture.
_Avoid_: browser tab, render texture, WebView window

**Host Locator**:
A non-owning binding capability that resolves the engine's currently valid host for a WebView Surface.
_Avoid_: host pointer, owned host view

**Surface Lease**:
The application-scoped exclusive claim held by the SDK Instance whose WebView Surface is open or still being removed.
_Avoid_: global WebView, surface lock

**Close**:
The reversible end of a WebView Surface's visibility while preserving its SDK Instance for a later open.
_Avoid_: dispose, destroy SDK

**Dispose**:
The terminal release of an SDK Instance and all resources it owns.
_Avoid_: close, hide

**Untrusted Web Content**:
Any document, redirect destination, or embedded frame loaded by a WebView Surface, including application-owned origins; it receives ordinary browser sandbox capabilities but no implicit native, engine, or platform privilege from the SDK.
_Avoid_: trusted app page, privileged origin

**Web Runtime**:
A supported desktop browser environment in which an exported Unity WebGL or Godot Web application runs, independent of whether its host operating system has a native Platform Backend.
_Avoid_: native Linux support, native macOS support, browser backend

**Public Error Code**:
A stable, engine- and platform-neutral failure classification whose meaning allows an SDK caller to choose a recovery action.
_Avoid_: native error code, diagnostic message

**Diagnostic Detail**:
Non-contractual platform or runtime failure information provided for investigation and logging, never for application control flow.
_Avoid_: public error code, portable error

**WebView Result**:
The engine-idiomatic representation of one completed SDK operation, containing success status, one Public Error Code, and optional Diagnostic Detail with identical semantics across Engine Adapters.
_Avoid_: exception, native result, platform response

**API Contract**:
The versioned, machine-readable definition of WebView Core operations, lifecycle effects, WebView Result semantics, and Public Error Codes from which engine interfaces, reference documentation, and conformance data are generated or verified.
_Avoid_: handwritten API docs, ABI specification, engine-specific contract
