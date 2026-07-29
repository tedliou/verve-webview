load("//build:module_rules.bzl", "platform_backend")

def windows_backend(name, core, runtime_metadata, visibility):
    platform_backend(
        name = name,
        core = core,
        platform = "windows",
        required_transport = "native",
        runtime_metadata = runtime_metadata,
        target_compatible_with = [
            "@platforms//cpu:x86_64",
            "@platforms//os:windows",
        ],
        visibility = visibility,
    )
