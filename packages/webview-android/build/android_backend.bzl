load("@rules_android//rules:rules.bzl", "android_library")
load("//build:module_rules.bzl", "platform_backend")

def android_backend(
        name,
        core,
        java_srcs,
        manifest,
        runtime_metadata,
        visibility):
    library_name = "_" + name + "_java"
    android_library(
        name = library_name,
        srcs = java_srcs,
        custom_package = "com.tedliou.verve.webview",
        javacopts = [
            "--release",
            "11",
        ],
        manifest = manifest,
        visibility = ["//visibility:private"],
    )
    native_payload = "_" + name + "_arm64_payload"
    emulator_payload = "_" + name + "_x86_64_payload"
    native.filegroup(
        name = native_payload,
        srcs = [":" + library_name + ".aar"],
        visibility = ["//visibility:private"],
    )
    native.filegroup(
        name = emulator_payload,
        srcs = [":" + library_name + ".aar"],
        visibility = ["//visibility:private"],
    )
    platform_backend(
        name = name,
        core = core,
        payload_keys = [
            "release/arm64-v8a/verve-webview.aar",
            "verification/x86_64/verve-webview.aar",
        ],
        payloads = [
            ":" + native_payload,
            ":" + emulator_payload,
        ],
        platform = "android",
        required_transport = "native",
        runtime_metadata = runtime_metadata,
        target_compatible_with = ["@platforms//os:android"],
        visibility = visibility,
    )
