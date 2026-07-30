load("//build:module_rules.bzl", "distribution_fragment")
load("//build:release_version.bzl", "ReleaseVersionInfo")

def _package_json_impl(ctx):
    version = ctx.attr._release_version[ReleaseVersionInfo].value
    if version == "UNSET":
        version = "0.0.0-pre.0"
    output = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.expand_template(
        template = ctx.file.template,
        output = output,
        substitutions = {"{RELEASE_VERSION}": version},
    )
    return [DefaultInfo(files = depset([output]))]

_package_json = rule(
    implementation = _package_json_impl,
    attrs = {
        "template": attr.label(mandatory = True, allow_single_file = True),
        "_release_version": attr.label(
            default = "//build:release_version",
            providers = [ReleaseVersionInfo],
        ),
    },
)

def unity_adapter(
        name,
        api_contract,
        compatibility,
        entries,
        package_json_template,
        visibility):
    package_json_name = "_" + name + "_package_json"
    _package_json(
        name = package_json_name,
        template = package_json_template,
        visibility = ["//visibility:private"],
    )
    all_entries = dict(entries)
    all_entries[":" + package_json_name] = "package.json"
    distribution_fragment(
        name = name,
        api_contract = api_contract,
        api_contract_group = "unity",
        api_contract_destination = "Runtime/WebViewContract.g.cs",
        compatibility = compatibility,
        entries = all_entries,
        platform = "engine",
        visibility = visibility,
    )

def unity_binding(
        name,
        adapter,
        backend,
        backend_entries,
        compatibility,
        entries,
        architecture,
        platform,
        visibility,
        backend_file_entries = {}):
    distribution_fragment(
        name = name,
        adapter = adapter,
        backend = backend,
        backend_entries = backend_entries,
        backend_file_entries = backend_file_entries,
        compatibility = compatibility,
        entries = entries,
        architecture = architecture,
        platform = platform,
        visibility = visibility,
    )
