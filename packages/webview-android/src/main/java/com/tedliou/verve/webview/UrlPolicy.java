package com.tedliou.verve.webview;

import java.net.URI;
import java.net.URISyntaxException;

final class UrlPolicy {
  private UrlPolicy() {}

  static boolean allows(String value) {
    if (value == null) {
      return false;
    }
    try {
      URI uri = new URI(value);
      String scheme = uri.getScheme();
      return ("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme))
          && uri.isAbsolute()
          && uri.getHost() != null
          && !uri.getHost().isEmpty()
          && uri.getRawUserInfo() == null;
    } catch (URISyntaxException ignored) {
      return false;
    }
  }
}
