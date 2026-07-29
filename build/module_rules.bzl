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
    payload_files = depset(transitive = [
        target[DefaultInfo].files
        for target in ctx.attr.payloads
    ])
    return [
        DefaultInfo(files = depset(
            direct = [ctx.file.abi_metadata] if ctx.file.abi_metadata else [],
            transitive = [payload_files],
        )),
        CorePayloadInfo(
            transport = ctx.attr.transport,
            payloads = {ctx.attr.transport: payload_files},
            abi_metadata = ctx.file.abi_metadata,
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
        # Core source is platform-neutral, but final native archive linking
        # belongs to each later Binding Target's registered platform toolchain.
        # Build the implementation here in exec configuration so skeleton
        # transitions validate it without pretending a target linker exists.
        "payloads": attr.label_list(cfg = "exec"),
        "abi_metadata": attr.label(allow_single_file = [".json"]),
    },
)

def _platform_backend_impl(ctx):
    core = ctx.attr.core[CorePayloadInfo]
    if core.transport != ctx.attr.required_transport:
        fail("%s backend requires the %s Core transport" % (
            ctx.attr.platform,
            ctx.attr.required_transport,
        ))
    if len(ctx.attr.payloads) != len(ctx.attr.payload_keys):
        fail("payloads and payload_keys must have identical lengths")
    if len(ctx.attr.payload_keys) != len({key: True for key in ctx.attr.payload_keys}):
        fail("Platform Backend payload keys must be unique")
    payloads = dict(core.payloads) if core.transport == "web" else {}
    for key, target in zip(ctx.attr.payload_keys, ctx.attr.payloads):
        if key in payloads:
            fail("Platform Backend payload key collides with Core payload: %s" % key)
        payloads[key] = target[DefaultInfo].files
    payload_files = depset(transitive = payloads.values())
    return [
        DefaultInfo(files = depset(
            direct = [ctx.file.runtime_metadata],
            transitive = [payload_files],
        )),
        PlatformBackendInfo(
            platform = ctx.attr.platform,
            payloads = payloads,
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
        # Platform-specific compiler helpers retain their native providers and
        # produce packaging payloads in execution configuration. The canonical
        # Backend label remains target-compatible with the logical platform
        # without pretending every host has a target C/C++ toolchain.
        "payloads": attr.label_list(cfg = "exec"),
        "payload_keys": attr.string_list(),
    },
)

def _platform_backend_payload_manifest_impl(ctx):
    backend = ctx.attr.backend[PlatformBackendInfo]
    output = ctx.actions.declare_file(ctx.label.name + ".txt")
    lines = ["platform=" + backend.platform]
    payload_sets = []
    for key in sorted(backend.payloads.keys()):
        lines.append("payload=" + key)
        payload_sets.append(backend.payloads[key])
    ctx.actions.write(output, "\n".join(lines) + "\n")
    return [DefaultInfo(files = depset(
        direct = [output, backend.runtime_metadata],
        transitive = payload_sets,
    ))]

platform_backend_payload_manifest = rule(
    implementation = _platform_backend_payload_manifest_impl,
    attrs = {
        "backend": attr.label(
            mandatory = True,
            providers = [PlatformBackendInfo],
        ),
    },
)

def _fragment_impl(ctx):
    platform = ctx.attr.platform
    entry_sets = []
    if ctx.attr.api_contract:
        ctx.attr.api_contract[ApiContractInfo]
    if ctx.attr.adapter:
        ctx.attr.adapter[DistributionFragmentInfo]
    if ctx.attr.backend:
        backend = ctx.attr.backend[PlatformBackendInfo]
        if backend.platform != platform:
            fail("%s binding cannot consume the %s backend" % (platform, backend.platform))
        entry_sets.extend(backend.payloads.values())

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
    entries = depset(transitive = entry_sets)
    return [
        DefaultInfo(files = depset(
            direct = [content_manifest, fragment_manifest],
            transitive = [entries],
        )),
        DistributionFragmentInfo(
            entries = entries,
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

def _web_identity_transition_impl(_settings, _attr):
    return {"//command_line_option:platforms": "//build/platforms:release_web_wasm32"}

_web_identity_transition = transition(
    implementation = _web_identity_transition_impl,
    inputs = [],
    outputs = ["//command_line_option:platforms"],
)

def _web_core_consumer_identity_impl(ctx):
    if len(ctx.attr.unity) != 1 or len(ctx.attr.godot) != 1:
        fail("each Web binding must resolve to exactly one configured target")
    unity_info = ctx.attr.unity[0][DistributionFragmentInfo]
    godot_info = ctx.attr.godot[0][DistributionFragmentInfo]
    unity_entries = unity_info.entries.to_list()
    godot_entries = godot_info.entries.to_list()
    unity_paths = sorted([file.path for file in unity_entries])
    godot_paths = sorted([file.path for file in godot_entries])
    if unity_paths != godot_paths:
        fail("Unity and Godot binding_web targets do not consume identical Core files")
    if len(unity_paths) != ctx.attr.expected_payload_count:
        fail("expected %d shared Web Core payloads, found %d" % (
            ctx.attr.expected_payload_count,
            len(unity_paths),
        ))

    manifest = ctx.actions.declare_file(ctx.label.name + ".txt")
    ctx.actions.write(
        manifest,
        "\n".join(unity_paths) + "\n",
    )
    return [DefaultInfo(
        files = depset(
            direct = [manifest],
            transitive = [
                unity_info.entries,
                godot_info.entries,
            ],
        ),
    )]

web_core_consumer_identity = rule(
    implementation = _web_core_consumer_identity_impl,
    attrs = {
        "unity": attr.label(
            mandatory = True,
            providers = [DistributionFragmentInfo],
            cfg = _web_identity_transition,
        ),
        "godot": attr.label(
            mandatory = True,
            providers = [DistributionFragmentInfo],
            cfg = _web_identity_transition,
        ),
        "expected_payload_count": attr.int(mandatory = True),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
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
