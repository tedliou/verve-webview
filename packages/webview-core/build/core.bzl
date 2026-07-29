"""Canonical WebView Core target macros."""

load("@rules_rust_wasm_bindgen//:providers.bzl", "RustWasmBindgenInfo")
load("//build:module_rules.bzl", "core_payload")

def _browser_bindgen_bundle_impl(ctx):
    bindgen = ctx.attr.bindgen[RustWasmBindgenInfo]
    return [DefaultInfo(files = depset(
        direct = [bindgen.wasm],
        transitive = [bindgen.js],
    ))]

browser_bindgen_bundle = rule(
    implementation = _browser_bindgen_bundle_impl,
    attrs = {
        "bindgen": attr.label(
            mandatory = True,
            providers = [RustWasmBindgenInfo],
        ),
    },
)

def webview_core_native(name, api_contract, payloads, abi_metadata, visibility):
    core_payload(
        name = name,
        api_contract = api_contract,
        transport = "native",
        payloads = payloads,
        abi_metadata = abi_metadata,
        visibility = visibility,
    )

def webview_core_web(name, api_contract, payloads, visibility):
    core_payload(
        name = name,
        api_contract = api_contract,
        transport = "web",
        payloads = payloads,
        target_compatible_with = ["//build/platforms:web"],
        visibility = visibility,
    )
