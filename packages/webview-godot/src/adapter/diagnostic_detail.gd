extends RefCounted

const MAXIMUM_BYTES := 1024

static var _complete_url := RegEx.create_from_string("\\bhttps?://\\S+")
static var _windows_path := RegEx.create_from_string(
	"(?i)\\b[A-Z]:[\\\\/]\\S+"
)
static var _unix_home_path := RegEx.create_from_string(
	"(?i)(?:^|\\s)/(?:home|users)/[^\\s]+"
)
static var _memory_address := RegEx.create_from_string(
	"(?i)\\b0x[0-9a-f]+\\b"
)


static func normalize(detail: String) -> String:
	if detail.is_empty():
		return ""
	var safe := _complete_url.sub(detail, "<redacted-url>", true)
	safe = _windows_path.sub(safe, "<redacted-path>", true)
	safe = _unix_home_path.sub(safe, " <redacted-path>", true)
	safe = _memory_address.sub(safe, "<redacted-address>", true)
	var bytes := safe.to_utf8_buffer()
	if bytes.size() <= MAXIMUM_BYTES:
		return safe

	var length := MAXIMUM_BYTES
	while length > 0 and (bytes[length] & 0xc0) == 0x80:
		length -= 1
	return bytes.slice(0, length).get_string_from_utf8()


static func unknown_wire_code(wire_code: int, detail: String) -> String:
	var prefix := "Unknown Public Error Code wire ID %d." % wire_code
	var normalized := normalize(detail)
	if normalized.is_empty():
		return prefix
	return normalize("%s %s" % [prefix, normalized])
