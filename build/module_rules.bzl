"""Private implementations behind the canonical Repository Module interfaces."""

load(
    "//build:providers.bzl",
    "ApiContractInfo",
    "CorePayloadInfo",
    "DistributionFragmentInfo",
    "PlatformBackendInfo",
)
load("//build:release_version.bzl", "ReleaseVersionInfo")
load("@rules_pkg//pkg:providers.bzl", "PackageFilesInfo")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("@rules_pkg//pkg:zip.bzl", "pkg_zip")

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
    destinations = {}
    passthrough_sets = []

    def add(destination, files, origin):
        _validate_destination(destination)
        values = files.to_list()
        if len(values) != 1:
            fail("%s must expose exactly one file for %s" % (origin, destination))
        folded = destination.lower()
        if folded in [value.lower() for value in destinations.keys()]:
            fail("case-folded distribution destination collision: %s" % destination)
        destinations[destination] = values[0]

    for target, destination in ctx.attr.entries.items():
        add(destination, target[DefaultInfo].files, target.label)
    if ctx.attr.api_contract:
        contract = ctx.attr.api_contract[ApiContractInfo]
        if ctx.attr.api_contract_group:
            add(
                ctx.attr.api_contract_destination,
                getattr(contract, ctx.attr.api_contract_group),
                ctx.attr.api_contract.label,
            )
    if ctx.attr.adapter:
        ctx.attr.adapter[DistributionFragmentInfo]
    if ctx.attr.backend:
        backend = ctx.attr.backend[PlatformBackendInfo]
        if backend.platform != platform:
            fail("%s binding cannot consume the %s backend" % (platform, backend.platform))
        if not ctx.attr.backend_entries and not ctx.attr.backend_file_entries:
            passthrough_sets.extend(backend.payloads.values())
        for key, destination in ctx.attr.backend_entries.items():
            if key not in backend.payloads:
                fail("%s backend does not expose payload %s" % (platform, key))
            add(destination, backend.payloads[key], key)
        for selector, destination in ctx.attr.backend_file_entries.items():
            parts = selector.split("|")
            if len(parts) != 2 or parts[0] not in backend.payloads:
                fail("invalid Backend payload file selector: %s" % selector)
            matches = depset([
                file
                for file in backend.payloads[parts[0]].to_list()
                if file.basename == parts[1]
            ])
            add(destination, matches, selector)

    version = ctx.attr._release_version[ReleaseVersionInfo].value
    content_manifest = ctx.actions.declare_file(ctx.label.name + ".content-manifest.json")
    fragment_manifest = ctx.actions.declare_file(ctx.label.name + ".fragment-manifest.json")
    fragment_tree = ctx.actions.declare_directory(ctx.label.name + ".fragment-tree")
    spec = ctx.actions.declare_file(ctx.label.name + ".entries.tsv")
    ctx.actions.write(spec, "".join([
        "%s\t%s\n" % (destination, destinations[destination].path)
        for destination in sorted(destinations.keys())
    ]))
    ctx.actions.run(
        executable = ctx.executable._distribution_tool,
        arguments = [
            "fragment",
            "--spec",
            spec.path,
            "--content",
            content_manifest.path,
            "--tree",
            fragment_tree.path,
            "--provenance",
            fragment_manifest.path,
            "--fragment-id",
            ctx.label.name,
            "--platform",
            platform,
            "--architecture",
            ctx.attr.architecture,
            "--release-version",
            version,
        ],
        inputs = depset(
            direct = [spec],
            transitive = [depset(destinations.values())],
        ),
        outputs = [content_manifest, fragment_manifest, fragment_tree],
        mnemonic = "DistributionFragmentManifest",
    )
    entries = depset(
        direct = destinations.values(),
        transitive = passthrough_sets,
    )
    return [
        DefaultInfo(files = depset(
            direct = [content_manifest, fragment_manifest, fragment_tree],
            transitive = [entries],
        )),
        PackageFilesInfo(
            attributes = {"mode": "0644"},
            dest_src_map = destinations,
        ),
        DistributionFragmentInfo(
            entries = entries,
            destinations = destinations,
            compatibility = ctx.file.compatibility,
            content_manifest = content_manifest,
            fragment_manifest = fragment_manifest,
            release_version = version,
            verification = depset([content_manifest, fragment_manifest]),
        ),
    ]

def _fragment_import_impl(ctx):
    destinations = {}
    for target, destination in ctx.attr.entries.items():
        _validate_destination(destination)
        files = target[DefaultInfo].files.to_list()
        if len(files) != 1:
            fail("imported entry must expose exactly one file: %s" % target.label)
        if destination.lower() in [value.lower() for value in destinations.keys()]:
            fail("case-folded imported destination collision: %s" % destination)
        destinations[destination] = files[0]
    version = ctx.attr._release_version[ReleaseVersionInfo].value
    if version == "UNSET":
        fail("//build:release_version is required for imported fragments")
    spec = ctx.actions.declare_file(ctx.label.name + ".imported-entries.tsv")
    ctx.actions.write(spec, "".join([
        "%s\t%s\n" % (destination, destinations[destination].path)
        for destination in sorted(destinations.keys())
    ]))
    marker = ctx.actions.declare_file(ctx.label.name + ".verified")
    ctx.actions.run(
        executable = ctx.executable._distribution_tool,
        arguments = [
            "verify",
            "--spec",
            spec.path,
            "--content",
            ctx.file.content_manifest.path,
            "--provenance",
            ctx.file.fragment_manifest.path,
            "--compatibility",
            ctx.file.compatibility.path,
            "--marker",
            marker.path,
            "--fragment-id",
            ctx.attr.fragment_id,
            "--platform",
            ctx.attr.platform,
            "--architecture",
            ctx.attr.architecture,
            "--release-version",
            version,
        ],
        inputs = depset(
            direct = [
                spec,
                ctx.file.compatibility,
                ctx.file.content_manifest,
                ctx.file.fragment_manifest,
            ] + destinations.values(),
        ),
        outputs = [marker],
        mnemonic = "VerifyImportedDistributionFragment",
    )
    entries = depset(destinations.values())
    return [
        DefaultInfo(files = depset(
            direct = [ctx.file.content_manifest, ctx.file.fragment_manifest, marker],
            transitive = [entries],
        )),
        PackageFilesInfo(
            attributes = {"mode": "0644"},
            dest_src_map = destinations,
        ),
        DistributionFragmentInfo(
            entries = entries,
            destinations = destinations,
            compatibility = ctx.file.compatibility,
            content_manifest = ctx.file.content_manifest,
            fragment_manifest = ctx.file.fragment_manifest,
            release_version = version,
            verification = depset([marker]),
        ),
    ]

fragment_import = rule(
    implementation = _fragment_import_impl,
    attrs = {
        "entries": attr.label_keyed_string_dict(mandatory = True, allow_files = True),
        "compatibility": attr.label(mandatory = True, allow_single_file = [".json"]),
        "content_manifest": attr.label(mandatory = True, allow_single_file = [".json"]),
        "fragment_manifest": attr.label(mandatory = True, allow_single_file = [".json"]),
        "fragment_id": attr.string(mandatory = True),
        "platform": attr.string(mandatory = True),
        "architecture": attr.string(mandatory = True),
        "_release_version": attr.label(
            default = "//build:release_version",
            providers = [ReleaseVersionInfo],
        ),
        "_distribution_tool": attr.label(
            default = "//build:distribution_tool",
            executable = True,
            cfg = "exec",
        ),
    },
)

def _validate_destination(destination):
    if (
        not destination or
        destination.startswith("/") or
        "\\" in destination or
        (len(destination) > 1 and destination[1] == ":")
    ):
        fail("invalid distribution destination: %s" % destination)
    for segment in destination.split("/"):
        if segment in ["", ".", ".."]:
            fail("invalid distribution destination: %s" % destination)

distribution_fragment = rule(
    implementation = _fragment_impl,
    attrs = {
        "platform": attr.string(mandatory = True),
        "compatibility": attr.label(
            mandatory = True,
            allow_single_file = [".json"],
        ),
        "api_contract": attr.label(providers = [ApiContractInfo]),
        "api_contract_group": attr.string(
            values = ["", "unity", "godot"],
        ),
        "api_contract_destination": attr.string(),
        "adapter": attr.label(providers = [DistributionFragmentInfo]),
        "backend": attr.label(providers = [PlatformBackendInfo]),
        "entries": attr.label_keyed_string_dict(allow_files = True),
        "backend_entries": attr.string_dict(),
        "backend_file_entries": attr.string_dict(),
        "architecture": attr.string(default = "engine"),
        "_release_version": attr.label(
            default = "//build:release_version",
            providers = [ReleaseVersionInfo],
        ),
        "_distribution_tool": attr.label(
            default = "//build:distribution_tool",
            executable = True,
            cfg = "exec",
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
    unity_paths = sorted([
        file.path
        for file in unity_entries
        if "/packages/webview-core/" in "/" + file.short_path or
           "/packages/webview-web/" in "/" + file.short_path
    ])
    godot_paths = sorted([
        file.path
        for file in godot_entries
        if "/packages/webview-core/" in "/" + file.short_path or
           "/packages/webview-web/" in "/" + file.short_path
    ])
    if unity_paths != godot_paths:
        fail("Unity and Godot binding_web targets do not consume identical Core files:\nUnity=%s\nGodot=%s" % (
            unity_paths,
            godot_paths,
        ))
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

def _fragment_merge_impl(ctx):
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
    destinations = {}
    provenance = []
    verification_sets = []
    for fragment in fragments[1:]:
        if fragment.compatibility != compatibility:
            fail("all fragments must use the same compatibility.json label")
    for fragment in fragments:
        if fragment.release_version != version:
            fail("fragment release versions differ")
        provenance.append(fragment.fragment_manifest)
        verification_sets.append(fragment.verification)
        for destination, source in fragment.destinations.items():
            _validate_destination(destination)
            folded = destination.lower()
            if folded in [value.lower() for value in destinations.keys()]:
                fail("case-folded distribution destination collision: %s" % destination)
            destinations[destination] = source

    tree = ctx.actions.declare_directory(ctx.label.name + ".package-tree")
    manifest = ctx.actions.declare_file(ctx.label.name + ".content-manifest.json")
    spec = ctx.actions.declare_file(ctx.label.name + ".entries.tsv")
    ctx.actions.write(spec, "".join([
        "%s\t%s\n" % (destination, destinations[destination].path)
        for destination in sorted(destinations.keys())
    ]))
    ctx.actions.run(
        executable = ctx.executable._distribution_tool,
        arguments = [
            "merge",
            "--spec",
            spec.path,
            "--tree",
            tree.path,
            "--manifest",
            manifest.path,
            "--compatibility",
            compatibility.path,
            "--release-version",
            version,
        ],
        inputs = depset(
            direct = [spec, compatibility],
            transitive = [depset(destinations.values())] + verification_sets,
        ),
        outputs = [tree, manifest],
        mnemonic = "EngineSdkPackageTree",
    )
    package_destinations = dict(destinations)
    package_destinations["compatibility.json"] = compatibility
    package_destinations["content-manifest.json"] = manifest
    return [
        DefaultInfo(files = depset(
            direct = [tree, manifest, compatibility],
            transitive = [depset(destinations.values())],
        )),
        PackageFilesInfo(
            attributes = {"mode": "0644"},
            dest_src_map = package_destinations,
        ),
        OutputGroupInfo(
            package_tree = depset([tree]),
            content_manifest = depset([manifest]),
            provenance = depset(provenance),
        ),
    ]

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

_fragment_merge = rule(
    implementation = _fragment_merge_impl,
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
        "_distribution_tool": attr.label(
            default = "//build:distribution_tool",
            executable = True,
            cfg = "exec",
        ),
    },
)

def _sdk_outputs_impl(ctx):
    merge = ctx.attr.merge
    return [
        DefaultInfo(files = depset(
            direct = [ctx.file.tgz, ctx.file.zip],
            transitive = [merge[DefaultInfo].files],
        )),
        OutputGroupInfo(
            package_tree = merge[OutputGroupInfo].package_tree,
            content_manifest = merge[OutputGroupInfo].content_manifest,
            provenance = merge[OutputGroupInfo].provenance,
        ),
    ]

_sdk_outputs = rule(
    implementation = _sdk_outputs_impl,
    attrs = {
        "merge": attr.label(mandatory = True),
        "tgz": attr.label(mandatory = True, allow_single_file = [".tgz"]),
        "zip": attr.label(mandatory = True, allow_single_file = [".zip"]),
    },
)

def engine_sdk_distribution(
        name,
        engine,
        adapter,
        android,
        ios,
        windows,
        web,
        release_version,
        visibility,
        target_compatible_with = []):
    merge_name = "_" + name + "_merge"
    _fragment_merge(
        name = merge_name,
        engine = engine,
        adapter = adapter,
        android = android,
        ios = ios,
        windows = windows,
        web = web,
        release_version = release_version,
        target_compatible_with = target_compatible_with,
        visibility = ["//visibility:private"],
    )
    tgz_name = "_" + name + "_tgz"
    pkg_tar(
        name = tgz_name,
        srcs = [":" + merge_name],
        package_dir = "package",
        extension = "tgz",
        mode = "0644",
        owner = "0.0",
        ownername = "root.root",
        portable_mtime = True,
        stamp = 0,
        allow_duplicates_with_different_content = False,
        target_compatible_with = target_compatible_with,
        visibility = ["//visibility:private"],
    )
    zip_name = "_" + name + "_zip"
    pkg_zip(
        name = zip_name,
        srcs = [":" + merge_name],
        package_dir = "com.tedliou.verve-webview",
        mode = "0644",
        timestamp = 315532800,
        stamp = 0,
        allow_duplicates_with_different_content = False,
        target_compatible_with = target_compatible_with,
        visibility = ["//visibility:private"],
    )
    _sdk_outputs(
        name = name,
        merge = ":" + merge_name,
        tgz = ":" + tgz_name,
        zip = ":" + zip_name,
        target_compatible_with = target_compatible_with,
        visibility = visibility,
    )
