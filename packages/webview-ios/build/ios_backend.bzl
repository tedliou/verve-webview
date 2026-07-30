load("@rules_apple//apple:apple.bzl", "apple_static_xcframework")
load("@rules_cc//cc:objc_library.bzl", "objc_library")
load("//build:module_rules.bzl", "platform_backend")

def ios_backend(
        name,
        core,
        hdrs,
        objc_srcs,
        runtime_deps,
        runtime_metadata,
        visibility):
    objc_library(
        name = "_" + name + "_objc",
        srcs = objc_srcs,
        hdrs = hdrs,
        copts = [
            "-fobjc-arc",
            "-std=c++17",
        ],
        deps = runtime_deps,
        sdk_frameworks = [
            "Security",
            "WebKit",
        ],
        visibility = ["//visibility:private"],
    )
    xcframework_name = "_" + name + "_xcframework"
    apple_static_xcframework(
        name = xcframework_name,
        bundle_name = "VerveWebViewIOS",
        deps = [":" + "_" + name + "_objc"],
        ios = {
            "device": ["arm64"],
            "simulator": [
                "arm64",
                "x86_64",
            ],
        },
        minimum_os_versions = {
            "ios": "13.0",
        },
        public_hdrs = hdrs,
        visibility = ["//visibility:private"],
    )
    platform_backend(
        name = name,
        core = core,
        payload_keys = [
            "release/ios/VerveWebViewIOS.xcframework.zip",
            "debug/ios/VerveWebViewIOS.xcframework.zip",
        ],
        payloads = [
            ":" + xcframework_name,
            ":" + xcframework_name,
        ],
        platform = "ios",
        required_transport = "native",
        runtime_metadata = runtime_metadata,
        target_compatible_with = ["@platforms//os:ios"],
        visibility = visibility,
    )
