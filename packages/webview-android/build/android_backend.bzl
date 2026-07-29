load("//build:module_rules.bzl", "platform_backend")

def android_backend(name, core, runtime_metadata, visibility):
    platform_backend(
        name = name,
        core = core,
        platform = "android",
        required_transport = "native",
        runtime_metadata = runtime_metadata,
        target_compatible_with = ["@platforms//os:android"],
        visibility = visibility,
    )
