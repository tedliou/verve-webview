#include "packages/webview-ios/src/runtime/ios_backend_runtime.h"

#include <algorithm>
#include <cctype>
#include <limits>
#include <map>
#include <mutex>
#include <stdexcept>
#include <utility>

namespace verve::webview::ios {
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

bool IsASCIIWhitespaceOrControl(unsigned char value) {
  return value <= 0x20 || value == 0x7f;
}

bool IsDecimalPort(const std::string& value) {
  if (value.empty() ||
      !std::all_of(value.begin(), value.end(),
                   [](unsigned char ch) { return std::isdigit(ch) != 0; })) {
    return false;
  }
  unsigned long port = 0;
  try {
    port = std::stoul(value);
  } catch (const std::exception&) {
    return false;
  }
  return port <= 65535;
}

}  // namespace

struct IOSBackendRuntime::State {
  struct SurfaceRecord {
    std::shared_ptr<Host> host;
    std::shared_ptr<Surface> surface;
    std::uint32_t generation;
  };

  State(
      std::shared_ptr<Platform> platform_value,
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

  void Complete(
      const Command& command,
      std::uint32_t code,
      std::string diagnostic_detail = {}) {
    if (IsStale(command)) {
      CleanupGeneration(command.instance, command.generation);
      return;
    }
    completion_sink(Completion{
        command.instance,
        command.operation,
        command.generation,
        code,
        std::move(diagnostic_detail),
    });
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

  void CleanupGeneration(std::uint64_t instance, std::uint32_t generation) {
    auto record = surfaces.find(instance);
    if (record != surfaces.end() && record->second.generation == generation) {
      Cleanup(instance);
    }
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

  void Open(const Command& command) {
    auto existing = surfaces.find(command.instance);
    if (!UrlPolicy::Allows(command.payload)) {
      Complete(command, kBackendFailure, "iOS Backend rejected URL policy");
      return;
    }

    std::shared_ptr<Host> current_host = platform->ResolveCurrentHost();
    if (!current_host || !current_host->IsValid()) {
      if (existing != surfaces.end()) {
        Cleanup(command.instance);
        Complete(command, kHostLost, "host unavailable while Surface was open");
      } else {
        ReleaseLease(command.instance);
        Complete(command, kHostUnavailable);
      }
      return;
    }

    if (existing != surfaces.end() &&
        !existing->second.host->IsSameHost(*current_host)) {
      Cleanup(command.instance);
      Complete(command, kHostLost, "host changed while Surface was open");
      return;
    }

    const bool is_new_surface = existing == surfaces.end();
    if (is_new_surface && !AcquireLease(command.instance)) {
      Complete(command, kSurfaceInUse);
      return;
    }

    if (is_new_surface) {
      std::weak_ptr<State> weak_state = shared_from_this;
      std::shared_ptr<Surface> surface = platform->CreateSurface(
          current_host, [weak_state, instance = command.instance,
                         generation = command.generation]() {
            if (auto state = weak_state.lock()) {
              state->platform->Dispatch([weak_state, instance, generation]() {
                if (auto inner_state = weak_state.lock()) {
                  inner_state->HostInvalidated(instance, generation);
                }
              });
            }
          });
      if (!surface) {
        ReleaseLease(command.instance);
        Complete(command, kBackendFailure, "WKWebView creation rejected");
        return;
      }
      surfaces.emplace(
          command.instance,
          SurfaceRecord{current_host, std::move(surface), command.generation});
      existing = surfaces.find(command.instance);
      if (!existing->second.surface->Attach()) {
        Cleanup(command.instance);
        Complete(command, kBackendFailure, "WKWebView attach rejected");
        return;
      }
    }

    const Geometry geometry = command.geometry.value_or(Geometry{});
    if (!existing->second.surface->ApplyGeometry(geometry) ||
        !existing->second.surface->Navigate(command.payload)) {
      if (is_new_surface) {
        Cleanup(command.instance);
      }
      Complete(
          command, kBackendFailure,
          "WKWebView geometry or navigation rejected");
      return;
    }
    existing->second.surface->Focus();
    Complete(command, kOk);
  }

  void Execute(const Command& command) {
    if (IsStale(command)) {
      return;
    }
    try {
      switch (command.kind) {
        case CommandKind::kInitialize: {
          auto host = platform->ResolveCurrentHost();
          Complete(
              command,
              host && host->IsValid() ? kOk : kHostUnavailable);
          return;
        }
        case CommandKind::kOpen:
          Open(command);
          return;
        case CommandKind::kClose:
          if (Cleanup(command.instance)) {
            Complete(command, kOk);
          } else {
            Complete(command, kBackendFailure, "WKWebView cleanup failed");
          }
          return;
        case CommandKind::kDispose:
          if (Cleanup(command.instance)) {
            Complete(command, kOk);
          } else {
            Complete(
                command, kCleanupFailed, "WKWebView disposal cleanup failed");
          }
          return;
        case CommandKind::kUnknown:
          Complete(command, kBackendFailure, "unknown lifecycle command");
          return;
      }
    } catch (const std::exception&) {
      if (command.kind == CommandKind::kOpen) {
        Cleanup(command.instance);
      }
      Complete(command, kBackendFailure, "iOS Backend platform failure");
    }
  }

  std::shared_ptr<Platform> platform;
  CompletionSink completion_sink;
  HostLostSink host_lost_sink;
  std::mutex generation_mutex;
  std::map<std::uint64_t, std::uint32_t> latest_generations;
  std::map<std::uint64_t, SurfaceRecord> surfaces;
  std::weak_ptr<State> shared_from_this;
};

Command Command::Initialize(
    std::uint64_t instance,
    std::uint64_t operation,
    std::uint32_t generation) {
  return {
      CommandKind::kInitialize, instance, operation, generation, "", std::nullopt};
}

Command Command::Open(
    std::uint64_t instance,
    std::uint64_t operation,
    std::uint32_t generation,
    std::string url,
    std::optional<Geometry> geometry) {
  return {
      CommandKind::kOpen,
      instance,
      operation,
      generation,
      std::move(url),
      geometry,
  };
}

Command Command::Close(
    std::uint64_t instance,
    std::uint64_t operation,
    std::uint32_t generation) {
  return {CommandKind::kClose, instance, operation, generation, "", std::nullopt};
}

Command Command::Dispose(
    std::uint64_t instance,
    std::uint64_t operation,
    std::uint32_t generation) {
  return {
      CommandKind::kDispose, instance, operation, generation, "", std::nullopt};
}

bool UrlPolicy::Allows(const std::string& url) {
  if (url.empty() ||
      std::any_of(
          url.begin(), url.end(),
          [](unsigned char ch) { return IsASCIIWhitespaceOrControl(ch); })) {
    return false;
  }

  const std::size_t scheme_end = url.find(':');
  if (scheme_end == std::string::npos) {
    return false;
  }
  std::string scheme = url.substr(0, scheme_end);
  std::transform(
      scheme.begin(), scheme.end(), scheme.begin(),
      [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  if (scheme != "http" && scheme != "https") {
    return false;
  }
  if (url.compare(scheme_end + 1, 2, "//") != 0) {
    return false;
  }

  const std::size_t authority_start = scheme_end + 3;
  const std::size_t authority_end = url.find_first_of("/?#", authority_start);
  const std::string authority =
      url.substr(authority_start, authority_end - authority_start);
  if (authority.empty() || authority.find('@') != std::string::npos) {
    return false;
  }

  if (authority.front() == '[') {
    const std::size_t closing_bracket = authority.find(']');
    if (closing_bracket == std::string::npos || closing_bracket == 1) {
      return false;
    }
    const std::string suffix = authority.substr(closing_bracket + 1);
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

IOSBackendRuntime::IOSBackendRuntime(
    std::shared_ptr<Platform> platform,
    CompletionSink completion_sink,
    HostLostSink host_lost_sink)
    : state_(std::make_shared<State>(
          std::move(platform),
          std::move(completion_sink),
          std::move(host_lost_sink))) {
  if (!state_->platform || !state_->completion_sink || !state_->host_lost_sink) {
    throw std::invalid_argument("iOS Backend runtime dependencies are required");
  }
  state_->shared_from_this = state_;
}

IOSBackendRuntime::~IOSBackendRuntime() = default;

void IOSBackendRuntime::Submit(Command command) {
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
          state->Execute(command);
        }
      });
}

}  // namespace verve::webview::ios
