#pragma once
// W02 live-frame consumer: v2 packed frame decode and single-producer ring reader.
//
// Deliberately header-only and free of bgfx/SDL: the risky half of the C++ consumer is
// turning untrusted bytes into records without guessing, and that is testable without a
// GPU. Layouts are defined in docs/RENDER_BRIDGE_W02.md and produced by
// render_bridge/packed.py + render_bridge/ring.py; tests/test_frame_v2.cpp checks these
// decoders against a frame authored by that Python code, not against values typed here.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace armada::bridge {

struct FrameError : std::runtime_error {
  using std::runtime_error::runtime_error;
};

namespace detail {
inline uint32_t crc32(const uint8_t *data, size_t size) {
  uint32_t c = ~0u;
  for (size_t i = 0; i < size; ++i) {
    c ^= data[i];
    for (int bit = 0; bit < 8; ++bit)
      c = (c >> 1) ^ ((c & 1) ? 0xedb88320u : 0u);
  }
  return ~c;
}
inline void need(bool ok, const char *message) {
  if (!ok)
    throw FrameError(message);
}
template <typename T> inline T read_le(const uint8_t *p) {
  std::array<uint8_t, sizeof(T)> bytes{};
  std::memcpy(bytes.data(), p, sizeof(T));
  T value{};
  std::memcpy(&value, bytes.data(), sizeof(T)); // host is little-endian on both targets
  return value;
}
inline float read_f32(const uint8_t *p) {
  const uint32_t bits = read_le<uint32_t>(p);
  float value{};
  std::memcpy(&value, &bits, sizeof(float));
  return value;
}
} // namespace detail

constexpr char kFrameMagic[8] = {'A', 'R', 'M', 'A', 'D', 'A', 'F', '2'};
constexpr char kRingMagic[8] = {'A', 'R', 'M', 'A', 'D', 'A', 'R', '1'};
constexpr uint16_t kFrameVersion = 2;
constexpr uint16_t kWorldKind = 1;
constexpr size_t kHeaderBytes = 48;
constexpr size_t kInstanceBytes = 68;
constexpr size_t kEffectBytes = 52;
constexpr uint32_t kMaxInstances = 4096;
constexpr uint32_t kMaxEffects = 8192;
constexpr uint32_t kEffectClass = 2;
constexpr uint32_t kProjectileClass = 3;
constexpr size_t kRingHeaderBytes = 64;
constexpr size_t kSlotOverhead = 20; // begin tag 8, length 4 (offset of the frame bytes)
constexpr size_t kSlotTrailer = 8;   // the completing tag sits in the slot's last 8 bytes)

// The session's string tables. A frame only indexes them; the identity is the CRC of
// the serialized table body the producer sent.
struct Tables {
  std::vector<std::string> bindings;
  std::vector<std::string> kinds;
  uint32_t crc32 = 0;

  // `body` is the producer's ARMTBL2 payload (see render_bridge/packed.py).
  static Tables parse(const std::vector<uint8_t> &body);
};

// Instance flags. `kSurfaceFrame` says the 12 floats are a full basis, not a heading: surface
// hardware stands on the foundation the site generator chose, which no yaw and uniform scale can
// describe. A consumer must copy such a matrix verbatim and must not interpolate it.
constexpr uint16_t kFlagSelected = 1 << 0;
constexpr uint16_t kFlagDamaged = 1 << 1;
constexpr uint16_t kFlagDisabled = 1 << 2;
constexpr uint16_t kFlagSurfaceFrame = 1 << 3;
// Orbital hulls/scaffolds use the mesh channel but are not surface hardware.
constexpr uint16_t kFlagDynamicMesh = 1 << 4;

struct Instance {
  uint32_t entity_id = 0;
  uint16_t binding_id = 0;
  uint16_t flags = 0;
  std::array<uint8_t, 4> tint{255, 255, 255, 255};
  std::array<float, 12> matrix{};
  float hp = 1.0f;
  float shield = 1.0f;
};

struct Transient {
  uint8_t cls = 0;
  bool is_beam = false;
  uint16_t kind_id = 0;
  std::array<float, 3> position{};
  std::array<float, 3> velocity{};
  std::array<float, 3> end_position{};
  float life = 0.0f;
  float size = 1.0f;
  std::array<uint8_t, 4> colour{255, 255, 255, 255};
};

struct Frame {
  uint32_t tick = 0;
  uint64_t frame_index = 0;
  uint32_t flags = 0;
  std::vector<Instance> instances;
  std::vector<Transient> effects;
};

// Validates before it decodes: magic/version/kind, counts, table identity, length
// against counts, exact total length, CRC. Any mismatch throws; nothing is guessed.
inline Frame decode(const uint8_t *data, size_t size, const Tables &tables);

inline Frame decode(const std::vector<uint8_t> &data, const Tables &tables) {
  return decode(data.data(), data.size(), tables);
}

inline Frame decode(const uint8_t *data, size_t size, const Tables &tables) {
  using detail::need;
  need(data != nullptr && size >= kHeaderBytes, "truncated frame header");
  need(std::memcmp(data, kFrameMagic, 8) == 0, "unknown frame magic");
  need(detail::read_le<uint16_t>(data + 8) == kFrameVersion, "unknown frame version");
  need(detail::read_le<uint16_t>(data + 10) == kWorldKind, "frame kind is not world");

  const uint32_t tick = detail::read_le<uint32_t>(data + 12);
  const uint64_t frame_index = detail::read_le<uint64_t>(data + 16);
  const uint32_t n_inst = detail::read_le<uint32_t>(data + 24);
  const uint32_t n_eff = detail::read_le<uint32_t>(data + 28);
  const uint32_t table_crc = detail::read_le<uint32_t>(data + 32);
  const uint32_t flags = detail::read_le<uint32_t>(data + 36);
  const uint32_t length = detail::read_le<uint32_t>(data + 40);
  const uint32_t crc = detail::read_le<uint32_t>(data + 44);

  need(n_inst <= kMaxInstances && n_eff <= kMaxEffects, "frame exceeds record ceilings");
  need(table_crc == tables.crc32, "frame was packed against a different table");
  need(length == kInstanceBytes * size_t(n_inst) + kEffectBytes * size_t(n_eff),
       "payload length does not match its counts");
  need(size == kHeaderBytes + size_t(length), "trailing bytes forbidden");
  need(detail::crc32(data + kHeaderBytes, length) == crc, "frame CRC32 mismatch");

  Frame frame;
  frame.tick = tick;
  frame.flags = flags;
  frame.frame_index = frame_index;
  frame.instances.reserve(n_inst);
  frame.effects.reserve(n_eff);
  const uint8_t *cursor = data + kHeaderBytes;
  for (uint32_t i = 0; i < n_inst; ++i, cursor += kInstanceBytes) {
    Instance record;
    record.entity_id = detail::read_le<uint32_t>(cursor);
    record.binding_id = detail::read_le<uint16_t>(cursor + 4);
    record.flags = detail::read_le<uint16_t>(cursor + 6);
    need(record.binding_id < tables.bindings.size(), "binding_id outside the table");
    std::memcpy(record.tint.data(), cursor + 8, 4);
    for (int f = 0; f < 12; ++f)
      record.matrix[size_t(f)] = detail::read_f32(cursor + 12 + 4 * f);
    record.hp = detail::read_f32(cursor + 60);
    record.shield = detail::read_f32(cursor + 64);
    // A CRC-valid frame can still carry a non-finite number if the producer was fed one;
    // a renderer must never receive NaN geometry, so refuse it here as well as in Python.
    for (float value : record.matrix)
      need(std::isfinite(value), "non-finite instance matrix");
    need(std::isfinite(record.hp) && std::isfinite(record.shield),
         "non-finite instance status");
    frame.instances.push_back(record);
  }
  for (uint32_t i = 0; i < n_eff; ++i, cursor += kEffectBytes) {
    Transient record;
    record.cls = cursor[0];
    record.is_beam = cursor[1] != 0;
    record.kind_id = detail::read_le<uint16_t>(cursor + 2);
    need(record.cls == kEffectClass || record.cls == kProjectileClass,
         "unknown transient class");
    need(record.kind_id < tables.kinds.size(), "kind_id outside the table");
    for (int f = 0; f < 3; ++f)
      record.position[size_t(f)] = detail::read_f32(cursor + 4 + 4 * f);
    for (int f = 0; f < 3; ++f)
      record.velocity[size_t(f)] = detail::read_f32(cursor + 16 + 4 * f);
    for (int f = 0; f < 3; ++f)
      record.end_position[size_t(f)] = detail::read_f32(cursor + 28 + 4 * f);
    record.life = detail::read_f32(cursor + 40);
    record.size = detail::read_f32(cursor + 44);
    for (float value : record.position)
      need(std::isfinite(value), "non-finite transient position");
    for (float value : record.velocity)
      need(std::isfinite(value), "non-finite transient velocity");
    for (float value : record.end_position)
      need(std::isfinite(value), "non-finite transient end position");
    need(std::isfinite(record.life) && std::isfinite(record.size),
         "non-finite transient status");
    std::memcpy(record.colour.data(), cursor + 48, 4);
    frame.effects.push_back(record);
  }
  return frame;
}

inline Tables Tables::parse(const std::vector<uint8_t> &raw) {
  using detail::need;
  // ARMTBL2: <8s magic><H version><H binding count><I body bytes><body><u32 crc32>,
  // where the body is length-prefixed UTF-8 names — all bindings, then all kinds.
  // Mirrors render_bridge/packed.py Tables.encode().
  need(raw.size() >= 16 + 4, "table body too short");
  need(std::memcmp(raw.data(), "ARMTBL2\0", 8) == 0, "unknown table magic");
  need(detail::read_le<uint16_t>(raw.data() + 8) == kFrameVersion,
       "unknown table version");
  const uint16_t binding_count = detail::read_le<uint16_t>(raw.data() + 10);
  const uint32_t body_bytes = detail::read_le<uint32_t>(raw.data() + 12);
  const size_t header = 16;
  need(raw.size() == header + size_t(body_bytes) + 4, "table length mismatch");
  const uint32_t declared = detail::read_le<uint32_t>(raw.data() + header + body_bytes);
  need(detail::crc32(raw.data() + header, body_bytes) == declared, "table CRC mismatch");

  Tables tables;
  tables.crc32 = declared;
  size_t offset = header;
  const size_t end = header + body_bytes;
  while (offset < end) {
    const size_t length = raw[offset];
    need(offset + 1 + length <= end && length > 0, "table name runs past its body");
    const auto *start = reinterpret_cast<const char *>(raw.data() + offset + 1);
    auto &group = tables.bindings.size() < binding_count ? tables.bindings : tables.kinds;
    group.emplace_back(start, length);
    offset += 1 + length;
  }
  need(tables.bindings.size() == binding_count, "table binding count mismatch");
  need(offset == end, "table carries trailing name bytes");
  return tables;
}

// Pose recovered from an instance record's twelve floats. The layout is
// (c,0,-t)(0,s,0)(t,0,c) then the translation, so the vertical axis carries the uniform
// scale and the horizontal pair carries cos/sin of the yaw. Decomposing here rather than
// interpolating the matrix element by element keeps a turning hull at constant size
// instead of shrinking toward the chord between two rotations.
struct Pose {
  std::array<float, 3> position{};
  float yaw = 0.0f;
  float scale = 1.0f;
};

inline Pose pose_from_matrix(const std::array<float, 12> &matrix) {
  Pose pose;
  pose.position = {matrix[9], matrix[10], matrix[11]};
  pose.scale = matrix[4];
  if (!(pose.scale > 0.0f) || !std::isfinite(pose.scale))
    throw FrameError("instance matrix has no usable scale");
  pose.yaw = std::atan2(matrix[6], matrix[0]);
  return pose;
}

// Shortest-path angle interpolation: -pi -> +pi must cross zero, not go the long way.
inline float lerp_angle(float from, float to, float alpha) {
  float delta = std::remainder(to - from, 2.0f * float(M_PI));
  return from + delta * alpha;
}

// The viewer's 20-float instance record: four columns of four, as the W01 snapshot layout
// expects, followed by the tint.
inline void write_instance(float *out, const Pose &pose, const std::array<uint8_t, 4> &tint) {
  const float c = std::cos(pose.yaw) * pose.scale;
  const float t = std::sin(pose.yaw) * pose.scale;
  const float values[20] = {c,    0.0f, -t,      0.0f,
                            0.0f, pose.scale, 0.0f, 0.0f,
                            t,    0.0f, c,       0.0f,
                            pose.position[0], pose.position[1], pose.position[2], 1.0f,
                            tint[0] / 255.0f, tint[1] / 255.0f, tint[2] / 255.0f, tint[3] / 255.0f};
  std::memcpy(out, values, sizeof(values));
}

// Read-only attachment to the producer's ring file. The writer never blocks; this side
// reads straight from the file on every call (never a snapshot copy, which would freeze
// the picture at the first frame) and must tolerate a slot being overwritten mid-read by
// returning "nothing" instead of a mix of two frames.
class RingReader {
public:
  explicit RingReader(const std::filesystem::path &path) : path_(path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    if (!in)
      throw FrameError("ring file does not exist");
    const auto length = in.tellg();
    if (length < std::streamoff(kRingHeaderBytes))
      throw FrameError("ring file is smaller than its header");
    file_bytes_ = size_t(length);
    std::array<uint8_t, kRingHeaderBytes> header{};
    in.seekg(0);
    in.read(reinterpret_cast<char *>(header.data()), std::streamsize(header.size()));
    if (!in)
      throw FrameError("cannot read ring header");
    if (std::memcmp(header.data(), kRingMagic, 8) != 0)
      throw FrameError("unknown ring magic");
    version_ = detail::read_le<uint16_t>(header.data() + 8);
    slots_ = detail::read_le<uint16_t>(header.data() + 10);
    slot_bytes_ = detail::read_le<uint32_t>(header.data() + 12);
    if (version_ != 1)
      throw FrameError("unknown ring version");
    if (slots_ == 0 || slot_bytes_ < kSlotOverhead + kSlotTrailer)
      throw FrameError("ring header declares an invalid layout");
    if (file_bytes_ != kRingHeaderBytes + size_t(slots_) * slot_bytes_)
      throw FrameError("ring file size does not match its header");
  }

  uint64_t published() const {
    std::ifstream in(path_, std::ios::binary);
    if (!in)
      throw FrameError("cannot open ring file");
    std::array<uint8_t, 8> head{};
    field(in, 16, head.data(), head.size());
    return detail::read_le<uint64_t>(head.data());
  }
  uint16_t slots() const { return slots_; }
  uint32_t slot_bytes() const { return slot_bytes_; }
  uint32_t payload_bytes() const {
    return slot_bytes_ - uint32_t(kSlotOverhead) - uint32_t(kSlotTrailer);
  }
  const std::filesystem::path &path() const { return path_; }

  // Sequence numbers are monotonic and never reused; slot = sequence % slots.
  bool read(uint64_t sequence, std::vector<uint8_t> &out) const {
    return read_at_sequence(sequence, published(), out);
  }

  // Reading the newest frame against a *single* header snapshot matters: re-reading the
  // header inside the attempt lets a producer that is a frame or two ahead make this frame
  // look overwritten and silently drop the newest picture.
  bool read_at_sequence(uint64_t sequence, uint64_t available,
                        std::vector<uint8_t> &out) const {
    if (sequence >= available)
      return false;
    if (available - sequence > slots_)
      return false; // overwritten by newer frames
    std::ifstream in(path_, std::ios::binary);
    if (!in)
      throw FrameError("cannot open ring file");
    return attempt(in, sequence, out);
  }

  bool latest(std::vector<uint8_t> &out, uint64_t *sequence = nullptr) const {
    const uint64_t available = published();
    if (available == 0)
      return false;
    if (!read_at_sequence(available - 1, available, out))
      return false;
    if (sequence != nullptr)
      *sequence = available - 1;
    return true;
  }

  // Frames the producer published that this reader never consumed.
  uint64_t dropped_since(uint64_t last_sequence) const {
    const uint64_t available = published();
    if (available <= last_sequence + 1)
      return 0;
    return available - 1 - (last_sequence + 1);
  }

private:
  void field(std::ifstream &in, size_t offset, uint8_t *target, size_t size) const {
    if (offset + size > file_bytes_)
      throw FrameError("ring read runs past the file");
    in.seekg(std::streamoff(offset));
    in.read(reinterpret_cast<char *>(target), std::streamsize(size));
    if (!in)
      throw FrameError("cannot read ring payload");
  }

  bool attempt(std::ifstream &in, uint64_t sequence, std::vector<uint8_t> &out) const {
    const uint64_t expected_begin = 2 * sequence + 1;
    const uint64_t expected_end = expected_begin + 1;
    const size_t offset = size_t(kRingHeaderBytes) + size_t(sequence % slots_) * slot_bytes_;
    const size_t end_tag = offset + slot_bytes_ - 8;
    std::array<uint8_t, 8> tag{};
    field(in, offset, tag.data(), tag.size());
    if (detail::read_le<uint64_t>(tag.data()) != expected_begin)
      return false; // slot reused by a newer frame
    field(in, end_tag, tag.data(), tag.size());
    if (detail::read_le<uint64_t>(tag.data()) != expected_end)
      return false; // torn write in progress
    std::array<uint8_t, 4> length_field{};
    field(in, offset + 8, length_field.data(), length_field.size());
    const uint32_t length = detail::read_le<uint32_t>(length_field.data());
    if (length > payload_bytes())
      return false; // corrupt length; never trust it
    out.resize(length);
    field(in, offset + kSlotOverhead, out.data(), length);
    // Re-validate after the copy: a check before it cannot see a writer that started
    // re-using this slot while the bytes were being copied.
    field(in, offset, tag.data(), tag.size());
    if (detail::read_le<uint64_t>(tag.data()) != expected_begin)
      return false;
    field(in, end_tag, tag.data(), tag.size());
    if (detail::read_le<uint64_t>(tag.data()) != expected_end)
      return false;
    return true;
  }

  std::filesystem::path path_;
  size_t file_bytes_ = 0;
  uint16_t version_ = 0;
  uint16_t slots_ = 0;
  uint32_t slot_bytes_ = 0;
};

} // namespace armada::bridge
