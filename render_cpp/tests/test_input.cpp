// W04: the native input codec must agree with the Python one byte for byte.
//
// The fixtures are written by `tools/render/write_input_fixtures.py` from the Python encoder. This
// test decodes them, checks every field, re-encodes the same events and compares the bytes, and
// refuses each malformed variant. Two encoders that each round-trip through themselves can still
// disagree on the wire; only a byte comparison catches that.
#include "input_ring.hpp"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <limits>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

using namespace armada::input;

static std::vector<uint8_t> slurp(const std::string& path) {
  std::ifstream file(std::filesystem::u8path(path), std::ios::binary);
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

// Runs on both backends. A refused contender must never resize or reset a live ring.
static void transport_contract(const std::string& path, const std::vector<uint8_t>& batch) {
  const auto diskPath = std::filesystem::u8path(path);
  const auto alias = std::filesystem::u8path(path + ".alias");
  std::filesystem::remove(diskPath);
  std::filesystem::remove(alias);
  // Create the alias before opening the producer: Windows may require delete sharing
  // when creating hard links, which is unrelated to the lock-identity contract.
  { std::ofstream seed(diskPath, std::ios::binary); }
  std::error_code aliasError;
  std::filesystem::create_hard_link(diskPath, alias, aliasError);
  check(!aliasError, "create hard-link alias for file-identity exclusion");
  {
    RingWriter writer(path, 4, kMinSlotBytes);
    writer.publish(batch);
    const auto before = slurp(path);
    bool refused = false;
    const auto start = std::chrono::steady_clock::now();
    try { RingWriter contender(path, 2, 2 * kMinSlotBytes); }
    catch (const InputError&) { refused = true; }
    check(refused, "second producer refused");
    check(std::chrono::steady_clock::now() - start < std::chrono::seconds(2),
          "producer refusal is nonblocking");
    check(slurp(path) == before, "refused producer leaves live bytes and file size untouched");

    // Hard links test file identity rather than a mutex derived from a path spelling.
    if (!aliasError) {
      refused = false;
      try { RingWriter contender(path + ".alias", 1, kMinSlotBytes); }
      catch (const InputError&) { refused = true; }
      check(refused, "producer through hard-link alias refused");
      check(slurp(path) == before, "alias contender leaves live ring untouched");
    }

    bool oversized = false;
    try { writer.publish(std::vector<uint8_t>(writer.payloadBytes() + 1)); }
    catch (const InputError&) { oversized = true; }
    check(oversized && writer.published() == 1, "oversize publish leaves head unchanged");
    check(writer.publish(batch) == 1, "failed contender does not disturb original writer");
    check(get64(slurp(path).data() + 16) == 2, "reader sees live mapped writes under producer lock");
    writer.close();
    writer.close();
    bool closed = false;
    try { writer.publish(batch); }
    catch (const InputError&) { closed = true; }
    check(closed, "publish after idempotent close refused");
    RingWriter replacement(path, 2, kMinSlotBytes);
    check(replacement.publish(batch) == 0, "close releases producer ownership before destructor");
  }
  {
    RingWriter replacement(path, 1, kMinSlotBytes);
    check(replacement.publish(batch) == 0, "destructor releases mapping and producer ownership");
  }
  // Reject unrepresentable dimensions before touching even an existing ring.
  const auto before = slurp(path);
  bool refused = false;
  try { RingWriter invalid(path, 4096, (std::numeric_limits<size_t>::max)()); }
  catch (const InputError&) { refused = true; }
  check(refused && slurp(path) == before, "invalid wire/mapping size rejected before file mutation");
  std::filesystem::remove(alias);
  std::filesystem::remove(diskPath);
}

#ifdef _WIN32
// Independent byte-range lock is the contract Python's msvcrt.locking must share.
// Keep the fixed offset here rather than borrowing the implementation's constant.
static OVERLAPPED producer_lock_position() {
  OVERLAPPED position{};
  position.OffsetHigh = 0x40000000u; // 1 << 62, one byte beyond every valid ring payload
  return position;
}

static void windows_lock_contract(const std::string& path) {
  const auto nativePath = std::filesystem::u8path(path);
  { std::ofstream seed(nativePath, std::ios::binary); seed << "do not truncate"; }
  HANDLE owner = ::CreateFileW(nativePath.c_str(), GENERIC_READ | GENERIC_WRITE,
                             FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
                             FILE_ATTRIBUTE_NORMAL, nullptr);
  check(owner != INVALID_HANDLE_VALUE, "open independent producer-lock handle");
  if (owner == INVALID_HANDLE_VALUE) return;
  auto position = producer_lock_position();
  const bool locked = ::LockFileEx(owner, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY,
                                   0, 1, 0, &position) != 0;
  check(locked, "acquire independent beyond-EOF producer lock");
  const auto before = slurp(path);
  bool refused = false;
  try { RingWriter contender(path, 1, kMinSlotBytes); }
  catch (const InputError&) { refused = true; }
  check(locked && refused, "native writer respects independently held Python-compatible lock");
  check(slurp(path) == before, "lock refusal occurs before sizing/header initialization");
  ::CloseHandle(owner);

  // Force failure AFTER lock acquisition: an existing mapped view prevents resize.
  // The throwing constructor must release its producer lock, not leak ownership.
  owner = ::CreateFileW(nativePath.c_str(), GENERIC_READ | GENERIC_WRITE,
                        FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
                        FILE_ATTRIBUTE_NORMAL, nullptr);
  HANDLE mapping = owner == INVALID_HANDLE_VALUE ? nullptr
      : ::CreateFileMappingW(owner, nullptr, PAGE_READONLY, 0, 0, nullptr);
  void* view = mapping ? ::MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0) : nullptr;
  check(view != nullptr, "create mapped-view resize-failure precondition");
  if (view) {
    refused = false;
    try { RingWriter contender(path, 1, kMinSlotBytes); }
    catch (const InputError&) { refused = true; }
    check(refused, "mapped backing refuses resize after producer lock acquired");
    check(slurp(path) == before, "failed resize preserves existing backing bytes");
    position = producer_lock_position();
    check(::LockFileEx(owner, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY,
                       0, 1, 0, &position) != 0,
          "throwing constructor releases producer lock on sizing failure");
    ::UnmapViewOfFile(view);
  }
  if (mapping) ::CloseHandle(mapping);
  if (owner != INVALID_HANDLE_VALUE) ::CloseHandle(owner);
  {
    RingWriter writer(path, 2, kMinSlotBytes);
    HANDLE contender = ::CreateFileW(nativePath.c_str(), GENERIC_READ | GENERIC_WRITE,
                                    FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
                                    FILE_ATTRIBUTE_NORMAL, nullptr);
    check(contender != INVALID_HANDLE_VALUE, "producer permits concurrent reader/writer handle open");
    if (contender != INVALID_HANDLE_VALUE) {
      position = producer_lock_position();
      const bool gotLock = ::LockFileEx(contender,
          LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &position) != 0;
      const DWORD lockError = ::GetLastError();
      check(!gotLock && lockError == ERROR_LOCK_VIOLATION,
            "native producer holds exact fixed beyond-EOF byte until close");
      // Ordinary ReadFile must remain usable: locking payload byte zero would break it.
      uint8_t magic[8]{};
      DWORD read = 0;
      check(::ReadFile(contender, magic, sizeof(magic), &read, nullptr) && read == sizeof(magic)
                && std::memcmp(magic, kRingMagic, sizeof(magic)) == 0,
            "producer byte lock does not block regular file readers");
      writer.close();
      position = producer_lock_position();
      check(::LockFileEx(contender, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY,
                         0, 1, 0, &position) != 0, "close releases exact producer byte");
      ::CloseHandle(contender);
    }
  }
  std::filesystem::remove(nativePath);
}
#endif

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
    // The closing tag lives in the slot's last eight bytes, so capacity is slot - overhead
    // - trailer (the same boundary ring.py and frame_v2.hpp use).
    check(writer.payloadBytes() == kMinSlotBytes - kSlotOverhead - kSlotTrailer,
          "slot payload capacity leaves room for the closing tag");
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
    // Exercise the boundary itself: a batch that exactly fills the capacity must leave
    // the closing tag intact and must not write past the mapping, and one byte more
    // must be refused rather than silently truncated.
    const std::string path = root + "/input-capacity.bin";
    ::remove(path.c_str());
    const size_t slots = 4;
    size_t capacity = 0;
    {
      RingWriter writer(path, slots, kMinSlotBytes);
      capacity = writer.payloadBytes();
      check(capacity + kSlotOverhead + kSlotTrailer == kMinSlotBytes,
            "capacity plus its framing is exactly one slot");
      // Pin the framing sizes themselves: the identity above holds for any pair of
      // constants, while these two numbers are what ring.py and frame_v2.hpp expect.
      check(kSlotOverhead == 20 && kSlotTrailer == 8,
            "slot framing is 20 bytes of header plus an 8-byte closing tag");
      std::vector<uint8_t> full(capacity);
      for (size_t i = 0; i < capacity; ++i)
        full[i] = uint8_t(i * 7 + 13);
      check(writer.publish(full) == 0, "full-capacity publish");
      bool overRefused = false;
      try {
        writer.publish(std::vector<uint8_t>(capacity + 1, 0x5a));
      } catch (const InputError&) {
        overRefused = true;
      }
      check(overRefused, "one byte over capacity is refused");
    }
    const auto file = slurp(path);
    check(file.size() == kRingHeaderBytes + slots * kMinSlotBytes,
          "full-capacity publish did not grow the mapping");
    uint64_t closing = 0;
    std::memcpy(&closing, file.data() + kRingHeaderBytes + kMinSlotBytes - kSlotTrailer,
                sizeof(closing));
    check(closing == 2, "closing tag survived a full-capacity payload");
    uint32_t length = 0;
    std::memcpy(&length, file.data() + kRingHeaderBytes + 8, sizeof(length));
    check(length == capacity, "full-capacity length field");
    // The tail of a full-capacity payload must survive: with the capacity eight bytes too
    // large, the closing tag overwrites the payload's last eight bytes.
    bool payloadIntact = true;
    for (size_t i = 0; i < capacity; ++i) {
      const uint8_t* stored = file.data() + kRingHeaderBytes + kSlotOverhead + i;
      if (*stored != uint8_t(i * 7 + 13)) {
        payloadIntact = false;
        std::cerr << "payload byte " << i << " was overwritten\n";
        break;
      }
    }
    check(payloadIntact, "full-capacity payload survives next to the closing tag");
    std::filesystem::remove(path);
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

  transport_contract(root + "/transport-\xC5\xBB\xC3\xB3\xC5\x82\xC4\x87.ring", bytes);
#ifdef _WIN32
  windows_lock_contract(root + "/windows-lock-contract.ring");
#endif

  if (failures) {
    std::cerr << failures << " input codec checks failed\n";
    return 1;
  }
  std::cout << "input codec: " << decoded.size() << " events, " << bytes.size()
            << " bytes, byte-identical with the Python encoder, 8 malformed frames refused\n";
  return 0;
}
