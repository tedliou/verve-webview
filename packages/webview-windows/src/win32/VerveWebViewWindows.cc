#include "packages/webview-windows/src/win32/VerveWebViewWindows.h"

#include <WebView2.h>
#include <WebView2EnvironmentOptions.h>
#include <wrl.h>

#include <algorithm>
#include <cmath>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

#include "packages/webview-windows/src/runtime/windows_backend_runtime.h"

namespace {

namespace backend = verve::webview::windows;
using Microsoft::WRL::Callback;
using Microsoft::WRL::ComPtr;

std::string Utf8(PCWSTR value) {
  if (!value) return {};
  int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value, -1,
                                 nullptr, 0, nullptr, nullptr);
  if (size <= 1) return {};
  std::string result(static_cast<size_t>(size), '\0');
  WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value, -1, result.data(),
                      size, nullptr, nullptr);
  result.resize(static_cast<size_t>(size - 1));
  return result;
}

std::wstring Wide(const std::string& value) {
  int size = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(),
                                 static_cast<int>(value.size()), nullptr, 0);
  if (size <= 0) return {};
  std::wstring result(static_cast<size_t>(size), L'\0');
  MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(),
                      static_cast<int>(value.size()), result.data(), size);
  return result;
}

class WinHost final : public backend::Host {
 public:
  explicit WinHost(HWND hwnd) : hwnd_(hwnd) {}
  bool IsValid() const override { return hwnd_ && IsWindow(hwnd_); }
  bool IsSameHost(const backend::Host& other) const override {
    auto* host = dynamic_cast<const WinHost*>(&other);
    return host && host->hwnd_ == hwnd_;
  }
  HWND hwnd() const { return hwnd_; }

 private:
  HWND hwnd_;
};

class WinSurface final : public backend::Surface {
 public:
  WinSurface(HWND host, ComPtr<ICoreWebView2Controller> controller,
             ComPtr<ICoreWebView2> webview, std::function<void()> invalidated,
             bool debugging_enabled)
      : host_(host),
        controller_(std::move(controller)),
        webview_(std::move(webview)),
        invalidated_(std::move(invalidated)),
        debugging_enabled_(debugging_enabled) {}

  ~WinSurface() override { Destroy(); }

  bool Configure() {
    ComPtr<ICoreWebView2Settings> settings;
    if (FAILED(webview_->get_Settings(&settings)) ||
        FAILED(settings->put_IsScriptEnabled(TRUE)) ||
        FAILED(settings->put_IsWebMessageEnabled(FALSE)) ||
        FAILED(settings->put_AreHostObjectsAllowed(FALSE)) ||
        FAILED(settings->put_AreDevToolsEnabled(debugging_enabled_ ? TRUE
                                                                   : FALSE))) {
      return false;
    }
    EventRegistrationToken ignored{};
    if (FAILED(webview_->add_NavigationStarting(
            Callback<ICoreWebView2NavigationStartingEventHandler>(
                [](ICoreWebView2*, ICoreWebView2NavigationStartingEventArgs* a) {
                  LPWSTR uri = nullptr;
                  if (FAILED(a->get_Uri(&uri)) ||
                      !backend::UrlPolicy::Allows(Utf8(uri))) {
                    a->put_Cancel(TRUE);
                  }
                  CoTaskMemFree(uri);
                  return S_OK;
                })
                .Get(),
            &ignored)) ||
        FAILED(webview_->add_PermissionRequested(
            Callback<ICoreWebView2PermissionRequestedEventHandler>(
                [](ICoreWebView2*, ICoreWebView2PermissionRequestedEventArgs* a) {
                  return a->put_State(COREWEBVIEW2_PERMISSION_STATE_DENY);
                })
                .Get(),
            &ignored)) ||
        FAILED(webview_->add_NewWindowRequested(
            Callback<ICoreWebView2NewWindowRequestedEventHandler>(
                [](ICoreWebView2*, ICoreWebView2NewWindowRequestedEventArgs* a) {
                  return a->put_Handled(TRUE);
                })
                .Get(),
            &ignored))) {
      return false;
    }
    ComPtr<ICoreWebView2_4> v4;
    if (FAILED(webview_.As(&v4)) ||
        FAILED(v4->add_DownloadStarting(
            Callback<ICoreWebView2DownloadStartingEventHandler>(
                [](ICoreWebView2*, ICoreWebView2DownloadStartingEventArgs* a) {
                  a->put_Cancel(TRUE);
                  return a->put_Handled(TRUE);
                })
                .Get(),
            &ignored))) {
      return false;
    }
    ComPtr<ICoreWebView2_5> v5;
    if (FAILED(webview_.As(&v5)) ||
        FAILED(v5->add_ClientCertificateRequested(
            Callback<ICoreWebView2ClientCertificateRequestedEventHandler>(
                [](ICoreWebView2*,
                   ICoreWebView2ClientCertificateRequestedEventArgs* a) {
                  a->put_Cancel(TRUE);
                  return a->put_Handled(TRUE);
                })
                .Get(),
            &ignored))) {
      return false;
    }
    ComPtr<ICoreWebView2_14> v14;
    if (FAILED(webview_.As(&v14)) ||
        FAILED(v14->add_ServerCertificateErrorDetected(
            Callback<ICoreWebView2ServerCertificateErrorDetectedEventHandler>(
                [](ICoreWebView2*,
                   ICoreWebView2ServerCertificateErrorDetectedEventArgs* a) {
                  return a->put_Action(
                      COREWEBVIEW2_SERVER_CERTIFICATE_ERROR_ACTION_CANCEL);
                })
                .Get(),
            &ignored))) {
      return false;
    }
    ComPtr<ICoreWebView2_18> v18;
    return SUCCEEDED(webview_.As(&v18)) &&
           SUCCEEDED(v18->add_LaunchingExternalUriScheme(
               Callback<ICoreWebView2LaunchingExternalUriSchemeEventHandler>(
                   [](ICoreWebView2*,
                      ICoreWebView2LaunchingExternalUriSchemeEventArgs* a) {
                     return a->put_Cancel(TRUE);
                   })
                   .Get(),
               &ignored));
  }

  bool Attach() override {
    if (!host_ || !IsWindow(host_) || !controller_) return false;
    attached_ = true;
    timer_ = SetTimer(nullptr, 0, 200, &WinSurface::TimerProc);
    if (!timer_) return false;
    std::lock_guard<std::mutex> lock(timer_mutex_);
    timers_[timer_] = this;
    return SUCCEEDED(controller_->put_IsVisible(TRUE));
  }

  bool ApplyGeometry(const backend::Geometry& geometry) override {
    if (!std::isfinite(geometry.x) || !std::isfinite(geometry.y) ||
        !std::isfinite(geometry.width) || !std::isfinite(geometry.height) ||
        geometry.x < 0 || geometry.y < 0 || geometry.width <= 0 ||
        geometry.height <= 0 || geometry.x + geometry.width > 1 ||
        geometry.y + geometry.height > 1) {
      return false;
    }
    geometry_ = geometry;
    has_geometry_ = true;
    return ReapplyGeometry();
  }

  bool Navigate(const std::string& url) override {
    if (!backend::UrlPolicy::Allows(url)) return false;
    std::wstring wide = Wide(url);
    return !wide.empty() && SUCCEEDED(webview_->Navigate(wide.c_str()));
  }

  void Focus() override {
    if (controller_) {
      controller_->MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);
    }
  }

  void Destroy() override {
    if (destroyed_) return;
    destroyed_ = true;
    if (timer_) {
      KillTimer(nullptr, timer_);
      std::lock_guard<std::mutex> lock(timer_mutex_);
      timers_.erase(timer_);
      timer_ = 0;
    }
    if (controller_) {
      controller_->put_IsVisible(FALSE);
      controller_->Close();
    }
    webview_.Reset();
    controller_.Reset();
    host_ = nullptr;
  }

 private:
  bool ReapplyGeometry() {
    if (!has_geometry_ || !host_ || !IsWindow(host_) || !controller_) {
      return false;
    }
    RECT client{};
    if (!GetClientRect(host_, &client)) return false;
    const double scale =
        static_cast<double>(GetDpiForWindow(host_) ? GetDpiForWindow(host_)
                                                   : USER_DEFAULT_SCREEN_DPI) /
        USER_DEFAULT_SCREEN_DPI;
    const double width_dip = (client.right - client.left) / scale;
    const double height_dip = (client.bottom - client.top) / scale;
    RECT bounds{
        static_cast<LONG>(std::lround(geometry_.x * width_dip * scale)),
        static_cast<LONG>(std::lround(geometry_.y * height_dip * scale)),
        static_cast<LONG>(
            std::lround((geometry_.x + geometry_.width) * width_dip * scale)),
        static_cast<LONG>(
            std::lround((geometry_.y + geometry_.height) * height_dip * scale)),
    };
    return SUCCEEDED(controller_->put_Bounds(bounds));
  }

  void Tick() {
    if (destroyed_) return;
    if (!host_ || !IsWindow(host_)) {
      if (invalidated_) invalidated_();
      return;
    }
    ReapplyGeometry();
  }

  static void CALLBACK TimerProc(HWND, UINT, UINT_PTR timer, DWORD) {
    WinSurface* surface = nullptr;
    {
      std::lock_guard<std::mutex> lock(timer_mutex_);
      auto found = timers_.find(timer);
      if (found != timers_.end()) surface = found->second;
    }
    if (surface) surface->Tick();
  }

  HWND host_;
  ComPtr<ICoreWebView2Controller> controller_;
  ComPtr<ICoreWebView2> webview_;
  std::function<void()> invalidated_;
  backend::Geometry geometry_{};
  UINT_PTR timer_ = 0;
  bool debugging_enabled_;
  bool attached_ = false;
  bool has_geometry_ = false;
  bool destroyed_ = false;
  static std::mutex timer_mutex_;
  static std::map<UINT_PTR, WinSurface*> timers_;
};

std::mutex WinSurface::timer_mutex_;
std::map<UINT_PTR, WinSurface*> WinSurface::timers_;

class WinPlatform final : public backend::Platform,
                          public std::enable_shared_from_this<WinPlatform> {
 public:
  WinPlatform(VWWindowsHostLocator host_locator,
              VWWindowsDispatcher dispatcher,
              VWWindowsDiagnosticSink diagnostic_sink, void* context,
              bool debugging_enabled)
      : host_locator_(host_locator),
        dispatcher_(dispatcher),
        diagnostic_sink_(diagnostic_sink),
        context_(context),
        debugging_enabled_(debugging_enabled) {}

  void Dispatch(std::function<void()> work) override {
    auto* owned = new std::function<void()>(std::move(work));
    dispatcher_(
        context_,
        [](void* value) {
          std::unique_ptr<std::function<void()>> work(
              static_cast<std::function<void()>*>(value));
          (*work)();
        },
        owned);
  }

  std::shared_ptr<backend::Host> ResolveCurrentHost() override {
    HWND hwnd = host_locator_(context_);
    return hwnd ? std::make_shared<WinHost>(hwnd) : nullptr;
  }

  void EnsureEnvironment(
      std::function<void(backend::EnvironmentResult)> completion) override {
    if (environment_) {
      completion({backend::WindowsBackendRuntime::kOk, ""});
      return;
    }
    pending_.push_back(std::move(completion));
    if (creating_) return;
    creating_ = true;
    HRESULT com = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(com)) {
      FinishEnvironment(backend::WindowsBackendRuntime::kBackendFailure,
                        com == RPC_E_CHANGED_MODE
                            ? "WebView2 requires a Windows STA dispatcher"
                            : "WebView2 COM initialization failed");
      return;
    }
    auto options = Microsoft::WRL::Make<CoreWebView2EnvironmentOptions>();
    options->put_ReleaseChannels(COREWEBVIEW2_RELEASE_CHANNELS_STABLE);
    LPWSTR version = nullptr;
    int comparison = -1;
    HRESULT available = GetAvailableCoreWebView2BrowserVersionStringWithOptions(
        nullptr, options.Get(), &version);
    if (FAILED(available) || !version ||
        FAILED(CompareBrowserVersions(version, L"86.0.616.0", &comparison)) ||
        comparison < 0) {
      CoTaskMemFree(version);
      FinishEnvironment(backend::WindowsBackendRuntime::kRuntimeUnavailable,
                        "Evergreen WebView2 Runtime missing or insufficient");
      return;
    }
    CoTaskMemFree(version);
    std::weak_ptr<WinPlatform> weak = shared_from_this();
    HRESULT started = CreateCoreWebView2EnvironmentWithOptions(
        nullptr, nullptr, options.Get(),
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [weak](HRESULT result, ICoreWebView2Environment* environment) {
              if (auto self = weak.lock()) {
                if (SUCCEEDED(result) && environment) {
                  self->environment_ = environment;
                  self->FinishEnvironment(
                      backend::WindowsBackendRuntime::kOk, "");
                } else {
                  self->FinishEnvironment(
                      backend::WindowsBackendRuntime::kRuntimeUnavailable,
                      "Evergreen WebView2 environment creation failed");
                }
              }
              return S_OK;
            })
            .Get());
    if (FAILED(started)) {
      FinishEnvironment(backend::WindowsBackendRuntime::kRuntimeUnavailable,
                        "Evergreen WebView2 environment creation rejected");
    }
  }

  void CreateSurface(
      const std::shared_ptr<backend::Host>& host,
      std::function<void()> invalidated,
      std::function<void(std::shared_ptr<backend::Surface>, std::uint32_t,
                         std::string)> completion) override {
    auto win_host = std::dynamic_pointer_cast<WinHost>(host);
    if (!environment_ || !win_host || !win_host->IsValid()) {
      completion(nullptr, backend::WindowsBackendRuntime::kHostUnavailable,
                 "");
      return;
    }
    HWND hwnd = win_host->hwnd();
    bool debugging = debugging_enabled_;
    HRESULT started = environment_->CreateCoreWebView2Controller(
        hwnd,
        Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
            [hwnd, invalidated = std::move(invalidated),
             completion = std::move(completion), debugging](
                HRESULT result, ICoreWebView2Controller* controller) mutable {
              ComPtr<ICoreWebView2> webview;
              if (FAILED(result) || !controller ||
                  FAILED(controller->get_CoreWebView2(&webview))) {
                completion(nullptr,
                           backend::WindowsBackendRuntime::kBackendFailure,
                           "WebView2 controller creation failed");
                return S_OK;
              }
              auto surface = std::make_shared<WinSurface>(
                  hwnd, controller, webview, std::move(invalidated), debugging);
              if (!surface->Configure()) {
                surface->Destroy();
                completion(nullptr,
                           backend::WindowsBackendRuntime::kBackendFailure,
                           "WebView2 security policy setup failed");
                return S_OK;
              }
              completion(surface, backend::WindowsBackendRuntime::kOk, "");
              return S_OK;
            })
            .Get());
    if (FAILED(started)) {
      completion(nullptr, backend::WindowsBackendRuntime::kBackendFailure,
                 "WebView2 controller creation rejected");
    }
  }

  void Diagnose(const char* detail) {
    if (diagnostic_sink_) diagnostic_sink_(context_, detail);
  }

 private:
  void FinishEnvironment(std::uint32_t code, std::string detail) {
    creating_ = false;
    auto pending = std::move(pending_);
    pending_.clear();
    for (auto& callback : pending) {
      callback({code, detail});
    }
  }

  VWWindowsHostLocator host_locator_;
  VWWindowsDispatcher dispatcher_;
  VWWindowsDiagnosticSink diagnostic_sink_;
  void* context_;
  bool debugging_enabled_;
  bool creating_ = false;
  ComPtr<ICoreWebView2Environment> environment_;
  std::vector<std::function<void(backend::EnvironmentResult)>> pending_;
};

}  // namespace

struct VWWindowsBackend {
  std::shared_ptr<WinPlatform> platform;
  std::unique_ptr<backend::WindowsBackendRuntime> runtime;
};

extern "C" VW_WINDOWS_API VWWindowsBackend* verve_webview_windows_create(
    VWWindowsHostLocator host_locator, VWWindowsDispatcher dispatcher,
    VWWindowsCompletionSink completion_sink,
    VWWindowsHostLostSink host_lost_sink,
    VWWindowsDiagnosticSink diagnostic_sink, void* callback_context,
    int debugging_enabled) {
  if (!host_locator || !dispatcher || !completion_sink || !host_lost_sink) {
    return nullptr;
  }
  auto backend_handle = std::make_unique<VWWindowsBackend>();
  backend_handle->platform = std::make_shared<WinPlatform>(
      host_locator, dispatcher, diagnostic_sink, callback_context,
      debugging_enabled != 0);
  backend_handle->platform->Diagnose(
      "WebView2 secure defaults retain mixed-content blocking; file-system "
      "permissions and downloads are denied");
  backend_handle->platform->Diagnose(
      "WebView2 has no stable per-view HTML file-picker interception; the "
      "system user-mediated picker retains control");
  backend_handle->runtime = std::make_unique<backend::WindowsBackendRuntime>(
      backend_handle->platform,
      [completion_sink, callback_context](const backend::Completion& value) {
        completion_sink(callback_context, value.instance, value.operation,
                        value.generation, value.code,
                        value.diagnostic_detail.empty()
                            ? nullptr
                            : value.diagnostic_detail.c_str());
      },
      [host_lost_sink, callback_context](std::uint64_t instance) {
        host_lost_sink(callback_context, instance);
      });
  return backend_handle.release();
}

extern "C" VW_WINDOWS_API void verve_webview_windows_submit(
    VWWindowsBackend* backend_handle, uint32_t kind, uint64_t instance,
    uint64_t operation, uint32_t generation, const char* url,
    const VWWindowsSurfaceGeometry* geometry) {
  if (!backend_handle) return;
  std::optional<backend::Geometry> converted;
  if (geometry) {
    converted = backend::Geometry{geometry->x, geometry->y, geometry->width,
                                  geometry->height};
  }
  backend::Command command{
      kind == 1   ? backend::CommandKind::kInitialize
      : kind == 2 ? backend::CommandKind::kOpen
      : kind == 3 ? backend::CommandKind::kClose
      : kind == 4 ? backend::CommandKind::kDispose
                  : backend::CommandKind::kUnknown,
      instance,
      operation,
      generation,
      url ? url : "",
      converted,
  };
  backend_handle->runtime->Submit(std::move(command));
}

extern "C" VW_WINDOWS_API void verve_webview_windows_destroy(
    VWWindowsBackend* backend_handle) {
  delete backend_handle;
}
