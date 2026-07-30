#nullable enable
using UnityEngine;

namespace Verve.WebView
{
    internal static class GeometryConverter
    {
        internal static NormalizedGeometry FromUnityRect(Rect rectangle, int viewportWidth, int viewportHeight)
        {
            if (viewportWidth <= 0 || viewportHeight <= 0)
            {
                return new NormalizedGeometry(double.NaN, double.NaN, double.NaN, double.NaN);
            }

            double width = viewportWidth;
            double height = viewportHeight;
            return new NormalizedGeometry(
                rectangle.x / width,
                1.0 - ((rectangle.y + rectangle.height) / height),
                rectangle.width / width,
                rectangle.height / height);
        }
    }
}
