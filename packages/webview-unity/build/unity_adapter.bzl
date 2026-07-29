load("//build:module_rules.bzl", "distribution_fragment")

def unity_adapter(name, api_contract, compatibility, srcs, visibility):
    distribution_fragment(
        name = name,
        api_contract = api_contract,
        api_contract_group = "unity",
        compatibility = compatibility,
        entries = srcs,
        platform = "engine",
        visibility = visibility,
    )

def unity_binding(name, adapter, backend, compatibility, platform, visibility):
    distribution_fragment(
        name = name,
        adapter = adapter,
        backend = backend,
        compatibility = compatibility,
        platform = platform,
        visibility = visibility,
    )
