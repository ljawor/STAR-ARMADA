// W04: the window's input, going back across the bridge to the simulation.
//
// Frames travel Python -> C++; input travels C++ -> Python. The transport is the same
// memory-mapped ring (`render_bridge/ring.py` layout: 64-byte header, slots with a
// beginning and closing sequence tag), because a consumer that falls behind must lose
// input the same way it loses frames: visibly and without corrupting anything.
//
// One ring frame holds a batch of fixed-size records. The batch header is 20 bytes
// (magic, version, count, reserved, crc32 of the records) and every record is 16 bytes:
//
//     u8 kind | u8 button | u16 code | i32 x | i32 y | u32 extra
//
// `code` is deliberately not an SDL or platform keycode: printable keys carry their ASCII
// value and everything else is one of the KeyCode constants below, which `render_bridge/
// input.py` shares. Mapping SDL keycodes here and again there would drift the first time
// SDL renumbers a scancode, and the symptom would be "that key does nothing".
//
// Nothing in this header decides anything. It records what the pointer and the keyboard
// did; the simulation still validates every command.
#pragma once

#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

#include <limits>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <filesystem>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace armada {
namespace input {

constexpr char kBatchMagic[8] = {'A', 'R', 'M', 'I', 'N', 'P', '0', '1'};
constexpr uint16_t kBatchVersion = 1;
constexpr size_t kBatchHeaderBytes = 20;
constexpr size_t kRecordBytes = 16;
constexpr size_t kMaxRecords = 1024;

constexpr char kRingMagic[8] = {'A', 'R', 'M', 'A', 'D', 'A', 'R', '1'};
constexpr uint16_t kRingVersion = 1;
constexpr size_t kRingHeaderBytes = 64;
constexpr size_t kSlotOverhead = 8 + 4 + 8;   // begin tag, length, and the closing
                                             // tag's reserved bytes (see kSlotTrailer)
constexpr size_t kSlotTrailer = 8;            // the closing tag at the end of the slot
constexpr size_t kMinSlotBytes = 1024;

enum Kind : uint8_t {
  kMotion = 1,
  kButtonDown = 2,
  kButtonUp = 3,
  kWheel = 4,
  kKeyDownEvent = 5,
  kKeyUpEvent = 6,
  kFocusLost = 7,
  kResize = 8,
  kQuit = 9,
};

enum Mod : uint8_t {
  kModShiftLeft = 0x01,
  kModShiftRight = 0x02,
  kModCtrl = 0x04,
  kModAlt = 0x08,
  kModGui = 0x10,
};

// Non-printable keys. Printable keys send their ASCII value instead.
enum KeyCode : uint16_t {
  kCodeEscape = 0x100,
  kCodeReturn = 0x101,
  kCodeTab = 0x102,
  kCodeBackspace = 0x103,
  kCodeDelete = 0x104,
  kCodeInsert = 0x105,
  kCodeSpace = 0x106,
  kCodeLeft = 0x110,
  kCodeRight = 0x111,
  kCodeUp = 0x112,
  kCodeDown = 0x113,
  kCodeHome = 0x114,
  kCodeEnd = 0x115,
  kCodePageUp = 0x116,
  kCodePageDown = 0x117,
  kCodeLShift = 0x120,
  kCodeRShift = 0x121,
  kCodeLCtrl = 0x122,
  kCodeRCtrl = 0x123,
  kCodeLAlt = 0x124,
  kCodeRAlt = 0x125,
  kCodeF1 = 0x130,
};

struct Event {
  uint8_t kind = 0;
  uint8_t button = 0;
  uint16_t code = 0;
  int32_t x = 0;
  int32_t y = 0;
  uint32_t extra = 0;

  bool operator==(const Event& other) const {
    return kind == other.kind && button == other.button && code == other.code &&
           x == other.x && y == other.y && extra == other.extra;
  }
};

class InputError : public std::runtime_error {
public:
  explicit InputError(const std::string& what) : std::runtime_error(what) {}
};

inline uint32_t crc32(const uint8_t* data, size_t size) {
  static uint32_t table[256];
  static bool ready = false;
  if (!ready) {
    for (uint32_t i = 0; i < 256; ++i) {
      uint32_t value = i;
      for (int bit = 0; bit < 8; ++bit)
        value = (value & 1u) ? (0xEDB88320u ^ (value >> 1)) : (value >> 1);
      table[i] = value;
    }
    ready = true;
  }
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0; i < size; ++i)
    crc = table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
  return crc ^ 0xFFFFFFFFu;
}

inline void put16(uint8_t* at, uint16_t value) {
  at[0] = uint8_t(value & 0xFF);
  at[1] = uint8_t((value >> 8) & 0xFF);
}

inline void put32(uint8_t* at, uint32_t value) {
  for (int i = 0; i < 4; ++i)
    at[i] = uint8_t((value >> (8 * i)) & 0xFF);
}

inline void put64(uint8_t* at, uint64_t value) {
  for (int i = 0; i < 8; ++i)
    at[i] = uint8_t((value >> (8 * i)) & 0xFF);
}

inline uint16_t get16(const uint8_t* at) {
  return uint16_t(at[0]) | uint16_t(at[1]) << 8;
}

inline uint32_t get32(const uint8_t* at) {
  return uint32_t(at[0]) | uint32_t(at[1]) << 8 | uint32_t(at[2]) << 16 |
         uint32_t(at[3]) << 24;
}

inline uint64_t get64(const uint8_t* at) {
  uint64_t value = 0;
  for (int i = 7; i >= 0; --i)
    value = (value << 8) | uint64_t(at[i]);
  return value;
}

//: Pack one batch. Refuses more records than the wire format allows.
inline std::vector<uint8_t> encodeBatch(const std::vector<Event>& events) {
  if (events.size() > kMaxRecords)
    throw InputError("batch exceeds the record ceiling");
  std::vector<uint8_t> out(kBatchHeaderBytes + events.size() * kRecordBytes, 0);
  std::memcpy(out.data(), kBatchMagic, 8);
  put16(out.data() + 8, kBatchVersion);
  put16(out.data() + 10, uint16_t(events.size()));
  put32(out.data() + 12, 0);                     // reserved
  uint8_t* records = out.data() + kBatchHeaderBytes;
  for (size_t i = 0; i < events.size(); ++i) {
    uint8_t* at = records + i * kRecordBytes;
    at[0] = events[i].kind;
    at[1] = events[i].button;
    put16(at + 2, events[i].code);
    put32(at + 4, uint32_t(events[i].x));
    put32(at + 8, uint32_t(events[i].y));
    put32(at + 12, events[i].extra);
  }
  put32(out.data() + 16, crc32(records, events.size() * kRecordBytes));
  return out;
}

//: Unpack and validate a batch. Throws rather than half-applying it, like every other
//: decoder on this bridge.
inline std::vector<Event> decodeBatch(const uint8_t* data, size_t size) {
  if (size < kBatchHeaderBytes)
    throw InputError("shorter than the batch header");
  if (std::memcmp(data, kBatchMagic, 8) != 0)
    throw InputError("bad batch magic");
  if (get16(data + 8) != kBatchVersion)
    throw InputError("unsupported batch version");
  const uint16_t count = get16(data + 10);
  if (get32(data + 12) != 0)
    throw InputError("reserved header field is not zero");
  if (count > kMaxRecords)
    throw InputError("batch exceeds the record ceiling");
  const size_t expected = kBatchHeaderBytes + size_t(count) * kRecordBytes;
  if (size != expected)
    throw InputError("length does not match the header");
  const uint8_t* records = data + kBatchHeaderBytes;
  if (get32(data + 16) != crc32(records, size_t(count) * kRecordBytes))
    throw InputError("record crc mismatch");
  std::vector<Event> events;
  events.reserve(count);
  for (uint16_t i = 0; i < count; ++i) {
    const uint8_t* at = records + size_t(i) * kRecordBytes;
    Event event;
    event.kind = at[0];
    event.button = at[1];
    event.code = get16(at + 2);
    event.x = int32_t(get32(at + 4));
    event.y = int32_t(get32(at + 8));
    event.extra = get32(at + 12);
    if (event.kind < kMotion || event.kind > kQuit)
      throw InputError("unknown event kind");
    events.push_back(event);
  }
  return events;
}

//: A single-producer ring the window writes input into. Mirrors `render_bridge/ring.py`
//: exactly, so the Python reader opens it with the code that already carries frames.
class RingWriter {
public:
  RingWriter(const std::string& path, uint16_t slots = 8, size_t slotBytes = 1u << 16) {
    if (slots < 1 || slots > 4096)
      throw InputError("slot count must be 1..4096");
    if (slotBytes < kMinSlotBytes)
      throw InputError("slot bytes below the minimum");
    if (slotBytes > (std::numeric_limits<uint32_t>::max)() ||
        slotBytes > ((std::numeric_limits<size_t>::max)() - kRingHeaderBytes) / slots)
      throw InputError("slot bytes exceed the wire or mapping size limit");
    slots_ = slots;
    slotBytes_ = slotBytes;
    const size_t total = kRingHeaderBytes + size_t(slots_) * slotBytes_;
#ifdef _WIN32
    // The public narrow path is UTF-8, not the machine's active ANSI code page.
    const auto nativePath = std::filesystem::u8path(path);
    file_ = ::CreateFileW(nativePath.c_str(), GENERIC_READ | GENERIC_WRITE,
                          FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS,
                          FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file_ == INVALID_HANDLE_VALUE)
      windowsFailure("cannot open the input ring");
    // Match Python's msvcrt.locking offset exactly. Locking payload byte zero would
    // deny ordinary file readers; a pathname mutex would miss hard-link aliases.
    OVERLAPPED producerLock{};
    producerLock.Offset = DWORD(kProducerLockOffset & 0xffffffffu);
    producerLock.OffsetHigh = DWORD(kProducerLockOffset >> 32);
    if (!::LockFileEx(file_, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY,
                      0, 1, 0, &producerLock))
      windowsFailure("cannot acquire input ring producer lock");
    // Never truncate in CreateFileW: producer ownership must precede file mutation.
    LARGE_INTEGER length{};
    length.QuadPart = static_cast<LONGLONG>(total);
    if (!::SetFilePointerEx(file_, length, nullptr, FILE_BEGIN) || !::SetEndOfFile(file_))
      windowsFailure("cannot size the input ring");
    mapping_ = ::CreateFileMappingW(file_, nullptr, PAGE_READWRITE, 0, 0, nullptr);
    if (!mapping_)
      windowsFailure("cannot create the input ring mapping");
    map_ = static_cast<uint8_t*>(::MapViewOfFile(mapping_, FILE_MAP_READ | FILE_MAP_WRITE,
                                               0, 0, total));
    if (!map_)
      windowsFailure("cannot map the input ring");
#else
    fd_ = ::open(path.c_str(), O_RDWR | O_CREAT, 0600);
    if (fd_ < 0)
      throw InputError("cannot open the input ring: " + path);
    // Single producer, like the frame ring: a second writer would restart the counter
    // under the first one and the consumer would report nonsense drops.
    if (::flock(fd_, LOCK_EX | LOCK_NB) != 0) {
      ::close(fd_);
      fd_ = -1;
      throw InputError("input ring already has a producer: " + path);
    }
    if (::ftruncate(fd_, off_t(total)) != 0) {
      ::close(fd_);
      fd_ = -1;
      throw InputError("cannot size the input ring");
    }
    void* mapped = ::mmap(nullptr, total, PROT_READ | PROT_WRITE, MAP_SHARED, fd_, 0);
    if (mapped == MAP_FAILED) {
      ::close(fd_);
      fd_ = -1;
      throw InputError("cannot map the input ring");
    }
    map_ = static_cast<uint8_t*>(mapped);
#endif
    bytes_ = total;
    std::memset(map_, 0, total);
    std::memcpy(map_, kRingMagic, 8);
    put16(map_ + 8, kRingVersion);
    put16(map_ + 10, slots_);
    put32(map_ + 12, uint32_t(slotBytes_));
    put64(map_ + 16, 0);
  }

  RingWriter(const RingWriter&) = delete;
  RingWriter& operator=(const RingWriter&) = delete;

  ~RingWriter() { close(); }

  void close() {
#ifdef _WIN32
    if (map_) {
      ::UnmapViewOfFile(map_);
      map_ = nullptr;
    }
    if (mapping_) {
      ::CloseHandle(mapping_);
      mapping_ = nullptr;
    }
    // The file handle owns the byte lock. Release it LAST, after all writable views.
    if (file_ != INVALID_HANDLE_VALUE) {
      ::CloseHandle(file_);
      file_ = INVALID_HANDLE_VALUE;
    }
#else
    if (map_) {
      ::munmap(map_, bytes_);
      map_ = nullptr;
    }
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
#endif
  }

  // The closing tag owns the slot's last bytes, so a batch that filled slotBytes_ -
  // kSlotOverhead would have its tail overwritten by that tag (and, in the last slot,
  // written past the mapping). ring.py and frame_v2.hpp subtract the same trailer.
  size_t payloadBytes() const { return slotBytes_ - kSlotOverhead - kSlotTrailer; }

  uint64_t published() const { return published_; }

  //: Copy one batch into the next slot. Returns its sequence number.
  uint64_t publish(const std::vector<uint8_t>& batch) {
    if (!map_)
      throw InputError("input ring is closed");
    if (batch.size() > payloadBytes())
      throw InputError("batch exceeds the slot capacity");
    const uint64_t sequence = published_;
    const size_t offset = kRingHeaderBytes + size_t(sequence % slots_) * slotBytes_;
    const uint64_t inProgress = 2 * sequence + 1;
    const uint64_t complete = inProgress + 1;
    put64(map_ + offset, inProgress);
    put32(map_ + offset + 8, uint32_t(batch.size()));
    std::memcpy(map_ + offset + kSlotOverhead, batch.data(), batch.size());
    put64(map_ + offset + slotBytes_ - 8, complete);
    published_ = sequence + 1;
    put64(map_ + 16, published_);        // head last: a reader that sees n can trust slot n
    return sequence;
  }

private:
  uint8_t* map_ = nullptr;
  size_t bytes_ = 0;
  size_t slotBytes_ = 0;
  uint16_t slots_ = 0;
  uint64_t published_ = 0;
#ifdef _WIN32
  static constexpr uint64_t kProducerLockOffset = uint64_t{1} << 62;
  HANDLE file_ = INVALID_HANDLE_VALUE;
  HANDLE mapping_ = nullptr;

  [[noreturn]] void windowsFailure(const char* operation) {
    const DWORD error = ::GetLastError();
    // A throwing constructor has no destructor: explicitly release partially acquired
    // mappings/handles and the producer lock on every failed acquisition.
    close();
    throw InputError(std::string(operation) + " (Windows error " + std::to_string(error) + ")");
  }
#else
  int fd_ = -1;
#endif
};

}  // namespace input
}  // namespace armada
