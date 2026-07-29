load("//build:module_rules.bzl", "platform_backend")

def ios_backend(name, core, runtime_metadata, visibility):
    platform_backend(
        name = name,
        core = core,
        platform = "ios",
        required_transport = "native",
        runtime_metadata = runtime_metadata,
        target_compatible_with = ["@platforms//os:ios"],
        visibility = visibility,
    )
