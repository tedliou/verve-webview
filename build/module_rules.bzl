"""Private implementations behind the canonical Repository Module interfaces."""

load(
    "//build:providers.bzl",
    "ApiContractInfo",
    "CorePayloadInfo",
    "DistributionFragmentInfo",
    "PlatformBackendInfo",
)
load("//build:release_version.bzl", "ReleaseVersionInfo")

def _core_payload_impl(ctx):
    contract = ctx.attr.api_contract[ApiContractInfo]
    return [
        DefaultInfo(),
        CorePayloadInfo(
            transport = ctx.attr.transport,
            payloads = {},
            abi_metadata = None,
            conformance = contract.conformance,
        ),
    ]

core_payload = rule(
    implementation = _core_payload_impl,
    attrs = {
        "api_contract": attr.label(
            mandatory = True,
            providers = [ApiContractInfo],
        ),
        "transport": attr.string(
            mandatory = True,
            values = ["native", "web"],
        ),
    },
)

def _platform_backend_impl(ctx):
    core = ctx.attr.core[CorePayloadInfo]
    if core.transport != ctx.attr.required_transport:
        fail("%s backend requires the %s Core transport" % (
            ctx.attr.platform,
            ctx.attr.required_transport,
        ))
    return [
        DefaultInfo(files = depset([ctx.file.runtime_metadata])),
        PlatformBackendInfo(
            platform = ctx.attr.platform,
            payloads = {},
            runtime_metadata = ctx.file.runtime_metadata,
        ),
    ]

platform_backend = rule(
    implementation = _platform_backend_impl,
    attrs = {
        "core": attr.label(
            mandatory = True,
            providers = [CorePayloadInfo],
        ),
        "platform": attr.string(mandatory = True),
        "required_transport": attr.string(
            mandatory = True,
            values = ["native", "web"],
        ),
        "runtime_metadata": attr.label(
            mandatory = True,
            allow_single_file = [".json"],
        ),
    },
)

def _fragment_impl(ctx):
    platform = ctx.attr.platform
    if ctx.attr.api_contract:
        ctx.attr.api_contract[ApiContractInfo]
    if ctx.attr.adapter:
        ctx.attr.adapter[DistributionFragmentInfo]
    if ctx.attr.backend:
        backend = ctx.attr.backend[PlatformBackendInfo]
        if backend.platform != platform:
            fail("%s binding cannot consume the %s backend" % (platform, backend.platform))

    version = ctx.attr._release_version[ReleaseVersionInfo].value
    content_manifest = ctx.actions.declare_file(ctx.label.name + ".content-manifest.json")
    fragment_manifest = ctx.actions.declare_file(ctx.label.name + ".fragment-manifest.json")
    ctx.actions.write(
        content_manifest,
        "{\"entries\":[],\"schema_version\":1}\n",
    )
    ctx.actions.write(
        fragment_manifest,
        (
            "{\"architecture\":\"skeleton\",\"fragment_id\":\"%s\","
            + "\"platform\":\"%s\",\"release_version\":\"%s\","
            + "\"schema_version\":1}\n"
        ) % (ctx.label.name, platform, version),
    )
    return [
        DefaultInfo(files = depset([content_manifest, fragment_manifest])),
        DistributionFragmentInfo(
            entries = depset(),
            compatibility = ctx.file.compatibility,
            content_manifest = content_manifest,
            fragment_manifest = fragment_manifest,
        ),
    ]

distribution_fragment = rule(
    implementation = _fragment_impl,
    attrs = {
        "platform": attr.string(mandatory = True),
        "compatibility": attr.label(
            mandatory = True,
            allow_single_file = [".json"],
        ),
        "api_contract": attr.label(providers = [ApiContractInfo]),
        "adapter": attr.label(providers = [DistributionFragmentInfo]),
        "backend": attr.label(providers = [PlatformBackendInfo]),
        "_release_version": attr.label(
            default = "//build:release_version",
            providers = [ReleaseVersionInfo],
        ),
    },
)

def _sdk_impl(ctx):
    version = ctx.attr.release_version[ReleaseVersionInfo].value
    if version == "UNSET":
        fail("//build:release_version is required for an Engine SDK Distribution")

    transitioned = []
    for name, configured_targets in [
        ("android", ctx.attr.android),
        ("ios", ctx.attr.ios),
        ("windows", ctx.attr.windows),
        ("web", ctx.attr.web),
    ]:
        if len(configured_targets) != 1:
            fail("%s must resolve to exactly one transitioned fragment" % name)
        transitioned.append(configured_targets[0][DistributionFragmentInfo])

    fragments = [ctx.attr.adapter[DistributionFragmentInfo]] + transitioned
    compatibility = fragments[0].compatibility
    for fragment in fragments[1:]:
        if fragment.compatibility != compatibility:
            fail("all fragments must use the same compatibility.json label")

    marker = ctx.actions.declare_file(ctx.label.name + ".skeleton.txt")
    ctx.actions.write(
        marker,
        "release-only distribution skeleton for %s %s\n" % (ctx.attr.engine, version),
    )
    return [DefaultInfo(files = depset([marker]))]

def _platform_transition(platform):
    def _impl(_settings, _attr):
        return {"//command_line_option:platforms": platform}
    return transition(
        implementation = _impl,
        inputs = [],
        outputs = ["//command_line_option:platforms"],
    )

_android_transition = _platform_transition("//build/platforms:release_android_arm64")
_ios_transition = _platform_transition("//build/platforms:release_ios_xcframework")
_windows_transition = _platform_transition("//build/platforms:release_windows_x86_64")
_web_transition = _platform_transition("//build/platforms:release_web_wasm32")

engine_sdk_distribution = rule(
    implementation = _sdk_impl,
    attrs = {
        "engine": attr.string(mandatory = True, values = ["unity", "godot"]),
        "adapter": attr.label(
            mandatory = True,
            providers = [DistributionFragmentInfo],
        ),
        "android": attr.label(
            mandatory = True,
            providers = [DistributionFragmentInfo],
            cfg = _android_transition,
        ),
        "ios": attr.label(
            mandatory = True,
            providers = [DistributionFragmentInfo],
            cfg = _ios_transition,
        ),
        "windows": attr.label(
            mandatory = True,
            providers = [DistributionFragmentInfo],
            cfg = _windows_transition,
        ),
        "web": attr.label(
            mandatory = True,
            providers = [DistributionFragmentInfo],
            cfg = _web_transition,
        ),
        "release_version": attr.label(
            mandatory = True,
            providers = [ReleaseVersionInfo],
        ),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
)
