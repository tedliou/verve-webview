"""Hermetic API Contract generation and committed snapshot verification."""

load("//build:providers.bzl", "ApiContractInfo")

def _api_contract_impl(ctx):
    stamp = ctx.actions.declare_file(ctx.label.name + ".verified")
    groups = {
        "rust": ctx.files.rust,
        "native": ctx.files.native,
        "web": ctx.files.web,
        "unity": ctx.files.unity,
        "godot": ctx.files.godot,
        "docs": ctx.files.docs,
        "conformance": ctx.files.conformance,
    }
    snapshots = []
    for files in groups.values():
        snapshots.extend(files)

    args = ctx.actions.args()
    args.add("verify")
    args.add(ctx.file.src)
    args.add(ctx.file.id_registry)
    args.add(ctx.label.package + "/generated")
    args.add(stamp)
    ctx.actions.run(
        executable = ctx.executable.generator,
        arguments = [args],
        inputs = depset([ctx.file.src, ctx.file.id_registry] + snapshots),
        outputs = [stamp],
        mnemonic = "VerifyApiContract",
        progress_message = "Verifying deterministic API Contract snapshots",
    )

    return [
        DefaultInfo(files = depset([stamp])),
        ApiContractInfo(
            rust = depset(groups["rust"]),
            native = depset(groups["native"]),
            web = depset(groups["web"]),
            unity = depset(groups["unity"]),
            godot = depset(groups["godot"]),
            docs = depset(groups["docs"]),
            conformance = depset(groups["conformance"]),
        ),
    ]

_api_contract = rule(
    implementation = _api_contract_impl,
    attrs = {
        "src": attr.label(allow_single_file = [".yaml"], mandatory = True),
        "id_registry": attr.label(allow_single_file = [".json"], mandatory = True),
        "generator": attr.label(executable = True, cfg = "exec", mandatory = True),
        "rust": attr.label_list(allow_files = True),
        "native": attr.label_list(allow_files = True),
        "web": attr.label_list(allow_files = True),
        "unity": attr.label_list(allow_files = True),
        "godot": attr.label_list(allow_files = True),
        "docs": attr.label_list(allow_files = True),
        "conformance": attr.label_list(allow_files = True),
    },
)

def api_contract(name, src, id_registry, generator, snapshots, visibility):
    """Declares the canonical API Contract interface."""
    expected_groups = [
        "rust",
        "native",
        "web",
        "unity",
        "godot",
        "docs",
        "conformance",
    ]
    if sorted(snapshots.keys()) != sorted(expected_groups):
        fail("api_contract snapshots must define exactly: %s" % sorted(expected_groups))
    _api_contract(
        name = name,
        src = src,
        id_registry = id_registry,
        generator = generator,
        rust = snapshots["rust"],
        native = snapshots["native"],
        web = snapshots["web"],
        unity = snapshots["unity"],
        godot = snapshots["godot"],
        docs = snapshots["docs"],
        conformance = snapshots["conformance"],
        visibility = visibility,
    )
