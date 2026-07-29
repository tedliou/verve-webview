load("@rules_cc//cc:defs.bzl", "cc_binary", "cc_library")
load("//build:module_rules.bzl", "platform_backend")

def windows_backend(name, core, runtime_deps, runtime_metadata, visibility):
    cc_library(
        name = "_" + name + "_win32",
        alwayslink = True,
        srcs = ["src/win32/VerveWebViewWindows.cc"],
        hdrs = ["src/win32/VerveWebViewWindows.h"],
        copts = [
            "/D_WIN32_WINNT=0x0A00",
            "/DVERVE_WEBVIEW_WINDOWS_EXPORTS",
            "/std:c++17",
        ],
        deps = runtime_deps + ["@webview2_sdk//:sdk_x64"],
        target_compatible_with = [
            "@platforms//cpu:x86_64",
            "@platforms//os:windows",
        ],
        visibility = ["//visibility:private"],
    )
    dll_name = "verve_webview_windows"
    cc_binary(
        name = dll_name,
        deps = [":" + "_" + name + "_win32"],
        linkopts = [
            "/DEFAULTLIB:advapi32.lib",
            "/DEFAULTLIB:ole32.lib",
            "/DEFAULTLIB:user32.lib",
        ],
        linkshared = True,
        win_def_file = "src/win32/VerveWebViewWindows.def",
        target_compatible_with = [
            "@platforms//cpu:x86_64",
            "@platforms//os:windows",
        ],
        visibility = ["//visibility:private"],
    )
    platform_backend(
        name = name,
        core = core,
        payload_keys = ["release/windows/x86_64/verve_webview_windows.dll"],
        payloads = [":" + dll_name],
        platform = "windows",
        required_transport = "native",
        runtime_metadata = runtime_metadata,
        target_compatible_with = [
            "@platforms//cpu:x86_64",
            "@platforms//os:windows",
        ],
        visibility = visibility,
    )
