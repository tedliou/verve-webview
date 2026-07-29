load("//build:module_rules.bzl", "platform_backend")

def web_backend(name, core, runtime_metadata, visibility):
    platform_backend(
        name = name,
        core = core,
        platform = "web",
        required_transport = "web",
        runtime_metadata = runtime_metadata,
        target_compatible_with = ["//build/platforms:web"],
        visibility = visibility,
    )
