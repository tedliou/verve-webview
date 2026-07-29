#include "packages/webview-ios/src/runtime/ios_backend_runtime.h"

#include <cmath>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

using verve::webview::ios::Command;
using verve::webview::ios::Completion;
using verve::webview::ios::Geometry;
using verve::webview::ios::Host;
using verve::webview::ios::HostLostSink;
using verve::webview::ios::IOSBackendRuntime;
using verve::webview::ios::Platform;
using verve::webview::ios::Surface;
using verve::webview::ios::UrlPolicy;

void Check(bool condition, const char* message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

class FakeHost final : public Host {
 public:
  bool IsValid() const override { return valid; }
  bool IsSameHost(const Host& other) const override { return this == &other; }

  bool valid = true;
};

class FakeSurface final : public Surface {
 public:
  explicit FakeSurface(std::function<void()> host_invalidated)
      : host_invalidated_(std::move(host_invalidated)) {}

  bool Attach() override {
    attached = !fail_attach;
    return attached;
  }

  bool ApplyGeometry(const Geometry& value) override {
    geometry = value;
    return !fail_geometry;
  }

  bool Navigate(const std::string& value) override {
    url = value;
    return !fail_navigation;
  }

  void Focus() override { focused = true; }

  void Destroy() override {
    destroyed = true;
    focused = false;
    if (throw_on_destroy) {
      throw std::runtime_error("injected iOS cleanup failure");
    }
  }

  void InvalidateHost() { host_invalidated_(); }

  std::function<void()> host_invalidated_;
  Geometry geometry{};
  std::string url;
  bool fail_attach = false;
  bool fail_geometry = false;
  bool fail_navigation = false;
  bool attached = false;
  bool focused = false;
  bool destroyed = false;
  bool throw_on_destroy = false;
};

class FakePlatform final : public Platform {
 public:
  FakePlatform() : current_host(std::make_shared<FakeHost>()) {}

  void Dispatch(std::function<void()> work) override {
    ui_queue.push_back(std::move(work));
  }

  std::shared_ptr<Host> ResolveCurrentHost() override {
    ++host_resolution_count;
    return current_host;
  }

  std::shared_ptr<Surface> CreateSurface(
      const std::shared_ptr<Host>&,
      std::function<void()> host_invalidated) override {
    auto surface = std::make_shared<FakeSurface>(std::move(host_invalidated));
    surface->fail_attach = fail_next_attach;
    fail_next_attach = false;
    created_surfaces.push_back(surface);
    return surface;
  }

  void RunUIQueue() {
    while (!ui_queue.empty()) {
      auto work = std::move(ui_queue.front());
      ui_queue.erase(ui_queue.begin());
      work();
    }
  }

  std::vector<std::function<void()>> ui_queue;
  std::vector<std::shared_ptr<FakeSurface>> created_surfaces;
  std::shared_ptr<FakeHost> current_host;
  bool fail_next_attach = false;
  int host_resolution_count = 0;
};

void AcceptedWorkIsAsynchronousAndResolvesTheCurrentHost() {
  auto platform = std::make_shared<FakePlatform>();
  std::vector<Completion> completions;
  IOSBackendRuntime backend(
      platform,
      [&](const Completion& value) { completions.push_back(value); },
      [](std::uint64_t) {});

  backend.Submit(Command::Initialize(1, 10, 1));
  Check(completions.empty(), "accepted work must not complete inline");
  Check(platform->host_resolution_count == 0,
        "the Host Locator must run on the dispatched UI path");

  platform->RunUIQueue();
  Check(completions.size() == 1, "initialize must complete once");
  Check(completions[0].code == IOSBackendRuntime::kOk,
        "a usable current host must initialize successfully");
  Check(platform->host_resolution_count == 1,
        "initialize must resolve the current host exactly when it executes");
}

void OpenOwnsGeometryFocusRenavigationAndCleanup() {
  auto platform = std::make_shared<FakePlatform>();
  std::vector<Completion> completions;
  IOSBackendRuntime backend(
      platform,
      [&](const Completion& value) { completions.push_back(value); },
      [](std::uint64_t) {});

  backend.Submit(Command::Open(2, 20, 1, "https://example.test/", std::nullopt));
  platform->RunUIQueue();
  Check(completions.back().code == IOSBackendRuntime::kOk,
        "first open must succeed");
  Check(platform->created_surfaces.size() == 1,
        "first open must create one owned Surface");
  std::shared_ptr<FakeSurface> surface = platform->created_surfaces[0];
  Check(surface->attached, "successful open must attach the Surface");
  Check(surface->focused, "successful open must allow the Surface to acquire focus");
  Check(surface->geometry == Geometry{0.0, 0.0, 1.0, 1.0},
        "omitted geometry must cover the complete host");

  Geometry inset{0.25, 0.2, 0.5, 0.6};
  backend.Submit(Command::Open(
      2, 21, 1, "http://127.0.0.1:8080/next", inset));
  platform->RunUIQueue();
  Check(platform->created_surfaces.size() == 1,
        "open on the owning instance must reuse its current Surface");
  Check(surface->geometry == inset,
        "renavigation must apply the latest normalized geometry");
  Check(surface->url == "http://127.0.0.1:8080/next",
        "renavigation must stay in the current Surface");
  Check(platform->host_resolution_count == 2,
        "every open must resolve the current Host Locator");

  backend.Submit(Command::Close(2, 22, 1));
  platform->RunUIQueue();
  Check(surface->destroyed, "close must destroy the native Surface");
  Check(!surface->focused, "close must release focus");
  Check(completions.back().code == IOSBackendRuntime::kOk,
        "successful cleanup must complete close");
}

void HostLossFailsClosedAndReleasesTheLease() {
  auto first_platform = std::make_shared<FakePlatform>();
  auto second_platform = std::make_shared<FakePlatform>();
  std::vector<std::uint64_t> host_losses;
  std::vector<Completion> second_completions;
  IOSBackendRuntime first(
      first_platform, [](const Completion&) {},
      [&](std::uint64_t instance) { host_losses.push_back(instance); });
  IOSBackendRuntime second(
      second_platform,
      [&](const Completion& value) { second_completions.push_back(value); },
      [](std::uint64_t) {});

  first.Submit(Command::Open(3, 30, 1, "https://first.test/", std::nullopt));
  first_platform->RunUIQueue();
  second.Submit(Command::Open(4, 40, 1, "https://second.test/", std::nullopt));
  second_platform->RunUIQueue();
  Check(second_completions.back().code == IOSBackendRuntime::kSurfaceInUse,
        "a competing instance must not steal the application Surface Lease");

  first_platform->created_surfaces[0]->InvalidateHost();
  Check(host_losses.empty(), "host loss must be serialized on the UI path");
  first_platform->RunUIQueue();
  Check(host_losses == std::vector<std::uint64_t>{3},
        "an open Surface must report host_lost exactly once");
  Check(first_platform->created_surfaces[0]->destroyed,
        "host loss must perform best-effort cleanup");

  second.Submit(Command::Open(4, 41, 1, "https://second.test/", std::nullopt));
  second_platform->RunUIQueue();
  Check(second_completions.back().code == IOSBackendRuntime::kOk,
        "host loss must release the application Surface Lease");
  second.Submit(Command::Close(4, 42, 1));
  second_platform->RunUIQueue();
}

void AChangedResolvedHostDoesNotReparentAnOpenSurface() {
  auto platform = std::make_shared<FakePlatform>();
  std::vector<Completion> completions;
  IOSBackendRuntime backend(
      platform,
      [&](const Completion& value) { completions.push_back(value); },
      [](std::uint64_t) {});

  backend.Submit(Command::Open(5, 50, 1, "https://one.test/", std::nullopt));
  platform->RunUIQueue();
  std::shared_ptr<FakeSurface> original = platform->created_surfaces[0];
  platform->current_host = std::make_shared<FakeHost>();
  backend.Submit(Command::Open(5, 51, 1, "https://two.test/", std::nullopt));
  platform->RunUIQueue();

  Check(completions.back().code == IOSBackendRuntime::kHostLost,
        "a changed Host Locator must fail the operation with host_lost");
  Check(original->destroyed, "a changed host must clean up the original Surface");
  Check(platform->created_surfaces.size() == 1,
        "the Backend must not silently reparent or recreate after host loss");
}

void StaleGenerationCannotAttachOrReportSuccess() {
  auto platform = std::make_shared<FakePlatform>();
  std::vector<Completion> completions;
  IOSBackendRuntime backend(
      platform,
      [&](const Completion& value) { completions.push_back(value); },
      [](std::uint64_t) {});

  backend.Submit(Command::Open(6, 60, 1, "https://stale.test/", std::nullopt));
  backend.Submit(Command::Dispose(6, 61, 2));
  platform->RunUIQueue();

  Check(platform->created_surfaces.empty(),
        "stale queued open work must not create or attach a Surface");
  Check(completions.size() == 1 && completions[0].operation == 61,
        "stale work must not report success; current dispose must complete");
}

void FailedCreationAndCleanupStillReleaseTheLease() {
  auto first_platform = std::make_shared<FakePlatform>();
  first_platform->fail_next_attach = true;
  std::vector<Completion> first_completions;
  IOSBackendRuntime first(
      first_platform,
      [&](const Completion& value) { first_completions.push_back(value); },
      [](std::uint64_t) {});
  first.Submit(Command::Open(7, 70, 1, "https://failure.test/", std::nullopt));
  first_platform->RunUIQueue();
  Check(first_completions.back().code == IOSBackendRuntime::kBackendFailure,
        "synchronous attach rejection must fail open");

  auto second_platform = std::make_shared<FakePlatform>();
  std::vector<Completion> second_completions;
  IOSBackendRuntime second(
      second_platform,
      [&](const Completion& value) { second_completions.push_back(value); },
      [](std::uint64_t) {});
  second.Submit(Command::Open(8, 80, 1, "https://success.test/", std::nullopt));
  second_platform->RunUIQueue();
  Check(second_completions.back().code == IOSBackendRuntime::kOk,
        "failed first open must release the Surface Lease");

  second_platform->created_surfaces[0]->throw_on_destroy = true;
  second.Submit(Command::Dispose(8, 81, 2));
  second_platform->RunUIQueue();
  Check(second_completions.back().code == IOSBackendRuntime::kCleanupFailed,
        "dispose cleanup failure must use cleanup_failed");

  first.Submit(Command::Open(7, 71, 1, "https://after-cleanup.test/", std::nullopt));
  first_platform->RunUIQueue();
  Check(first_completions.back().code == IOSBackendRuntime::kOk,
        "failed disposal cleanup must still release the Surface Lease");
  first.Submit(Command::Close(7, 72, 1));
  first_platform->RunUIQueue();
}

void FixedURLPolicyAcceptsOnlyCredentialFreeHTTPURLs() {
  Check(UrlPolicy::Allows("https://example.test/path?q=1#fragment"),
        "https must be allowed");
  Check(UrlPolicy::Allows("http://127.0.0.1:8080/"),
        "literal and private hosts stay allowed");
  Check(UrlPolicy::Allows("https://[::1]/"),
        "bracketed IPv6 hosts must be allowed");
  Check(!UrlPolicy::Allows("https://user:secret@example.test/"),
        "credentials must be rejected");
  Check(!UrlPolicy::Allows("file:///tmp/page.html"), "file URLs must be rejected");
  Check(!UrlPolicy::Allows("data:text/html,hello"), "data URLs must be rejected");
  Check(!UrlPolicy::Allows("blob:https://example.test/id"), "blob URLs must be rejected");
  Check(!UrlPolicy::Allows("javascript:alert(1)"),
        "JavaScript URLs must be rejected");
  Check(!UrlPolicy::Allows("mailto:user@example.test"),
        "external schemes must be rejected");
  Check(!UrlPolicy::Allows("https:///missing-host"),
        "a non-empty host is required");
  Check(!UrlPolicy::Allows("https://example.test:invalid/"),
        "a malformed port must be rejected");
  Check(!UrlPolicy::Allows("/relative"), "relative URLs must be rejected");
}

}  // namespace

int main() {
  try {
    AcceptedWorkIsAsynchronousAndResolvesTheCurrentHost();
    OpenOwnsGeometryFocusRenavigationAndCleanup();
    HostLossFailsClosedAndReleasesTheLease();
    AChangedResolvedHostDoesNotReparentAnOpenSurface();
    StaleGenerationCannotAttachOrReportSuccess();
    FailedCreationAndCleanupStillReleaseTheLease();
    FixedURLPolicyAcceptsOnlyCredentialFreeHTTPURLs();
    std::cout << "iOS Backend runtime unit tests passed (7 scenarios)\n";
    return EXIT_SUCCESS;
  } catch (const std::exception& error) {
    std::cerr << "iOS Backend runtime unit tests failed: " << error.what() << '\n';
    return EXIT_FAILURE;
  }
}
