load("//build:module_rules.bzl", "platform_backend")
load("//build:providers.bzl", "CorePayloadInfo")

def _web_core_transition_impl(_settings, _attr):
    return {"//command_line_option:platforms": "//build/platforms:release_web_wasm32"}

_web_core_transition = transition(
    implementation = _web_core_transition_impl,
    inputs = [],
    outputs = ["//command_line_option:platforms"],
)

def _web_core_test_payload_impl(ctx):
    if len(ctx.attr.core) != 1:
        fail("Web Core test payload must resolve to one configured target")
    core = ctx.attr.core[0][CorePayloadInfo]
    if core.transport != "web":
        fail("Web Backend tests require the Web Core transport")
    return [DefaultInfo(files = depset(transitive = core.payloads.values()))]

web_core_test_payload = rule(
    implementation = _web_core_test_payload_impl,
    attrs = {
        "core": attr.label(
            mandatory = True,
            providers = [CorePayloadInfo],
            cfg = _web_core_transition,
        ),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
)

def web_backend(name, core, runtime, runtime_metadata, visibility):
    platform_backend(
        name = name,
        core = core,
        platform = "web",
        payload_keys = ["backend_runtime"],
        payloads = [runtime],
        required_transport = "web",
        runtime_metadata = runtime_metadata,
        target_compatible_with = ["//build/platforms:web"],
        visibility = visibility,
    )
