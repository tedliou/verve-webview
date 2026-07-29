package com.tedliou.verve.webview;

import java.util.ArrayList;
import java.util.List;

public final class AndroidPlatformBackendTest {
  public static void main(String[] args) {
    initializeResolvesCurrentHostAndCompletesAsynchronously();
    missingHostFailsExplicitly();
    openReusesSurfaceAndAppliesNormalizedGeometry();
    surfaceLeaseRejectsCompetitorUntilCleanupFinishes();
    hostLossCleansUpAndReleasesLease();
    generationStaleWorkCannotAttachOrComplete();
    failedFirstOpenReleasesLease();
    disposeReportsCleanupFailureButReleasesLease();
    urlPolicyMatchesTheFixedTrustDecision();
  }

  private static void initializeResolvesCurrentHostAndCompletesAsynchronously() {
    FakePlatform platform = new FakePlatform();
    List<AndroidBackendRuntime.Completion> completions = new ArrayList<>();
    AndroidBackendRuntime backend =
        new AndroidBackendRuntime(platform, completions::add, ignored -> {});

    backend.submit(AndroidBackendRuntime.Command.initialize(7L, 11L, 1));

    check(completions.isEmpty(), "accepted work must never complete inline");
    check(platform.hostResolutionCount == 0, "host must be resolved on the UI queue");

    platform.runUiQueue();

    check(platform.hostResolutionCount == 1, "current host must be resolved when work runs");
    check(completions.size() == 1, "initialize must complete exactly once");
    AndroidBackendRuntime.Completion completion = completions.get(0);
    check(completion.code == AndroidBackendRuntime.OK, "initialize must succeed");
    check(completion.instance == 7L, "instance identity must be preserved");
    check(completion.operation == 11L, "operation identity must be preserved");
    check(completion.generation == 1, "generation must be preserved");
  }

  private static void missingHostFailsExplicitly() {
    FakePlatform platform = new FakePlatform();
    platform.currentHost = null;
    List<AndroidBackendRuntime.Completion> completions = new ArrayList<>();
    AndroidBackendRuntime backend =
        new AndroidBackendRuntime(platform, completions::add, ignored -> {});

    backend.submit(AndroidBackendRuntime.Command.initialize(8L, 12L, 1));
    platform.runUiQueue();

    check(completions.get(0).code == AndroidBackendRuntime.HOST_UNAVAILABLE,
        "missing host must be host_unavailable");
  }

  private static void openReusesSurfaceAndAppliesNormalizedGeometry() {
    FakePlatform platform = new FakePlatform();
    List<AndroidBackendRuntime.Completion> completions = new ArrayList<>();
    AndroidBackendRuntime backend =
        new AndroidBackendRuntime(platform, completions::add, ignored -> {});
    AndroidBackendRuntime.Geometry geometry =
        new AndroidBackendRuntime.Geometry(0.1, 0.2, 0.5, 0.6);

    backend.submit(AndroidBackendRuntime.Command.open(
        20L, 21L, 1, "https://example.test/first", geometry));
    platform.runUiQueue();
    FakeSurface surface = platform.createdSurfaces.get(0);

    check(surface.attached, "successful open must attach the Surface");
    check(surface.geometry == geometry, "normalized geometry must reach the platform");
    check("https://example.test/first".equals(surface.url),
        "successful open must accept navigation");
    check(completions.get(0).code == AndroidBackendRuntime.OK, "first open must succeed");

    backend.submit(AndroidBackendRuntime.Command.open(
        20L, 22L, 1, "http://other.test/next", null));
    platform.runUiQueue();

    check(platform.createdSurfaces.size() == 1, "re-navigation must reuse the Surface");
    check("http://other.test/next".equals(surface.url), "re-navigation must use the new URL");
    check(surface.geometry.width == 1.0 && surface.geometry.height == 1.0,
        "omitted geometry must mean the complete host");

    backend.submit(AndroidBackendRuntime.Command.close(20L, 23L, 1));
    platform.runUiQueue();
    check(surface.destroyed, "close must destroy the native Surface");
  }

  private static void surfaceLeaseRejectsCompetitorUntilCleanupFinishes() {
    FakePlatform platform = new FakePlatform();
    List<AndroidBackendRuntime.Completion> completions = new ArrayList<>();
    AndroidBackendRuntime backend =
        new AndroidBackendRuntime(platform, completions::add, ignored -> {});

    backend.submit(AndroidBackendRuntime.Command.open(
        30L, 31L, 1, "https://one.test", null));
    backend.submit(AndroidBackendRuntime.Command.open(
        40L, 41L, 1, "https://two.test", null));
    platform.runUiQueue();

    check(completions.get(0).code == AndroidBackendRuntime.OK, "lease owner must open");
    check(completions.get(1).code == AndroidBackendRuntime.SURFACE_IN_USE,
        "competing open must fail with surface_in_use");

    backend.submit(AndroidBackendRuntime.Command.close(30L, 32L, 1));
    backend.submit(AndroidBackendRuntime.Command.open(
        40L, 42L, 1, "https://two.test", null));
    platform.runUiQueue();
    check(completions.get(3).code == AndroidBackendRuntime.OK,
        "lease must transfer only after cleanup");

    backend.submit(AndroidBackendRuntime.Command.close(40L, 43L, 1));
    platform.runUiQueue();
  }

  private static void hostLossCleansUpAndReleasesLease() {
    FakePlatform platform = new FakePlatform();
    List<Long> hostLosses = new ArrayList<>();
    AndroidBackendRuntime backend =
        new AndroidBackendRuntime(platform, ignored -> {}, hostLosses::add);

    backend.submit(AndroidBackendRuntime.Command.open(
        50L, 51L, 1, "https://host.test", null));
    platform.runUiQueue();
    FakeSurface surface = platform.createdSurfaces.get(0);
    surface.invalidateHost();
    platform.runUiQueue();

    check(surface.destroyed, "host loss must perform best-effort cleanup");
    check(hostLosses.size() == 1 && hostLosses.get(0) == 50L,
        "host loss between operations must be reported");

    List<AndroidBackendRuntime.Completion> completions = new ArrayList<>();
    AndroidBackendRuntime successor =
        new AndroidBackendRuntime(platform, completions::add, ignored -> {});
    successor.submit(AndroidBackendRuntime.Command.open(
        60L, 61L, 1, "https://recovered.test", null));
    platform.runUiQueue();
    check(completions.get(0).code == AndroidBackendRuntime.OK,
        "host loss must release the application Surface Lease");
    successor.submit(AndroidBackendRuntime.Command.close(60L, 62L, 1));
    platform.runUiQueue();
  }

  private static void generationStaleWorkCannotAttachOrComplete() {
    FakePlatform platform = new FakePlatform();
    List<AndroidBackendRuntime.Completion> completions = new ArrayList<>();
    AndroidBackendRuntime backend =
        new AndroidBackendRuntime(platform, completions::add, ignored -> {});

    backend.submit(AndroidBackendRuntime.Command.open(
        70L, 71L, 1, "https://stale.test", null));
    backend.submit(AndroidBackendRuntime.Command.dispose(70L, 72L, 2));
    platform.runUiQueue();

    check(platform.createdSurfaces.isEmpty(), "stale open must not create a Surface");
    check(completions.size() == 1 && completions.get(0).operation == 72L,
        "stale work must not report success; dispose must still complete");
  }

  private static void failedFirstOpenReleasesLease() {
    FakePlatform platform = new FakePlatform();
    platform.failNextAttach = true;
    List<AndroidBackendRuntime.Completion> completions = new ArrayList<>();
    AndroidBackendRuntime backend =
        new AndroidBackendRuntime(platform, completions::add, ignored -> {});

    backend.submit(AndroidBackendRuntime.Command.open(
        80L, 81L, 1, "https://failure.test", null));
    backend.submit(AndroidBackendRuntime.Command.open(
        90L, 91L, 1, "https://success.test", null));
    platform.runUiQueue();

    check(completions.get(0).code == AndroidBackendRuntime.BACKEND_FAILURE,
        "synchronous attach rejection must fail open");
    check(completions.get(1).code == AndroidBackendRuntime.OK,
        "failed first open must release the lease");
    backend.submit(AndroidBackendRuntime.Command.close(90L, 92L, 1));
    platform.runUiQueue();
  }

  private static void disposeReportsCleanupFailureButReleasesLease() {
    FakePlatform platform = new FakePlatform();
    List<AndroidBackendRuntime.Completion> completions = new ArrayList<>();
    AndroidBackendRuntime backend =
        new AndroidBackendRuntime(platform, completions::add, ignored -> {});
    backend.submit(AndroidBackendRuntime.Command.open(
        100L, 101L, 1, "https://dispose.test", null));
    platform.runUiQueue();
    platform.createdSurfaces.get(0).throwOnDestroy = true;

    backend.submit(AndroidBackendRuntime.Command.dispose(100L, 102L, 2));
    platform.runUiQueue();
    check(completions.get(1).code == AndroidBackendRuntime.CLEANUP_FAILED,
        "dispose cleanup failure must use cleanup_failed");

    backend.submit(AndroidBackendRuntime.Command.open(
        110L, 111L, 1, "https://after-dispose.test", null));
    platform.runUiQueue();
    check(completions.get(2).code == AndroidBackendRuntime.OK,
        "failed disposal cleanup must still release the lease");
    backend.submit(AndroidBackendRuntime.Command.close(110L, 112L, 1));
    platform.runUiQueue();
  }

  private static void urlPolicyMatchesTheFixedTrustDecision() {
    check(UrlPolicy.allows("https://example.test/path?q=1#fragment"), "https must be allowed");
    check(UrlPolicy.allows("http://127.0.0.1:8080/"), "literal and private hosts stay allowed");
    check(!UrlPolicy.allows("https://user:secret@example.test/"), "credentials must be rejected");
    check(!UrlPolicy.allows("file:///tmp/page.html"), "file URLs must be rejected");
    check(!UrlPolicy.allows("content://provider/item"), "content URLs must be rejected");
    check(!UrlPolicy.allows("javascript:alert(1)"), "javascript URLs must be rejected");
    check(!UrlPolicy.allows("mailto:user@example.test"), "external schemes must be rejected");
    check(!UrlPolicy.allows("https:///missing-host"), "a non-empty host is required");
    check(!UrlPolicy.allows("/relative"), "relative URLs must be rejected");
  }

  private static void check(boolean condition, String message) {
    if (!condition) {
      throw new AssertionError(message);
    }
  }

  private static final class FakePlatform implements AndroidBackendRuntime.Platform {
    private final List<Runnable> uiQueue = new ArrayList<>();
    private final List<FakeSurface> createdSurfaces = new ArrayList<>();
    private FakeHost currentHost = new FakeHost();
    private boolean failNextAttach;
    private int hostResolutionCount;

    @Override
    public void dispatch(Runnable work) {
      uiQueue.add(work);
    }

    @Override
    public AndroidBackendRuntime.Host resolveCurrentHost() {
      hostResolutionCount++;
      return currentHost;
    }

    @Override
    public AndroidBackendRuntime.Surface createSurface(
        AndroidBackendRuntime.Host host, Runnable hostInvalidated) {
      FakeSurface surface = new FakeSurface(hostInvalidated);
      surface.failAttach = failNextAttach;
      failNextAttach = false;
      createdSurfaces.add(surface);
      return surface;
    }

    void runUiQueue() {
      while (!uiQueue.isEmpty()) {
        uiQueue.remove(0).run();
      }
    }
  }

  private static final class FakeHost implements AndroidBackendRuntime.Host {
    private boolean valid = true;

    @Override
    public boolean isValid() {
      return valid;
    }

    @Override
    public boolean sameHost(AndroidBackendRuntime.Host other) {
      return this == other;
    }
  }

  private static final class FakeSurface implements AndroidBackendRuntime.Surface {
    private final Runnable hostInvalidated;
    private AndroidBackendRuntime.Geometry geometry;
    private String url;
    private boolean failAttach;
    private boolean attached;
    private boolean destroyed;
    private boolean throwOnDestroy;

    private FakeSurface(Runnable hostInvalidated) {
      this.hostInvalidated = hostInvalidated;
    }

    @Override
    public boolean attach() {
      attached = !failAttach;
      return attached;
    }

    @Override
    public boolean applyGeometry(AndroidBackendRuntime.Geometry value) {
      geometry = value;
      return true;
    }

    @Override
    public boolean navigate(String value) {
      url = value;
      return true;
    }

    @Override
    public void destroy() {
      destroyed = true;
      if (throwOnDestroy) {
        throw new IllegalStateException("injected Android cleanup failure");
      }
    }

    void invalidateHost() {
      hostInvalidated.run();
    }
  }
}
