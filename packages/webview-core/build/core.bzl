"""Canonical WebView Core target macros."""

load("//build:module_rules.bzl", "core_payload")

def webview_core_native(name, api_contract, payloads, abi_metadata, visibility):
    core_payload(
        name = name,
        api_contract = api_contract,
        transport = "native",
        payloads = payloads,
        abi_metadata = abi_metadata,
        visibility = visibility,
    )

def webview_core_web(name, api_contract, visibility):
    core_payload(
        name = name,
        api_contract = api_contract,
        transport = "web",
        payloads = [],
        target_compatible_with = ["//build/platforms:web"],
        visibility = visibility,
    )
