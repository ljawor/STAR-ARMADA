// W04: the native input codec must agree with the Python one byte for byte.
//
// The fixtures are written by `tools/render/write_input_fixtures.py` from the Python encoder. This
// test decodes them, checks every field, re-encodes the same events and compares the bytes, and
// refuses each malformed variant. Two encoders that each round-trip through themselves can still
// disagree on the wire; only a byte comparison catches that.
#include "input_ring.hpp"

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

using namespace armada::input;

static std::vector<uint8_t> slurp(const std::string& path) {
  std::ifstream file(path, std::ios::binary);
  if (!file)
    throw std::runtime_error("cannot read fixture: " + path);
  return std::vector<uint8_t>(std::istreambuf_iterator<char>(file),
                              std::istreambuf_iterator<char>());
}

static int failures = 0;

static void check(bool ok, const std::string& what) {
  if (!ok) {
    std::cerr << "FAIL " << what << '\n';
    ++failures;
  }
}

int main() {
  const char* dir = std::getenv("ARMADA_INPUT_FIXTURE_DIR");
  if (!dir) {
    std::cerr << "ARMADA_INPUT_FIXTURE_DIR is not set\n";
    return 2;
  }
  const std::string root(dir);

  const std::vector<Event> expected = {
      {kResize, 0, 0, 0, 0, (2560u << 16) | 1600u},
      {kMotion, 1, 0, 640, 400, 0},
      {kMotion, 1, 0, 700, 440, 0},
      {kButtonDown, 1, 0, 700, 440, 0},
      {kButtonUp, 1, 0, 700, 440, 0},
      {kWheel, 1, 0, 512, 300, 0},
      {kWheel, 0, 0, 512, 300, 0},
      // The fixture's shift is the either-shift mask the Python constant spells as one value.
      {kKeyDownEvent, uint8_t(kModShiftLeft | kModShiftRight), 'q', 0, 0, 0},
      {kKeyUpEvent, uint8_t(kModShiftLeft | kModShiftRight), 'q', 0, 0, 0},
      {kKeyDownEvent, 0, kCodeLeft, 0, 0, 0},
      {kKeyUpEvent, 0, kCodeLeft, 0, 0, 0},
      {kKeyDownEvent, kModCtrl, kCodeF1 + 4, 0, 0, 0},
      {kFocusLost, 0, 0, 0, 0, 0},
      {kQuit, 0, 0, 0, 0, 0},
  };

  const auto bytes = slurp(root + "/input-batch.bin");
  std::vector<Event> decoded;
  try {
    decoded = decodeBatch(bytes.data(), bytes.size());
  } catch (const std::exception& error) {
    std::cerr << "FAIL decode: " << error.what() << '\n';
    return 1;
  }
  check(decoded.size() == expected.size(), "event count");
  const size_t common = std::min(decoded.size(), expected.size());
  for (size_t i = 0; i < common; ++i)
    check(decoded[i] == expected[i], "event " + std::to_string(i));

  // Byte-for-byte agreement: the same events must produce the same frame the Python encoder wrote.
  const auto reencoded = encodeBatch(decoded);
  check(reencoded.size() == bytes.size(), "re-encoded size");
  check(reencoded == bytes, "re-encoded bytes");

  // Refusals: every malformed variant must be rejected, naming nothing about half-applied state
  // because nothing is applied.
  for (const char* name : {"bad-magic.bin", "bad-version.bin", "reserved.bin", "truncated.bin",
                           "trailing.bin", "bad-crc.bin", "unknown-kind.bin",
                           "over-ceiling.bin"}) {
    const auto frame = slurp(root + "/" + name);
    bool refused = false;
    try {
      decodeBatch(frame.data(), frame.size());
    } catch (const InputError&) {
      refused = true;
    }
    check(refused, std::string("refused ") + name);
  }

  // A batch written by the ring writer must come back out of the same slot the reader expects.
  const std::string ringPath = root + "/input-ring.bin";
  ::remove(ringPath.c_str());
  {
    RingWriter writer(ringPath, 4, kMinSlotBytes);
    check(writer.payloadBytes() == kMinSlotBytes - kSlotOverhead, "slot payload capacity");
    const auto first = writer.publish(bytes);
    const auto second = writer.publish(encodeBatch({{kQuit, 0, 0, 0, 0, 0}}));
    check(first == 0 && second == 1, "sequence numbering");
    check(writer.published() == 2, "published counter");
    if (writer.payloadBytes() < bytes.size() + 1) {
      std::cerr << "FAIL fixture does not fit a slot\n";
      return 1;
    }
  }
  {
    // The header the Python reader validates: magic, version, slots, slot bytes, published count.
    const auto file = slurp(ringPath);
    check(file.size() == kRingHeaderBytes + 4 * kMinSlotBytes, "ring file size");
    check(std::memcmp(file.data(), kRingMagic, 8) == 0, "ring magic");
    check(get16(file.data() + 8) == kRingVersion, "ring version");
    check(get16(file.data() + 10) == 4, "ring slots");
    check(get32(file.data() + 12) == kMinSlotBytes, "ring slot bytes");
    check(get64(file.data() + 16) == 2, "ring published");
    // First slot: begin tag, length, payload; closing tag at the end of the slot.
    check(get64(file.data() + kRingHeaderBytes) == 1, "slot begin tag");   // 2*0 + 1
    check(get32(file.data() + kRingHeaderBytes + 8) == bytes.size(), "slot length");
    check(get64(file.data() + kRingHeaderBytes + kMinSlotBytes - 8) == 2, "slot closing tag");
    check(std::memcmp(file.data() + kRingHeaderBytes + kSlotOverhead, bytes.data(), bytes.size()) ==
              0,
          "slot payload");
  }

  if (failures) {
    std::cerr << failures << " input codec checks failed\n";
    return 1;
  }
  std::cout << "input codec: " << decoded.size() << " events, " << bytes.size()
            << " bytes, byte-identical with the Python encoder, 8 malformed frames refused\n";
  return 0;
}
