"""The four project-owned providers at the canonical build seams."""

ApiContractInfo = provider(
    doc = "Byte-verified generated API Contract snapshots grouped by consumer.",
    fields = {
        "rust": "depset of Rust semantic snapshots",
        "native": "depset of native C ABI snapshots",
        "web": "depset of Web transport snapshots",
        "unity": "depset of Unity snapshots",
        "godot": "depset of Godot snapshots",
        "docs": "depset of generated reference documentation",
        "conformance": "depset of shared conformance vectors",
    },
)

CorePayloadInfo = provider(
    doc = "Transport-neutral view of a native or Web Core payload.",
    fields = {
        "transport": "'native' or 'web'",
        "payloads": "logical immutable payload map",
        "abi_metadata": "ABI metadata File or None in a skeleton",
        "conformance": "depset of shared conformance vectors",
    },
)

PlatformBackendInfo = provider(
    doc = "Logical Platform Backend payloads without native rule internals.",
    fields = {
        "platform": "canonical platform name",
        "payloads": "logical immutable payload map",
        "runtime_metadata": "runtime metadata File",
    },
)

DistributionFragmentInfo = provider(
    doc = "Explicit installable entries and verified metadata; never an archive.",
    fields = {
        "entries": "depset of explicit installable entry Files",
        "destinations": "immutable archive-relative destination to File map",
        "compatibility": "shared compatibility metadata File",
        "content_manifest": "content manifest File",
        "fragment_manifest": "identity and provenance manifest File",
        "release_version": "the single configured SDK release version",
        "verification": "depset that forces fragment checksum/provenance verification",
    },
)
