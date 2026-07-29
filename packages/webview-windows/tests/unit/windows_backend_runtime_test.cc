#include "packages/webview-windows/src/runtime/windows_backend_runtime.h"

#include <cstdlib>
#include <functional>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <utility>
#include <vector>

namespace {

using verve::webview::windows::Command;
using verve::webview::windows::Completion;
using verve::webview::windows::EnvironmentResult;
using verve::webview::windows::Geometry;
using verve::webview::windows::Host;
using verve::webview::windows::Platform;
using verve::webview::windows::Surface;
using verve::webview::windows::WindowsBackendRuntime;
using verve::webview::windows::UrlPolicy;

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
  explicit FakeSurface(std::function<void()> invalidated)
      : invalidated_(std::move(invalidated)) {}
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
      throw std::runtime_error("injected Windows cleanup failure");
    }
  }
  void InvalidateHost() { invalidated_(); }

  std::function<void()> invalidated_;
  Geometry geometry{};
  std::string url;
  bool attached = false;
  bool focused = false;
  bool destroyed = false;
  bool fail_attach = false;
  bool fail_geometry = false;
  bool fail_navigation = false;
  bool throw_on_destroy = false;
};

class FakePlatform final : public Platform {
 public:
  void Dispatch(std::function<void()> work) override {
    ui_queue.push_back(std::move(work));
  }
  std::shared_ptr<Host> ResolveCurrentHost() override { return host; }
  void EnsureEnvironment(
      std::function<void(EnvironmentResult)> completion) override {
    if (environment_ready) {
      completion(EnvironmentResult{WindowsBackendRuntime::kOk, ""});
      return;
    }
    environment_completions.push_back(std::move(completion));
  }
  void CreateSurface(
      const std::shared_ptr<Host>&,
      std::function<void()> invalidated,
      std::function<void(std::shared_ptr<Surface>, std::uint32_t, std::string)>
          completion) override {
    auto surface = std::make_shared<FakeSurface>(std::move(invalidated));
    surface->fail_attach = fail_next_attach;
    fail_next_attach = false;
    created_surfaces.push_back(surface);
    surface_completions.push_back(
        [surface, completion = std::move(completion)]() mutable {
          completion(surface, WindowsBackendRuntime::kOk, "");
        });
  }
  void RunOne() {
    auto work = std::move(ui_queue.front());
    ui_queue.erase(ui_queue.begin());
    work();
  }
  void RunAll() {
    while (!ui_queue.empty()) {
      RunOne();
    }
  }
  void CompleteEnvironment(std::uint32_t code = WindowsBackendRuntime::kOk) {
    auto completion = std::move(environment_completions.front());
    environment_completions.erase(environment_completions.begin());
    environment_ready = code == WindowsBackendRuntime::kOk;
    completion(EnvironmentResult{code, code == WindowsBackendRuntime::kOk
                                           ? ""
                                           : "WebView2 Runtime unavailable"});
  }
  void CompleteSurface() {
    auto completion = std::move(surface_completions.front());
    surface_completions.erase(surface_completions.begin());
    completion();
  }

  std::shared_ptr<FakeHost> host = std::make_shared<FakeHost>();
  std::vector<std::function<void()>> ui_queue;
  std::vector<std::function<void(EnvironmentResult)>> environment_completions;
  std::vector<std::function<void()>> surface_completions;
  std::vector<std::shared_ptr<FakeSurface>> created_surfaces;
  bool fail_next_attach = false;
  bool environment_ready = false;
};

void MissingRuntimeCompletesAsynchronouslyWithRuntimeUnavailable() {
  auto platform = std::make_shared<FakePlatform>();
  std::vector<Completion> completions;
  WindowsBackendRuntime backend(
      platform,
      [&](const Completion& value) { completions.push_back(value); },
      [](std::uint64_t) {});

  backend.Submit(Command::Initialize(1, 10, 1));
  Check(completions.empty(), "accepted work must not complete inline");
  Check(platform->environment_completions.empty(),
        "runtime detection must execute on the Windows UI dispatcher");
  platform->RunOne();
  Check(platform->environment_completions.size() == 1,
        "initialize must request the Evergreen WebView2 environment");
  platform->environment_completions[0](
      EnvironmentResult{WindowsBackendRuntime::kRuntimeUnavailable,
                        "WebView2 Runtime unavailable"});
  Check(completions.size() == 1,
        "the asynchronous environment result must complete initialize once");
  Check(completions[0].code == WindowsBackendRuntime::kRuntimeUnavailable,
        "a missing or insufficient Runtime must map to runtime_unavailable");
}

void LifecycleOwnsGeometryFocusRenavigationAndCleanup() {
  auto platform = std::make_shared<FakePlatform>();
  std::vector<Completion> completions;
  WindowsBackendRuntime backend(
      platform,
      [&](const Completion& value) { completions.push_back(value); },
      [](std::uint64_t) {});

  backend.Submit(Command::Open(
      2, 20, 1, "https://example.test/start", Geometry{0.1, 0.2, 0.5, 0.6}));
  platform->RunAll();
  platform->CompleteEnvironment();
  Check(platform->created_surfaces.size() == 1,
        "open must create one WebView2 controller Surface");
  platform->CompleteSurface();
  auto surface = platform->created_surfaces[0];
  Check(completions.back().code == WindowsBackendRuntime::kOk,
        "created and navigated Surface must complete open");
  Check(surface->attached && surface->focused,
        "open must attach and focus the WebView2 controller");
  Check(surface->geometry.x == 0.1 && surface->geometry.y == 0.2 &&
            surface->geometry.width == 0.5 && surface->geometry.height == 0.6,
        "normalized geometry must reach the Windows Surface");

  backend.Submit(Command::Open(2, 21, 1, "http://example.test/next",
                               std::nullopt));
  platform->RunAll();
  Check(platform->created_surfaces.size() == 1,
        "re-navigation must reuse the open Surface and lease");
  Check(surface->url == "http://example.test/next",
        "re-navigation must navigate the existing Surface");

  backend.Submit(Command::Close(2, 22, 1));
  platform->RunAll();
  Check(surface->destroyed && !surface->focused,
        "close must destroy the Surface and release focus");
  Check(completions.back().code == WindowsBackendRuntime::kOk,
        "successful cleanup must complete close");
}

void HostLossFailsClosedAndReleasesTheLease() {
  auto first_platform = std::make_shared<FakePlatform>();
  std::vector<Completion> first_completions;
  std::vector<std::uint64_t> lost;
  WindowsBackendRuntime first(
      first_platform,
      [&](const Completion& value) { first_completions.push_back(value); },
      [&](std::uint64_t instance) { lost.push_back(instance); });
  first.Submit(Command::Open(3, 30, 1, "https://one.test/", std::nullopt));
  first_platform->RunAll();
  first_platform->CompleteEnvironment();
  first_platform->CompleteSurface();
  first_platform->created_surfaces[0]->InvalidateHost();
  first_platform->RunAll();
  Check(lost.size() == 1 && lost[0] == 3,
        "host invalidation must emit host_lost");
  Check(first_platform->created_surfaces[0]->destroyed,
        "host loss must destroy the WebView2 controller");

  auto second_platform = std::make_shared<FakePlatform>();
  std::vector<Completion> second_completions;
  WindowsBackendRuntime second(
      second_platform,
      [&](const Completion& value) { second_completions.push_back(value); },
      [](std::uint64_t) {});
  second.Submit(Command::Open(4, 40, 1, "https://two.test/", std::nullopt));
  second_platform->RunAll();
  second_platform->CompleteEnvironment();
  second_platform->CompleteSurface();
  Check(second_completions.back().code == WindowsBackendRuntime::kOk,
        "host loss must release the application Surface Lease");
  second.Submit(Command::Close(4, 41, 1));
  second_platform->RunAll();
}

void StaleGenerationCannotAttachOrReportSuccess() {
  auto platform = std::make_shared<FakePlatform>();
  std::vector<Completion> completions;
  WindowsBackendRuntime backend(
      platform,
      [&](const Completion& value) { completions.push_back(value); },
      [](std::uint64_t) {});
  backend.Submit(Command::Open(5, 50, 1, "https://stale.test/", std::nullopt));
  platform->RunAll();
  platform->CompleteEnvironment();
  Check(platform->created_surfaces.size() == 1,
        "open must begin asynchronous controller creation");
  backend.Submit(Command::Dispose(5, 51, 2));
  platform->RunAll();
  platform->CompleteSurface();
  platform->RunAll();
  Check(platform->created_surfaces[0]->destroyed,
        "a stale controller completion must roll back its Surface");
  Check(completions.size() == 1 && completions[0].operation == 51,
        "stale open must not report success; current dispose must complete");
}

void FixedPolicyAcceptsOnlyCredentialFreeHTTPUrls() {
  Check(UrlPolicy::Allows("https://example.test/path?q=1#fragment"),
        "https must be allowed");
  Check(UrlPolicy::Allows("http://127.0.0.1:8080/"),
        "literal and private hosts stay allowed");
  Check(UrlPolicy::Allows("https://[::1]/"), "IPv6 hosts must be allowed");
  Check(!UrlPolicy::Allows("https://user:secret@example.test/"),
        "credentials must be rejected");
  Check(!UrlPolicy::Allows("file:///C:/page.html"),
        "local-file URLs must be rejected");
  Check(!UrlPolicy::Allows("data:text/html,hello"),
        "data URLs must be rejected");
  Check(!UrlPolicy::Allows("blob:https://example.test/id"),
        "blob URLs must be rejected");
  Check(!UrlPolicy::Allows("javascript:alert(1)"),
        "JavaScript URLs must be rejected");
  Check(!UrlPolicy::Allows("https:///missing-host"),
        "a non-empty host is required");
  Check(!UrlPolicy::Allows("/relative"), "relative URLs must be rejected");
}

}  // namespace

int main() {
  try {
    MissingRuntimeCompletesAsynchronouslyWithRuntimeUnavailable();
    LifecycleOwnsGeometryFocusRenavigationAndCleanup();
    HostLossFailsClosedAndReleasesTheLease();
    StaleGenerationCannotAttachOrReportSuccess();
    FixedPolicyAcceptsOnlyCredentialFreeHTTPUrls();
    std::cout << "Windows Backend runtime unit tests passed (5 scenarios)\n";
    return EXIT_SUCCESS;
  } catch (const std::exception& error) {
    std::cerr << "Windows Backend runtime unit tests failed: " << error.what()
              << '\n';
    return EXIT_FAILURE;
  }
}
