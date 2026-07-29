"""The single release version build setting."""

ReleaseVersionInfo = provider(fields = {"value": "configured release version"})

def _release_version_impl(ctx):
    return [ReleaseVersionInfo(value = ctx.build_setting_value)]

release_version = rule(
    implementation = _release_version_impl,
    build_setting = config.string(flag = True),
)
