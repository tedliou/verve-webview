#nullable enable
using System;
using System.Text;
using System.Text.RegularExpressions;

namespace Verve.WebView
{
    internal static class DiagnosticDetail
    {
        private const int MaximumBytes = 1024;
        private static readonly Regex CompleteUrl = new Regex(
            @"\bhttps?://\S+",
            RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
        private static readonly Regex WindowsPath = new Regex(
            @"\b[A-Z]:[\\/]\S+",
            RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
        private static readonly Regex MemoryAddress = new Regex(
            @"\b0x[0-9a-f]+\b",
            RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

        internal static string? Normalize(string? detail)
        {
            if (string.IsNullOrEmpty(detail))
            {
                return null;
            }

            string safe = CompleteUrl.Replace(detail, "<redacted-url>");
            safe = WindowsPath.Replace(safe, "<redacted-path>");
            safe = MemoryAddress.Replace(safe, "<redacted-address>");
            byte[] bytes = Encoding.UTF8.GetBytes(safe);
            if (bytes.Length <= MaximumBytes)
            {
                return safe;
            }

            int length = MaximumBytes;
            while (length > 0 && (bytes[length] & 0xC0) == 0x80)
            {
                length--;
            }
            return Encoding.UTF8.GetString(bytes, 0, length);
        }

        internal static string UnknownWireCode(uint wireCode, string? detail)
        {
            string prefix = "Unknown Public Error Code wire ID " + wireCode + ".";
            string? normalized = Normalize(detail);
            return Normalize(normalized == null ? prefix : prefix + " " + normalized) ?? prefix;
        }
    }
}
