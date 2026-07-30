load("//build:module_rules.bzl", "distribution_fragment")
load("//build:release_version.bzl", "ReleaseVersionInfo")
load("@rules_android//rules:rules.bzl", "android_library")
load("@rules_java//java:defs.bzl", "java_library")

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
        entries = {}):
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
