package org.godotengine.godot.plugin;

import org.godotengine.godot.Godot;

/** Compile-only subset of the GodotPlugin API used by the v2 registration wrapper. */
public abstract class GodotPlugin {
  protected GodotPlugin(Godot godot) {}

  public abstract String getPluginName();
}
