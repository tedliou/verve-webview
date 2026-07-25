"""Pure model for the throwaway canonical Bazel package prototype."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    name: str
    rule: str
    role: str
    deps: tuple[str, ...] = ()
    visibility: str = "private"
    compatible_with: tuple[str, ...] = ()
    produces_fragment: bool = False


@dataclass(frozen=True)
class Module:
    key: str
    package: str
    kind: str
    targets: tuple[Target, ...]


ENGINE_INTERNAL = "//visibility:private"
BACKEND_CONSUMERS = "//build/visibility:backend_consumers"
CORE_CONSUMERS = "//build/visibility:core_consumers"
PUBLIC = "//visibility:public"


def _binding(name: str, platform: str, backend: str) -> Target:
    constraint = {
        "android": "@platforms//os:android",
        "ios": "@platforms//os:ios",
        "windows": "@platforms//os:windows",
        "web": "//build/platforms:web",
    }[platform]
    return Target(
        name=name,
        rule="engine_binding",
        role=f"Compose the Engine Adapter with the {platform} Platform Backend.",
        deps=("adapter", backend),
        visibility=ENGINE_INTERNAL,
        compatible_with=(constraint,),
        produces_fragment=True,
    )


def _engine(key: str) -> Module:
    package = f"//packages/webview-{key}"
    return Module(
        key=key,
        package=package,
        kind="engine",
        targets=(
            Target(
                "adapter",
                f"{key}_adapter",
                "Translate the public SDK Interface and engine conventions.",
                deps=("//packages/webview-core:api_contract",),
                visibility=ENGINE_INTERNAL,
                produces_fragment=True,
            ),
            _binding(
                "binding_android",
                "android",
                "//packages/webview-android:backend",
            ),
            _binding(
                "binding_ios",
                "ios",
                "//packages/webview-ios:backend",
            ),
            _binding(
                "binding_windows",
                "windows",
                "//packages/webview-windows:backend",
            ),
            _binding(
                "binding_web",
                "web",
                "//packages/webview-web:backend",
            ),
            Target(
                "sdk",
                "engine_sdk_distribution",
                "Verify and aggregate all fragments into one installable distribution.",
                deps=(
                    "adapter",
                    "binding_android",
                    "binding_ios",
                    "binding_windows",
                    "binding_web",
                ),
                visibility=PUBLIC,
                compatible_with=("//build/platforms:canonical_aggregation",),
                produces_fragment=False,
            ),
        ),
    )


MODULES = (
    Module(
        key="core",
        package="//packages/webview-core",
        kind="core",
        targets=(
            Target(
                "api_contract",
                "api_contract",
                "Validate api-contract.yaml and generate shared semantic sources.",
                visibility=CORE_CONSUMERS,
            ),
            Target(
                "core_native",
                "webview_core_native",
                "Implement the native Core transport and internal C ABI.",
                deps=("api_contract",),
                visibility=CORE_CONSUMERS,
            ),
            Target(
                "core_web",
                "webview_core_web",
                "Produce the engine-independent browser JavaScript/Wasm Core bundle.",
                deps=("api_contract",),
                visibility=CORE_CONSUMERS,
                compatible_with=("//build/platforms:web",),
            ),
        ),
    ),
    Module(
        key="android",
        package="//packages/webview-android",
        kind="backend",
        targets=(
            Target(
                "backend",
                "android_backend",
                "Build the shared Android Platform Backend AAR payload.",
                deps=("//packages/webview-core:core_native",),
                visibility=BACKEND_CONSUMERS,
                compatible_with=("@platforms//os:android",),
            ),
        ),
    ),
    Module(
        key="ios",
        package="//packages/webview-ios",
        kind="backend",
        targets=(
            Target(
                "backend",
                "ios_backend",
                "Build device and simulator XCFramework payloads.",
                deps=("//packages/webview-core:core_native",),
                visibility=BACKEND_CONSUMERS,
                compatible_with=("@platforms//os:ios",),
            ),
        ),
    ),
    Module(
        key="windows",
        package="//packages/webview-windows",
        kind="backend",
        targets=(
            Target(
                "backend",
                "windows_backend",
                "Build the x86_64 WebView2 Platform Backend DLL.",
                deps=("//packages/webview-core:core_native",),
                visibility=BACKEND_CONSUMERS,
                compatible_with=(
                    "@platforms//os:windows",
                    "@platforms//cpu:x86_64",
                ),
            ),
        ),
    ),
    Module(
        key="web",
        package="//packages/webview-web",
        kind="backend",
        targets=(
            Target(
                "backend",
                "web_backend",
                "Expose the shared browser Core bundle to thin engine Web adapters.",
                deps=("//packages/webview-core:core_web",),
                visibility=BACKEND_CONSUMERS,
                compatible_with=("//build/platforms:web",),
            ),
        ),
    ),
    _engine("unity"),
    _engine("godot"),
)


def target_label(module: Module, target: Target) -> str:
    return f"{module.package}:{target.name}"


def validate() -> tuple[str, ...]:
    errors: list[str] = []
    modules = {module.key: module for module in MODULES}
    if set(modules) != {
        "core",
        "android",
        "ios",
        "windows",
        "web",
        "unity",
        "godot",
    }:
        errors.append("Repository Module set is not the resolved seven-module set.")

    required_engine_targets = {
        "adapter",
        "binding_android",
        "binding_ios",
        "binding_windows",
        "binding_web",
        "sdk",
    }
    core = modules.get("core")
    if core and {target.name for target in core.targets} != {
        "api_contract",
        "core_native",
        "core_web",
    }:
        errors.append("WebView Core canonical Target set changed.")

    expected_backend_core = {
        "android": "//packages/webview-core:core_native",
        "ios": "//packages/webview-core:core_native",
        "windows": "//packages/webview-core:core_native",
        "web": "//packages/webview-core:core_web",
    }
    for module in MODULES:
        names = {target.name for target in module.targets}
        if module.kind == "engine" and names != required_engine_targets:
            errors.append(f"{module.key}: fixed Engine Target set changed.")
        for target in module.targets:
            if target.name != "sdk" and target.visibility == PUBLIC:
                errors.append(f"{target_label(module, target)} is unexpectedly public.")
            if target.name.startswith("binding_") and not target.produces_fragment:
                errors.append(f"{target_label(module, target)} lacks a fragment.")
            if module.kind == "engine" and target.name == "adapter":
                if target.deps != ("//packages/webview-core:api_contract",):
                    errors.append(f"{module.key}: Adapter bypasses API Contract.")
            if module.kind == "engine" and target.name == "sdk":
                if set(target.deps) != required_engine_targets - {"sdk"}:
                    errors.append(f"{module.key}: SDK fragment set changed.")
                if target.compatible_with != (
                    "//build/platforms:canonical_aggregation",
                ):
                    errors.append(f"{module.key}: SDK is not release-only.")
            if module.kind == "engine" and target.name.startswith("binding_"):
                platform = target.name.removeprefix("binding_")
                backend = f"//packages/webview-{platform}:backend"
                if set(target.deps) != {"adapter", backend}:
                    errors.append(
                        f"{module.key}:{target.name} is not the sole "
                        f"{platform} composition root."
                    )
            if module.kind == "backend":
                forbidden = ("webview-unity", "webview-godot")
                if any(name in dep for dep in target.deps for name in forbidden):
                    errors.append(f"{target_label(module, target)} depends on an engine.")
                if target.deps != (expected_backend_core[module.key],):
                    errors.append(f"{module.key}: Backend uses the wrong Core transport.")
            if module.kind == "core":
                forbidden = ("webview-unity", "webview-godot", "webview-android",
                             "webview-ios", "webview-windows", "webview-web")
                if any(name in dep for dep in target.deps for name in forbidden):
                    errors.append(f"{target_label(module, target)} depends outward.")
                if target.name in {"core_native", "core_web"}:
                    if target.deps != ("api_contract",):
                        errors.append(f"{target.name} bypasses API Contract.")
    return tuple(errors)
