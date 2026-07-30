#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void Check(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}

std::vector<unsigned char> ReadBytes(const std::string& path) {
  std::string resolved = path;
  std::ifstream input(resolved, std::ios::binary);
  if (!input.good()) {
    const char* manifest_path = std::getenv("RUNFILES_MANIFEST_FILE");
    if (manifest_path) {
      std::ifstream manifest(manifest_path);
      const std::string key = "_main/" + path + " ";
      std::string line;
      while (std::getline(manifest, line)) {
        if (line.rfind(key, 0) == 0) {
          resolved = line.substr(key.size());
          input = std::ifstream(resolved, std::ios::binary);
          break;
        }
      }
    }
  }
  if (!input.good()) {
    throw std::runtime_error("contract input must be readable: " + resolved);
  }
  return {std::istreambuf_iterator<char>(input),
          std::istreambuf_iterator<char>()};
}

std::uint16_t U16(const std::vector<unsigned char>& value, std::size_t offset) {
  Check(offset + 2 <= value.size(), "PE uint16 must be in bounds");
  return static_cast<std::uint16_t>(value[offset]) |
         (static_cast<std::uint16_t>(value[offset + 1]) << 8);
}

std::uint32_t U32(const std::vector<unsigned char>& value, std::size_t offset) {
  Check(offset + 4 <= value.size(), "PE uint32 must be in bounds");
  return static_cast<std::uint32_t>(value[offset]) |
         (static_cast<std::uint32_t>(value[offset + 1]) << 8) |
         (static_cast<std::uint32_t>(value[offset + 2]) << 16) |
         (static_cast<std::uint32_t>(value[offset + 3]) << 24);
}

}  // namespace

int main(int argc, char** argv) {
  try {
    std::string manifest;
    std::string metadata;
    std::vector<unsigned char> dll;
    for (int index = 1; index < argc; ++index) {
      std::string path = argv[index];
      auto bytes = ReadBytes(path);
      if (path.size() >= 4 && path.substr(path.size() - 4) == ".txt") {
        manifest.assign(bytes.begin(), bytes.end());
      } else if (path.find("runtime-metadata.json") != std::string::npos) {
        metadata.assign(bytes.begin(), bytes.end());
      } else if (path.size() >= 4 && path.substr(path.size() - 4) == ".dll") {
        dll = std::move(bytes);
      }
    }
    Check(
        manifest ==
            "platform=windows\n"
            "payload=release/windows/x86_64/verve_webview_windows.dll\n",
        "canonical manifest must name the Windows x86_64 DLL");
    for (const char* expected : {
             "\"minimum_runtime_version\": \"86.0.616.0\"",
             "\"loader_linkage\": \"static\"",
             "\"runtime_distribution\": \"evergreen\"",
             "\"sdk_version\": \"1.0.4078.44\"",
             "\"runner\": \"windows-2022\"",
             "dc4d1d9168df26b830398303e50210b6e1729f6ce5a7ac69d2c766852f489962",
         }) {
      Check(metadata.find(expected) != std::string::npos,
            "runtime provenance field must be present");
    }
    Check(dll.size() > 0x40 && dll[0] == 'M' && dll[1] == 'Z',
          "payload must begin with a DOS header");
    const std::uint32_t pe = U32(dll, 0x3c);
    Check(pe + 6 <= dll.size() && dll[pe] == 'P' && dll[pe + 1] == 'E' &&
              dll[pe + 2] == 0 && dll[pe + 3] == 0,
          "payload must contain a PE header");
    Check(U16(dll, pe + 4) == 0x8664,
          "payload must target PE32+ x86_64");
    std::cout << "Windows Backend payload contract passed\n";
    return EXIT_SUCCESS;
  } catch (const std::exception& error) {
    std::cerr << "Windows Backend payload contract failed: " << error.what()
              << '\n';
    return EXIT_FAILURE;
  }
}
