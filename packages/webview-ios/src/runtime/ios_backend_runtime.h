#ifndef VERVE_WEBVIEW_IOS_BACKEND_RUNTIME_H_
#define VERVE_WEBVIEW_IOS_BACKEND_RUNTIME_H_

#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>

namespace verve::webview::ios {

struct Geometry {
  double x = 0.0;
  double y = 0.0;
  double width = 1.0;
  double height = 1.0;

  friend bool operator==(const Geometry& left, const Geometry& right) {
    return left.x == right.x && left.y == right.y &&
           left.width == right.width && left.height == right.height;
  }
};

enum class CommandKind {
  kInitialize,
  kOpen,
  kClose,
  kDispose,
  kUnknown,
};

struct Command {
  CommandKind kind;
  std::uint64_t instance;
  std::uint64_t operation;
  std::uint32_t generation;
  std::string payload;
  std::optional<Geometry> geometry;

  static Command Initialize(
      std::uint64_t instance,
      std::uint64_t operation,
      std::uint32_t generation);
  static Command Open(
      std::uint64_t instance,
      std::uint64_t operation,
      std::uint32_t generation,
      std::string url,
      std::optional<Geometry> geometry);
  static Command Close(
      std::uint64_t instance,
      std::uint64_t operation,
      std::uint32_t generation);
  static Command Dispose(
      std::uint64_t instance,
      std::uint64_t operation,
      std::uint32_t generation);
};

struct Completion {
  std::uint64_t instance;
  std::uint64_t operation;
  std::uint32_t generation;
  std::uint32_t code;
  std::string diagnostic_detail;
};

class Host {
 public:
  virtual ~Host() = default;
  virtual bool IsValid() const = 0;
  virtual bool IsSameHost(const Host& other) const = 0;
};

class Surface {
 public:
  virtual ~Surface() = default;
  virtual bool Attach() = 0;
  virtual bool ApplyGeometry(const Geometry& geometry) = 0;
  virtual bool Navigate(const std::string& url) = 0;
  virtual void Focus() = 0;
  virtual void Destroy() = 0;
};

class Platform {
 public:
  virtual ~Platform() = default;
  virtual void Dispatch(std::function<void()> work) = 0;
  virtual std::shared_ptr<Host> ResolveCurrentHost() = 0;
  virtual std::shared_ptr<Surface> CreateSurface(
      const std::shared_ptr<Host>& host,
      std::function<void()> host_invalidated) = 0;
};

using CompletionSink = std::function<void(const Completion&)>;
using HostLostSink = std::function<void(std::uint64_t instance)>;

class UrlPolicy {
 public:
  static bool Allows(const std::string& url);
};

// Platform-neutral serialized lifecycle behind the Objective-C++ WKWebView
// driver. Commands enter here; asynchronous completions and host_lost leave.
class IOSBackendRuntime {
 public:
  static constexpr std::uint32_t kOk = 0;
  static constexpr std::uint32_t kSurfaceInUse = 205;
  static constexpr std::uint32_t kHostUnavailable = 300;
  static constexpr std::uint32_t kHostLost = 301;
  static constexpr std::uint32_t kBackendFailure = 302;
  static constexpr std::uint32_t kCleanupFailed = 303;

  IOSBackendRuntime(
      std::shared_ptr<Platform> platform,
      CompletionSink completion_sink,
      HostLostSink host_lost_sink);
  ~IOSBackendRuntime();

  IOSBackendRuntime(const IOSBackendRuntime&) = delete;
  IOSBackendRuntime& operator=(const IOSBackendRuntime&) = delete;

  // Accepts work without resolving a host or completing inline.
  void Submit(Command command);

 private:
  struct State;
  std::shared_ptr<State> state_;
};

}  // namespace verve::webview::ios

#endif  // VERVE_WEBVIEW_IOS_BACKEND_RUNTIME_H_
