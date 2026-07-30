load("//build:module_rules.bzl", "distribution_fragment")
load("//build:providers.bzl", "PlatformBackendInfo")
load("//build:release_version.bzl", "ReleaseVersionInfo")
load("@rules_android//rules:rules.bzl", "android_library")
load("@rules_cc//cc:defs.bzl", "cc_binary")
load("@rules_java//java:defs.bzl", "java_library")

def _backend_zip_tree_impl(ctx):
    backend = ctx.attr.backend[PlatformBackendInfo]
    if ctx.attr.payload_key not in backend.payloads:
        fail("%s backend does not expose payload %s" % (
            backend.platform,
            ctx.attr.payload_key,
        ))
    archives = backend.payloads[ctx.attr.payload_key].to_list()
    if len(archives) != 1:
        fail("XCFramework payload must expose exactly one ZIP")
    output = ctx.actions.declare_directory(ctx.label.name + ".xcframework")
    ctx.actions.run(
        executable = ctx.executable._distribution_tool,
        arguments = [
            "extract-zip",
            "--archive",
            archives[0].path,
            "--tree",
            output.path,
            "--strip-prefix",
            "VerveWebViewIOS.xcframework",
        ],
        inputs = archives,
        outputs = [output],
        mnemonic = "ExtractGodotXcframework",
    )
    return [DefaultInfo(files = depset([output]))]

_backend_zip_tree = rule(
    implementation = _backend_zip_tree_impl,
    attrs = {
        "backend": attr.label(mandatory = True, providers = [PlatformBackendInfo]),
        "payload_key": attr.string(mandatory = True),
        "_distribution_tool": attr.label(
            default = "//build:distribution_tool",
            executable = True,
            cfg = "exec",
        ),
    },
)

def _plugin_config_impl(ctx):
    version = ctx.attr._release_version[ReleaseVersionInfo].value
    if version == "UNSET":
        version = "0.0.0-pre.0"
    output = ctx.actions.declare_file(ctx.label.name + ".cfg")
    ctx.actions.expand_template(
        template = ctx.file.template,
        output = output,
        substitutions = {"{RELEASE_VERSION}": version},
    )
    return [DefaultInfo(files = depset([output]))]

_plugin_config = rule(
    implementation = _plugin_config_impl,
    attrs = {
        "template": attr.label(mandatory = True, allow_single_file = True),
        "_release_version": attr.label(
            default = "//build:release_version",
            providers = [ReleaseVersionInfo],
        ),
    },
)

def godot_adapter(
        name,
        api_contract,
        compatibility,
        entries,
        plugin_config_template,
        visibility):
    plugin_config_name = "_" + name + "_plugin_config"
    _plugin_config(
        name = plugin_config_name,
        template = plugin_config_template,
        visibility = ["//visibility:private"],
    )
    all_entries = dict(entries)
    all_entries[":" + plugin_config_name] = "addons/verve_webview/plugin.cfg"
    distribution_fragment(
        name = name,
        api_contract = api_contract,
        api_contract_group = "godot",
        api_contract_destination = "addons/verve_webview/webview_contract.gd",
        compatibility = compatibility,
        entries = all_entries,
        platform = "engine",
        visibility = visibility,
    )

def godot_editor_support(
        name,
        compatibility,
        gdextension_srcs,
        visibility):
    editor_library_name = "_" + name + "_gdextension"
    cc_binary(
        name = editor_library_name,
        srcs = gdextension_srcs,
        linkshared = True,
        target_compatible_with = [
            "@platforms//cpu:x86_64",
            "@platforms//os:linux",
        ],
        visibility = ["//visibility:private"],
    )
    all_entries = {}
    all_entries[":" + editor_library_name] = (
        "addons/verve_webview/bin/windows/editor/linux/x86_64/" +
        "libverve_webview_godot_editor.so"
    )
    distribution_fragment(
        name = name,
        compatibility = compatibility,
        entries = all_entries,
        platform = "editor",
        visibility = visibility,
    )

def godot_binding(
        name,
        adapter,
        backend,
        compatibility,
        platform,
        visibility,
        architecture = "engine",
        android_compile_stubs = [],
        android_manifest = None,
        android_plugin_srcs = [],
        backend_entries = {},
        backend_file_entries = {},
        entries = {},
        windows_gdextension_srcs = []):
    all_entries = dict(entries)
    if platform == "android":
        stub_name = "_" + name + "_godot_compile_stubs"
        java_library(
            name = stub_name,
            srcs = android_compile_stubs,
            javacopts = ["--release", "11"],
            visibility = ["//visibility:private"],
        )
        plugin_name = "_" + name + "_godot_plugin"
        android_library(
            name = plugin_name,
            srcs = android_plugin_srcs,
            custom_package = "com.tedliou.verve.webview.godot",
            javacopts = ["--release", "11"],
            manifest = android_manifest,
            deps = [":" + stub_name],
            visibility = ["//visibility:private"],
        )
        all_entries[":" + plugin_name + ".aar"] = (
            "addons/verve_webview/bin/android/verve-webview-godot.aar"
        )
    if platform == "windows":
        windows_library_name = "_" + name + "_godot_gdextension"
        cc_binary(
            name = windows_library_name,
            srcs = windows_gdextension_srcs,
            linkshared = True,
            target_compatible_with = [
                "@platforms//cpu:x86_64",
                "@platforms//os:windows",
            ],
            visibility = ["//visibility:private"],
        )
        all_entries[":" + windows_library_name] = (
            "addons/verve_webview/bin/windows/x86_64/verve_webview_godot.dll"
        )
    if platform == "ios":
        for profile in ["debug", "release"]:
            payload_key = profile + "/ios/VerveWebViewIOS.xcframework.zip"
            tree_name = "_" + name + "_" + profile + "_xcframework"
            _backend_zip_tree(
                name = tree_name,
                backend = backend,
                payload_key = payload_key,
                visibility = ["//visibility:private"],
            )
            all_entries[":" + tree_name] = (
                "ios/plugins/verve_webview/VerveWebViewIOS." +
                profile + ".xcframework"
            )
    distribution_fragment(
        name = name,
        adapter = adapter,
        backend = backend,
        backend_entries = backend_entries,
        backend_file_entries = backend_file_entries,
        compatibility = compatibility,
        entries = all_entries,
        architecture = architecture,
        platform = platform,
        visibility = visibility,
    )
