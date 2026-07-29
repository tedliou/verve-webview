load("//build:module_rules.bzl", "distribution_fragment")

def godot_adapter(name, api_contract, compatibility, visibility):
    distribution_fragment(
        name = name,
        api_contract = api_contract,
        compatibility = compatibility,
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
