#include "packages/webview-windows/src/runtime/windows_backend_runtime.h"

#include <algorithm>
#include <cctype>
#include <map>
#include <mutex>
#include <stdexcept>
#include <utility>

namespace verve::webview::windows {
namespace {

std::mutex g_lease_mutex;
std::optional<std::uint64_t> g_lease_owner;

bool AcquireLease(std::uint64_t instance) {
  std::lock_guard<std::mutex> lock(g_lease_mutex);
  if (!g_lease_owner.has_value() || *g_lease_owner == instance) {
    g_lease_owner = instance;
    return true;
  }
  return false;
}

void ReleaseLease(std::uint64_t instance) {
  std::lock_guard<std::mutex> lock(g_lease_mutex);
  if (g_lease_owner == instance) {
    g_lease_owner.reset();
  }
}

bool IsDecimalPort(const std::string& value) {
  if (value.empty() ||
      !std::all_of(value.begin(), value.end(),
                   [](unsigned char ch) { return std::isdigit(ch) != 0; })) {
    return false;
  }
  try {
    return std::stoul(value) <= 65535;
  } catch (const std::exception&) {
    return false;
  }
}

}  // namespace

struct WindowsBackendRuntime::State {
  struct SurfaceRecord {
    std::shared_ptr<Host> host;
    std::shared_ptr<Surface> surface;
    std::uint32_t generation;
  };

  State(std::shared_ptr<Platform> platform_value,
        CompletionSink completion_sink_value,
        HostLostSink host_lost_sink_value)
      : platform(std::move(platform_value)),
        completion_sink(std::move(completion_sink_value)),
        host_lost_sink(std::move(host_lost_sink_value)) {}

  bool IsStale(const Command& command) {
    std::lock_guard<std::mutex> lock(generation_mutex);
    auto current = latest_generations.find(command.instance);
    return current == latest_generations.end() ||
           current->second != command.generation;
  }

  void Complete(const Command& command, EnvironmentResult result) {
    if (!IsStale(command)) {
      completion_sink(Completion{command.instance, command.operation,
                                 command.generation, result.code,
                                 std::move(result.diagnostic_detail)});
    }
  }

  bool Cleanup(std::uint64_t instance) {
    auto record = surfaces.find(instance);
    bool succeeded = true;
    if (record != surfaces.end()) {
      auto surface = std::move(record->second.surface);
      surfaces.erase(record);
      try {
        surface->Destroy();
      } catch (const std::exception&) {
        succeeded = false;
      }
    }
    ReleaseLease(instance);
    return succeeded;
  }

  void HostInvalidated(std::uint64_t instance, std::uint32_t generation) {
    {
      std::lock_guard<std::mutex> lock(generation_mutex);
      auto current = latest_generations.find(instance);
      if (current == latest_generations.end() || current->second != generation) {
        return;
      }
    }
    auto record = surfaces.find(instance);
    if (record != surfaces.end() && record->second.generation == generation) {
      Cleanup(instance);
      host_lost_sink(instance);
    }
  }

  void FinishOpen(Command command, const std::shared_ptr<Host>& host,
                  std::shared_ptr<Surface> surface, std::uint32_t code,
                  std::string detail) {
    if (IsStale(command)) {
      if (surface) {
        try {
          surface->Destroy();
        } catch (const std::exception&) {
        }
      }
      ReleaseLease(command.instance);
      return;
    }
    if (code != kOk || !surface) {
      ReleaseLease(command.instance);
      Complete(command, {code == kOk ? kBackendFailure : code,
                         detail.empty() ? "WebView2 controller creation rejected"
                                        : std::move(detail)});
      return;
    }
    surfaces.emplace(command.instance,
                     SurfaceRecord{host, surface, command.generation});
    const Geometry geometry = command.geometry.value_or(Geometry{});
    if (!surface->Attach() || !surface->ApplyGeometry(geometry) ||
        !surface->Navigate(command.payload)) {
      Cleanup(command.instance);
      Complete(command,
               {kBackendFailure,
                "WebView2 attach, geometry, or navigation rejected"});
      return;
    }
    surface->Focus();
    Complete(command, {kOk, ""});
  }

  void OpenAfterEnvironment(Command command, EnvironmentResult environment) {
    if (IsStale(command)) {
      return;
    }
    if (environment.code != kOk) {
      ReleaseLease(command.instance);
      Complete(command, std::move(environment));
      return;
    }
    auto existing = surfaces.find(command.instance);
    auto host = platform->ResolveCurrentHost();
    if (!host || !host->IsValid()) {
      if (existing != surfaces.end()) {
        Cleanup(command.instance);
        Complete(command,
                 {kHostLost, "host unavailable while Surface was open"});
      } else {
        ReleaseLease(command.instance);
        Complete(command, {kHostUnavailable, ""});
      }
      return;
    }
    if (existing != surfaces.end()) {
      if (!existing->second.host->IsSameHost(*host)) {
        Cleanup(command.instance);
        Complete(command, {kHostLost, "host changed while Surface was open"});
        return;
      }
      const Geometry geometry = command.geometry.value_or(Geometry{});
      if (!existing->second.surface->ApplyGeometry(geometry) ||
          !existing->second.surface->Navigate(command.payload)) {
        Complete(command,
                 {kBackendFailure,
                  "WebView2 geometry or navigation rejected"});
        return;
      }
      existing->second.surface->Focus();
      Complete(command, {kOk, ""});
      return;
    }
    if (!AcquireLease(command.instance)) {
      Complete(command, {kSurfaceInUse, ""});
      return;
    }
    std::weak_ptr<State> weak_state = shared_from_this;
    platform->CreateSurface(
        host,
        [weak_state, instance = command.instance,
         generation = command.generation]() {
          if (auto state = weak_state.lock()) {
            state->platform->Dispatch([weak_state, instance, generation]() {
              if (auto inner = weak_state.lock()) {
                inner->HostInvalidated(instance, generation);
              }
            });
          }
        },
        [weak_state, command = std::move(command), host](
            std::shared_ptr<Surface> surface, std::uint32_t code,
            std::string detail) mutable {
          if (auto state = weak_state.lock()) {
            state->FinishOpen(std::move(command), host, std::move(surface), code,
                              std::move(detail));
          }
        });
  }

  void Execute(Command command) {
    if (IsStale(command)) {
      return;
    }
    if (command.kind == CommandKind::kOpen &&
        !UrlPolicy::Allows(command.payload)) {
      Complete(command, {kBackendFailure, "Windows Backend rejected URL policy"});
      return;
    }
    if (command.kind == CommandKind::kClose) {
      const bool cleaned = Cleanup(command.instance);
      Complete(command,
               {cleaned ? kOk : kBackendFailure,
                cleaned ? "" : "WebView2 cleanup failed"});
      return;
    }
    if (command.kind == CommandKind::kDispose) {
      const bool cleaned = Cleanup(command.instance);
      Complete(command,
               {cleaned ? kOk : kCleanupFailed,
                cleaned ? "" : "WebView2 disposal cleanup failed"});
      return;
    }
    if (command.kind == CommandKind::kUnknown) {
      Complete(command, {kBackendFailure, "unknown lifecycle command"});
      return;
    }
    std::weak_ptr<State> weak_state = shared_from_this;
    platform->EnsureEnvironment(
        [weak_state, command = std::move(command)](
            EnvironmentResult result) mutable {
          if (auto state = weak_state.lock()) {
            if (command.kind == CommandKind::kOpen) {
              state->OpenAfterEnvironment(std::move(command),
                                          std::move(result));
            } else if (result.code != kOk) {
              state->Complete(command, std::move(result));
            } else {
              auto host = state->platform->ResolveCurrentHost();
              state->Complete(
                  command,
                  {host && host->IsValid() ? kOk : kHostUnavailable, ""});
            }
          }
        });
  }

  std::shared_ptr<Platform> platform;
  CompletionSink completion_sink;
  HostLostSink host_lost_sink;
  std::mutex generation_mutex;
  std::map<std::uint64_t, std::uint32_t> latest_generations;
  std::map<std::uint64_t, SurfaceRecord> surfaces;
  std::weak_ptr<State> shared_from_this;
};

Command Command::Initialize(std::uint64_t instance, std::uint64_t operation,
                            std::uint32_t generation) {
  return {CommandKind::kInitialize, instance, operation, generation, "",
          std::nullopt};
}

Command Command::Open(std::uint64_t instance, std::uint64_t operation,
                      std::uint32_t generation, std::string url,
                      std::optional<Geometry> geometry) {
  return {CommandKind::kOpen, instance, operation, generation, std::move(url),
          geometry};
}

Command Command::Close(std::uint64_t instance, std::uint64_t operation,
                       std::uint32_t generation) {
  return {CommandKind::kClose, instance, operation, generation, "",
          std::nullopt};
}

Command Command::Dispose(std::uint64_t instance, std::uint64_t operation,
                         std::uint32_t generation) {
  return {CommandKind::kDispose, instance, operation, generation, "",
          std::nullopt};
}

bool UrlPolicy::Allows(const std::string& url) {
  if (url.empty() ||
      std::any_of(url.begin(), url.end(), [](unsigned char ch) {
        return ch <= 0x20 || ch == 0x7f;
      })) {
    return false;
  }
  const std::size_t scheme_end = url.find(':');
  if (scheme_end == std::string::npos) {
    return false;
  }
  std::string scheme = url.substr(0, scheme_end);
  std::transform(scheme.begin(), scheme.end(), scheme.begin(),
                 [](unsigned char ch) {
                   return static_cast<char>(std::tolower(ch));
                 });
  if ((scheme != "http" && scheme != "https") ||
      url.compare(scheme_end + 1, 2, "//") != 0) {
    return false;
  }
  const std::size_t start = scheme_end + 3;
  const std::size_t end = url.find_first_of("/?#", start);
  const std::string authority = url.substr(start, end - start);
  if (authority.empty() || authority.find('@') != std::string::npos) {
    return false;
  }
  if (authority.front() == '[') {
    const std::size_t closing = authority.find(']');
    if (closing == std::string::npos || closing == 1) {
      return false;
    }
    const std::string suffix = authority.substr(closing + 1);
    return suffix.empty() ||
           (suffix.front() == ':' && IsDecimalPort(suffix.substr(1)));
  }
  const std::size_t colon = authority.rfind(':');
  std::string host = authority;
  if (colon != std::string::npos) {
    if (authority.find(':') != colon ||
        !IsDecimalPort(authority.substr(colon + 1))) {
      return false;
    }
    host = authority.substr(0, colon);
  }
  return !host.empty() && host.find('\\') == std::string::npos;
}

WindowsBackendRuntime::WindowsBackendRuntime(
    std::shared_ptr<Platform> platform, CompletionSink completion_sink,
    HostLostSink host_lost_sink)
    : state_(std::make_shared<State>(std::move(platform),
                                     std::move(completion_sink),
                                     std::move(host_lost_sink))) {
  if (!state_->platform || !state_->completion_sink || !state_->host_lost_sink) {
    throw std::invalid_argument(
        "Windows Backend runtime dependencies are required");
  }
  state_->shared_from_this = state_;
}

WindowsBackendRuntime::~WindowsBackendRuntime() = default;

void WindowsBackendRuntime::Submit(Command command) {
  {
    std::lock_guard<std::mutex> lock(state_->generation_mutex);
    auto current = state_->latest_generations.find(command.instance);
    if (current == state_->latest_generations.end() ||
        command.generation > current->second) {
      state_->latest_generations[command.instance] = command.generation;
    }
  }
  std::weak_ptr<State> weak_state = state_;
  state_->platform->Dispatch(
      [weak_state, command = std::move(command)]() mutable {
        if (auto state = weak_state.lock()) {
          state->Execute(std::move(command));
        }
      });
}

}  // namespace verve::webview::windows
