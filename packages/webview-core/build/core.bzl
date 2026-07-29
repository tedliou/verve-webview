"""Canonical WebView Core target macros."""

load("//build:module_rules.bzl", "core_payload")

def webview_core_native(name, api_contract, visibility):
    core_payload(
        name = name,
        api_contract = api_contract,
        transport = "native",
        visibility = visibility,
    )

def webview_core_web(name, api_contract, visibility):
    core_payload(
        name = name,
        api_contract = api_contract,
        transport = "web",
        target_compatible_with = ["//build/platforms:web"],
        visibility = visibility,
    )
