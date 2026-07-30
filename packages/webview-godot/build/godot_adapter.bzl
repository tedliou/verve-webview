load("//build:module_rules.bzl", "distribution_fragment")

def godot_adapter(name, api_contract, compatibility, entries, visibility):
    distribution_fragment(
        name = name,
        api_contract = api_contract,
        api_contract_group = "godot",
        api_contract_destination = "addons/verve_webview/webview_contract.gd",
        compatibility = compatibility,
        entries = entries,
        platform = "engine",
        visibility = visibility,
    )

def godot_binding(name, adapter, backend, compatibility, platform, visibility):
    distribution_fragment(
        name = name,
        adapter = adapter,
        backend = backend,
        compatibility = compatibility,
        platform = platform,
        visibility = visibility,
    )
