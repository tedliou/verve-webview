package com.tedliou.verve.webview;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

/**
 * Serialized lifecycle seam shared by the Android WebView driver and its deterministic unit tests.
 *
 * <p>Commands enter from the native Core callback. Completions and host-loss notifications leave
 * through the two supplied sinks. Platform UI and WebView details stay behind {@link Platform}.
 */
public final class AndroidBackendRuntime {
  public static final int OK = 0;
  public static final int SURFACE_IN_USE = 205;
  public static final int HOST_UNAVAILABLE = 300;
  public static final int HOST_LOST = 301;
  public static final int BACKEND_FAILURE = 302;
  public static final int CLEANUP_FAILED = 303;

  private static final Object LEASE_LOCK = new Object();
  private static Long leaseOwner;

  private final Platform platform;
  private final CompletionSink completionSink;
  private final HostLostSink hostLostSink;
  private final Object generationLock = new Object();
  private final Map<Long, Integer> latestGenerations = new HashMap<>();
  private final Map<Long, SurfaceRecord> surfaces = new HashMap<>();

  public AndroidBackendRuntime(
      Platform platform, CompletionSink completionSink, HostLostSink hostLostSink) {
    this.platform = Objects.requireNonNull(platform);
    this.completionSink = Objects.requireNonNull(completionSink);
    this.hostLostSink = Objects.requireNonNull(hostLostSink);
  }

  /** Accepts work without resolving a host or completing inline. */
  public void submit(Command command) {
    Objects.requireNonNull(command);
    synchronized (generationLock) {
      Integer current = latestGenerations.get(command.instance);
      if (current == null || command.generation > current) {
        latestGenerations.put(command.instance, command.generation);
      }
    }
    platform.dispatch(() -> execute(command));
  }

  private void execute(Command command) {
    if (isStale(command)) {
      rollbackStale(command);
      return;
    }
    try {
      switch (command.kind) {
        case INITIALIZE:
          complete(
              command,
              usable(platform.resolveCurrentHost()) ? OK : HOST_UNAVAILABLE,
              null);
          break;
        case OPEN:
          open(command);
          break;
        case CLOSE:
          close(command);
          break;
        case DISPOSE:
          dispose(command);
          break;
        default:
          complete(command, BACKEND_FAILURE, "unknown lifecycle command");
      }
    } catch (RuntimeException error) {
      if (command.kind == Kind.OPEN) {
        cleanup(command.instance);
      }
      complete(command, BACKEND_FAILURE, safeStage(error));
    }
  }

  private void open(Command command) {
    Host currentHost = platform.resolveCurrentHost();
    if (!usable(currentHost)) {
      releaseLease(command.instance);
      complete(command, HOST_UNAVAILABLE, null);
      return;
    }

    SurfaceRecord existing = surfaces.get(command.instance);
    if (existing != null && !existing.host.sameHost(currentHost)) {
      cleanup(command.instance);
      complete(command, HOST_LOST, "host changed while the Surface was open");
      return;
    }

    boolean acquired = existing != null || acquireLease(command.instance);
    if (!acquired) {
      complete(command, SURFACE_IN_USE, null);
      return;
    }

    SurfaceRecord record = existing;
    if (record == null) {
      Surface surface =
          platform.createSurface(
              currentHost,
              () ->
                  platform.dispatch(
                      () -> hostInvalidated(command.instance, command.generation)));
      record = new SurfaceRecord(currentHost, surface);
      surfaces.put(command.instance, record);
      if (!surface.attach()) {
        cleanup(command.instance);
        complete(command, BACKEND_FAILURE, "WebView attach rejected");
        return;
      }
    }

    Geometry geometry = command.geometry == null ? Geometry.fullHost() : command.geometry;
    if (!record.surface.applyGeometry(geometry) || !record.surface.navigate(command.payload)) {
      if (existing == null) {
        cleanup(command.instance);
      }
      complete(command, BACKEND_FAILURE, "WebView geometry or navigation rejected");
      return;
    }
    complete(command, OK, null);
  }

  private void close(Command command) {
    if (!cleanup(command.instance)) {
      complete(command, BACKEND_FAILURE, "WebView cleanup failed");
      return;
    }
    complete(command, OK, null);
  }

  private void dispose(Command command) {
    boolean cleaned = cleanup(command.instance);
    complete(
        command,
        cleaned ? OK : CLEANUP_FAILED,
        cleaned ? null : "WebView disposal cleanup failed");
  }

  private void hostInvalidated(long instance, int generation) {
    synchronized (generationLock) {
      if (!Integer.valueOf(generation).equals(latestGenerations.get(instance))) {
        return;
      }
    }
    if (surfaces.containsKey(instance)) {
      cleanup(instance);
      hostLostSink.onHostLost(instance);
    }
  }

  private void rollbackStale(Command command) {
    if (command.kind == Kind.OPEN) {
      cleanup(command.instance);
    }
  }

  private boolean cleanup(long instance) {
    SurfaceRecord record = surfaces.remove(instance);
    boolean succeeded = true;
    if (record != null) {
      try {
        record.surface.destroy();
      } catch (RuntimeException ignored) {
        succeeded = false;
      }
    }
    releaseLease(instance);
    return succeeded;
  }

  private boolean isStale(Command command) {
    synchronized (generationLock) {
      return !Integer.valueOf(command.generation).equals(latestGenerations.get(command.instance));
    }
  }

  private void complete(Command command, int code, String diagnostic) {
    if (!isStale(command)) {
      completionSink.onCompletion(
          new Completion(
              command.instance, command.operation, command.generation, code, diagnostic));
    } else if (command.kind == Kind.OPEN) {
      cleanup(command.instance);
    }
  }

  private static boolean acquireLease(long instance) {
    synchronized (LEASE_LOCK) {
      if (leaseOwner == null || leaseOwner == instance) {
        leaseOwner = instance;
        return true;
      }
      return false;
    }
  }

  private static void releaseLease(long instance) {
    synchronized (LEASE_LOCK) {
      if (Long.valueOf(instance).equals(leaseOwner)) {
        leaseOwner = null;
      }
    }
  }

  private static boolean usable(Host host) {
    return host != null && host.isValid();
  }

  private static String safeStage(RuntimeException error) {
    return "Android Backend failure at " + error.getClass().getSimpleName();
  }

  public enum Kind {
    INITIALIZE,
    OPEN,
    CLOSE,
    DISPOSE
  }

  public static final class Geometry {
    public final double x;
    public final double y;
    public final double width;
    public final double height;

    public Geometry(double x, double y, double width, double height) {
      this.x = x;
      this.y = y;
      this.width = width;
      this.height = height;
    }

    public static Geometry fullHost() {
      return new Geometry(0.0, 0.0, 1.0, 1.0);
    }
  }

  public static final class Command {
    public final Kind kind;
    public final long instance;
    public final long operation;
    public final int generation;
    public final String payload;
    public final Geometry geometry;

    private Command(
        Kind kind,
        long instance,
        long operation,
        int generation,
        String payload,
        Geometry geometry) {
      this.kind = kind;
      this.instance = instance;
      this.operation = operation;
      this.generation = generation;
      this.payload = payload;
      this.geometry = geometry;
    }

    public static Command initialize(long instance, long operation, int generation) {
      return new Command(Kind.INITIALIZE, instance, operation, generation, "", null);
    }

    public static Command open(
        long instance,
        long operation,
        int generation,
        String url,
        Geometry geometry) {
      return new Command(Kind.OPEN, instance, operation, generation, url, geometry);
    }

    public static Command close(long instance, long operation, int generation) {
      return new Command(Kind.CLOSE, instance, operation, generation, "", null);
    }

    public static Command dispose(long instance, long operation, int generation) {
      return new Command(Kind.DISPOSE, instance, operation, generation, "", null);
    }
  }

  public static final class Completion {
    public final long instance;
    public final long operation;
    public final int generation;
    public final int code;
    public final String diagnosticDetail;

    Completion(long instance, long operation, int generation, int code, String diagnosticDetail) {
      this.instance = instance;
      this.operation = operation;
      this.generation = generation;
      this.code = code;
      this.diagnosticDetail = diagnosticDetail;
    }
  }

  public interface CompletionSink {
    void onCompletion(Completion completion);
  }

  public interface HostLostSink {
    void onHostLost(long instance);
  }

  /** Android framework boundary, implemented by the production WebView driver. */
  public interface Platform {
    void dispatch(Runnable work);

    Host resolveCurrentHost();

    default Surface createSurface(Host host, Runnable hostInvalidated) {
      throw new UnsupportedOperationException("surface creation is unavailable");
    }
  }

  public interface Host {
    boolean isValid();

    boolean sameHost(Host other);
  }

  public interface Surface {
    boolean attach();

    boolean applyGeometry(Geometry geometry);

    boolean navigate(String url);

    void destroy();
  }

  private static final class SurfaceRecord {
    private final Host host;
    private final Surface surface;

    private SurfaceRecord(Host host, Surface surface) {
      this.host = host;
      this.surface = surface;
    }
  }
}
