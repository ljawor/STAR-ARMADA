// Native side of the W02 bridge: decode the frame the Python producer wrote, refuse
// every malformed variant of it, and read it out of the producer's ring layout.
//
// The fixtures are committed bytes authored by tools/render/write_frame_fixtures.py, so a
// failure here means the two languages disagree about the wire format — not that this test
// checked its own arithmetic.
#include "frame_v2.hpp"

#include <nlohmann/json.hpp>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <thread>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using armada::bridge::FrameError;
using Json = nlohmann::json;

namespace {

int failures = 0;

void check(bool ok, const std::string &what) {
  if (!ok) {
    std::cerr << "FAIL " << what << '\n';
    ++failures;
  }
}

template <typename Fn> void refuses(Fn &&fn, const std::string &what) {
  try {
    fn();
    std::cerr << "FAIL " << what << " (accepted a frame it should refuse)\n";
    ++failures;
  } catch (const FrameError &) {
    // expected: malformed input is refused, never guessed at
  } catch (const std::exception &e) {
    std::cerr << "FAIL " << what << " (wrong exception: " << e.what() << ")\n";
    ++failures;
  }
}

std::vector<uint8_t> read_bytes(const fs::path &path) {
  std::ifstream in(path, std::ios::binary | std::ios::ate);
  if (!in)
    throw std::runtime_error("cannot open " + path.string());
  const auto length = in.tellg();
  std::vector<uint8_t> bytes(static_cast<size_t>(length));
  in.seekg(0);
  if (!bytes.empty())
    in.read(reinterpret_cast<char *>(bytes.data()), length);
  return bytes;
}

void write_bytes(const fs::path &path, const std::vector<uint8_t> &bytes) {
  std::ofstream out(path, std::ios::binary | std::ios::trunc);
  out.write(reinterpret_cast<const char *>(bytes.data()), std::streamsize(bytes.size()));
  if (!out)
    throw std::runtime_error("cannot write " + path.string());
}

void put_u16(std::vector<uint8_t> &bytes, size_t offset, uint16_t value) {
  std::memcpy(bytes.data() + offset, &value, sizeof(value));
}
void put_u32(std::vector<uint8_t> &bytes, size_t offset, uint32_t value) {
  std::memcpy(bytes.data() + offset, &value, sizeof(value));
}
void put_u64(std::vector<uint8_t> &bytes, size_t offset, uint64_t value) {
  std::memcpy(bytes.data() + offset, &value, sizeof(value));
}

// Recompute the header CRC after a deliberate payload edit, so a control exercises the
// check it names rather than dying at the CRC first.
void reseal(std::vector<uint8_t> &frame) {
  const uint32_t length = uint32_t(frame.size() - armada::bridge::kHeaderBytes);
  put_u32(frame, 40, length);
  put_u32(frame, 44, armada::bridge::detail::crc32(
                        frame.data() + armada::bridge::kHeaderBytes, length));
}

void test_tables(const fs::path &dir, const Json &expected) {
  const auto raw = read_bytes(dir / "tables-v2.bin");
  const auto tables = armada::bridge::Tables::parse(raw);
  check(tables.crc32 == expected["table"]["crc32"].get<uint32_t>(), "table crc");
  check(tables.bindings == expected["table"]["bindings"].get<std::vector<std::string>>(),
        "table binding names");
  check(tables.kinds == expected["table"]["kinds"].get<std::vector<std::string>>(),
        "table kind names");

  auto corrupt = raw;
  corrupt[20] ^= 0x01; // inside a binding name
  refuses([&] { armada::bridge::Tables::parse(corrupt); }, "table with a flipped name byte");
  auto truncated = raw;
  truncated.pop_back();
  refuses([&] { armada::bridge::Tables::parse(truncated); }, "table missing its crc");
  auto short_body = raw;
  put_u32(short_body, 12, armada::bridge::detail::read_le<uint32_t>(raw.data() + 12) + 1);
  refuses([&] { armada::bridge::Tables::parse(short_body); }, "table with a wrong body length");
}

void test_frame(const fs::path &dir, const Json &expected) {
  const auto tables = armada::bridge::Tables::parse(read_bytes(dir / "tables-v2.bin"));
  const auto raw = read_bytes(dir / "frame-v2.bin");
  const auto frame = armada::bridge::decode(raw, tables);

  check(frame.tick == expected["frame"]["tick"].get<uint32_t>(), "frame tick");
  check(frame.frame_index == expected["frame"]["frame_index"].get<uint64_t>(), "frame index");
  check(frame.flags == expected["frame"]["flags"].get<uint32_t>(), "frame flags");
  check(frame.instances.size() == expected["frame"]["instances"].get<size_t>(),
        "instance count");
  check(frame.effects.size() == expected["frame"]["effects"].get<size_t>(), "transient count");
  check(raw.size() == expected["sizes"]["frame"].get<size_t>(), "frame byte size");
  check(armada::bridge::kHeaderBytes == expected["sizes"]["header"].get<size_t>(), "header size");
  check(armada::bridge::kInstanceBytes == expected["sizes"]["instance"].get<size_t>(),
        "instance stride");
  check(armada::bridge::kEffectBytes == expected["sizes"]["effect"].get<size_t>(),
        "transient stride");

  for (size_t i = 0; i < frame.instances.size() && i < expected["instance_records"].size(); ++i) {
    const auto &record = frame.instances[i];
    const auto &want = expected["instance_records"][i];
    check(record.entity_id == want["entity_id"].get<uint32_t>(), "instance entity id");
    check(tables.bindings.at(record.binding_id) == want["binding"].get<std::string>(),
          "instance binding");
    check(record.flags == want["flags"].get<uint16_t>(), "instance flags");
    for (int c = 0; c < 4; ++c)
      check(record.tint[size_t(c)] == want["tint"][size_t(c)].get<uint8_t>(), "instance tint");
    for (int f = 0; f < 12; ++f)
      check(record.matrix[size_t(f)] == want["matrix"][size_t(f)].get<float>(),
            "instance matrix element");
    check(record.hp == want["hp"].get<float>(), "instance hp");
    check(record.shield == want["shield"].get<float>(), "instance shield");
  }

  for (size_t i = 0; i < frame.effects.size() && i < expected["transient_records"].size(); ++i) {
    const auto &record = frame.effects[i];
    const auto &want = expected["transient_records"][i];
    check(record.cls == want["class"].get<uint8_t>(), "transient class");
    check(record.is_beam == want["is_beam"].get<bool>(), "transient beam flag");
    check(tables.kinds.at(record.kind_id) == want["kind"].get<std::string>(), "transient kind");
    for (int f = 0; f < 3; ++f) {
      check(record.position[size_t(f)] == want["position"][size_t(f)].get<float>(),
            "transient position");
      check(record.velocity[size_t(f)] == want["velocity"][size_t(f)].get<float>(),
            "transient velocity");
      check(record.end_position[size_t(f)] == want["end_position"][size_t(f)].get<float>(),
            "transient end position");
    }
    check(record.life == want["life"].get<float>(), "transient life");
    check(record.size == want["size"].get<float>(), "transient size");
    for (int c = 0; c < 4; ++c)
      check(record.colour[size_t(c)] == want["colour"][size_t(c)].get<uint8_t>(),
            "transient colour");
  }

  // Every rejection path, each one reaching the check it names.
  // Flip a bit inside a matrix element: the value stays finite and in range, so the CRC
  // is the only check that can object. (A flip in the binding field would be caught by the
  // table check instead and this control would prove nothing about the CRC.)
  auto flipped = raw;
  flipped[armada::bridge::kHeaderBytes + 20] ^= 0x01;
  refuses([&] { armada::bridge::decode(flipped, tables); }, "payload with a flipped byte");

  // A NaN that the producer would never write, resealed so only the finiteness check can
  // catch it.
  auto not_finite = raw;
  put_u32(not_finite, armada::bridge::kHeaderBytes + 12, 0x7fc00000u);
  reseal(not_finite);
  refuses([&] { armada::bridge::decode(not_finite, tables); }, "non-finite matrix element");

  auto trailing = raw;
  trailing.push_back(0);
  refuses([&] { armada::bridge::decode(trailing, tables); }, "frame with a trailing byte");

  auto truncated = raw;
  truncated.resize(raw.size() - 4);
  refuses([&] { armada::bridge::decode(truncated, tables); }, "truncated frame");

  auto foreign = raw;
  put_u32(foreign, 32, tables.crc32 ^ 0xFFFFu);
  reseal(foreign);
  refuses([&] { armada::bridge::decode(foreign, tables); }, "frame packed against another table");

  auto outside = raw;
  put_u16(outside, armada::bridge::kHeaderBytes + 4, 999);
  reseal(outside);
  refuses([&] { armada::bridge::decode(outside, tables); }, "binding id outside the table");

  auto bad_kind = raw;
  const size_t first_effect = armada::bridge::kHeaderBytes +
                              armada::bridge::kInstanceBytes * frame.instances.size();
  put_u16(bad_kind, first_effect + 2, 999);
  reseal(bad_kind);
  refuses([&] { armada::bridge::decode(bad_kind, tables); }, "kind id outside the table");

  auto bad_class = raw;
  bad_class[first_effect] = 7;
  reseal(bad_class);
  refuses([&] { armada::bridge::decode(bad_class, tables); }, "unknown transient class");

  auto counted = raw;
  put_u32(counted, 24, 1);
  reseal(counted);
  refuses([&] { armada::bridge::decode(counted, tables); }, "count that disagrees with length");

  auto wrong_version = raw;
  put_u16(wrong_version, 8, 3);
  refuses([&] { armada::bridge::decode(wrong_version, tables); }, "version bump");
}

void test_ring(const fs::path &dir, const Json &expected) {
  const auto tables = armada::bridge::Tables::parse(read_bytes(dir / "tables-v2.bin"));
  const auto frame_bytes = read_bytes(dir / "frame-v2.bin");
  const uint32_t slot_bytes = 512;
  const uint16_t slots = 2;
  auto ring = std::vector<uint8_t>(armada::bridge::kRingHeaderBytes + slots * slot_bytes, 0);
  std::memcpy(ring.data(), "ARMADAR1", 8);
  put_u16(ring, 8, 1);
  put_u16(ring, 10, slots);
  put_u32(ring, 12, slot_bytes);

  const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
  const fs::path path =
      fs::temp_directory_path() / ("armada-ring-" + std::to_string(stamp) + ".bin");
  struct Remover {
    fs::path path;
    ~Remover() { std::error_code ec; fs::remove(path, ec); }
  } remover{path};

  const auto slot_offset = [&](uint64_t sequence) {
    return size_t(armada::bridge::kRingHeaderBytes) + size_t(sequence % slots) * slot_bytes;
  };
  const auto publish = [&](std::vector<uint8_t> &file, uint64_t sequence,
                           const std::vector<uint8_t> &payload, bool complete) {
    const size_t offset = slot_offset(sequence);
    put_u64(file, offset, 2 * sequence + 1);
    put_u32(file, offset + 8, uint32_t(payload.size()));
    std::memcpy(file.data() + offset + 20, payload.data(), payload.size());
    put_u64(file, offset + slot_bytes - 8, complete ? 2 * sequence + 2 : 0);
    put_u64(file, 16, sequence + 1);
  };

  publish(ring, 0, frame_bytes, true);
  write_bytes(path, ring);
  {
    armada::bridge::RingReader reader(path);
    check(reader.published() == 1, "ring published count");
    // 20 bytes of begin tag and length in front, 8 bytes of completing tag behind: a frame sized
    // to the old figure would have its tail overwritten by that tag.
    check(reader.payload_bytes() == slot_bytes - 28, "ring payload capacity");
    std::vector<uint8_t> out;
    check(reader.read(0, out), "ring read of the complete slot");
    check(out == frame_bytes, "ring handed back the exact frame bytes");
    check(reader.dropped_since(0) == 0, "no frames dropped between 0 and the newest");
    const auto decoded = armada::bridge::decode(out, tables);
    check(decoded.instances.size() == expected["frame"]["instances"].get<size_t>(),
          "ring frame decodes");
  }

  // A slot whose completing tag is missing must never be handed back.
  auto torn = ring;
  publish(torn, 1, frame_bytes, false);
  write_bytes(path, torn);
  {
    armada::bridge::RingReader reader(path);
    std::vector<uint8_t> out;
    check(!reader.read(1, out), "torn slot is not readable");
    check(reader.read(0, out), "the previous whole slot is still readable");
    check(reader.dropped_since(0) == 0, "a torn slot is not counted as a delivered frame");
  }

  // Once the writer has cycled past a slot, the old sequence is gone.
  auto cycled = torn;
  publish(cycled, 2, frame_bytes, true);
  write_bytes(path, cycled);
  {
    armada::bridge::RingReader reader(path);
    std::vector<uint8_t> out;
    check(!reader.read(0, out), "overwritten slot is refused");
    check(reader.read(2, out), "newest slot is readable");
    check(reader.dropped_since(0) == 1, "one frame skipped between sequence 0 and 2");
    uint64_t sequence = 0;
    check(reader.latest(out, &sequence) && sequence == 2, "latest() reports the newest sequence");
  }

  // Concurrent writer: a reader must never observe a payload that was never published.
  // This is the only control for the post-copy tag re-validation, because that check only
  // matters while a writer is re-using the slot.
  {
    auto live = cycled;
    live.resize(armada::bridge::kRingHeaderBytes + slots * slot_bytes, 0);
    const uint16_t live_slots = 4;   // the producer's own ring uses 8; 4 is enough here
    const uint32_t live_slot_bytes = 2048;
    live.assign(armada::bridge::kRingHeaderBytes + live_slots * live_slot_bytes, 0);
    std::memcpy(live.data(), "ARMADAR1", 8);
    put_u16(live, 8, 1);
    put_u16(live, 10, live_slots);
    put_u32(live, 12, live_slot_bytes);
    write_bytes(path, live);

    std::vector<std::vector<uint8_t>> payloads;
    for (int variant = 0; variant < 6; ++variant) {
      std::vector<uint8_t> payload(size_t(200 + variant * 16));
      for (size_t i = 0; i < payload.size(); ++i)
        payload[i] = uint8_t(variant * 37 + i);
      payloads.push_back(payload);
    }
    std::atomic<bool> stop{false};
    std::atomic<uint64_t> published_frames{0};
    std::vector<std::vector<uint8_t>> observed;
    std::thread writer([&] {
      std::fstream out(path, std::ios::binary | std::ios::in | std::ios::out);
      uint64_t sequence = 0;
      while (!stop.load()) {
        const auto &payload = payloads[size_t(sequence % payloads.size())];
        const size_t offset =
            armada::bridge::kRingHeaderBytes + size_t(sequence % live_slots) * live_slot_bytes;
        const uint64_t begin = 2 * sequence + 1;
        const uint64_t end = begin + 1;
        const uint32_t length = uint32_t(payload.size());
        out.seekp(std::streamoff(offset));
        out.write(reinterpret_cast<const char *>(&begin), 8);
        out.write(reinterpret_cast<const char *>(&length), 4);
        out.seekp(std::streamoff(offset + 20));
        out.write(reinterpret_cast<const char *>(payload.data()), std::streamsize(length));
        out.seekp(std::streamoff(offset + live_slot_bytes - 8));
        out.write(reinterpret_cast<const char *>(&end), 8);
        out.seekp(16);
        const uint64_t head = sequence + 1;
        out.write(reinterpret_cast<const char *>(&head), 8);
        out.flush();
        ++sequence;
        published_frames.store(sequence);
        // A 30-60 Hz producer leaves the reader plenty of room; an unthrottled writer
        // re-uses every slot faster than a file read can complete, which tests the test
        // rather than the lock.
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
      }
    });
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(250);
    armada::bridge::RingReader reader(path);
    std::vector<uint8_t> out;
    while (std::chrono::steady_clock::now() < deadline) {
      uint64_t sequence = 0;
      if (reader.latest(out, &sequence))
        observed.push_back(out);
      std::this_thread::yield();
    }
    stop.store(true);
    writer.join();
    check(!observed.empty(), "concurrent reader observed no frames");
    for (const auto &frame : observed) {
      bool whole = false;
      for (const auto &payload : payloads)
        if (frame == payload)
          whole = true;
      if (!whole) {
        check(false, "concurrent reader observed a torn frame");
        break;
      }
    }
  }

  // A ring file that does not match its own header is refused at attach time.
  auto lying = cycled;
  put_u32(lying, 12, slot_bytes + 8);
  write_bytes(path, lying);
  refuses([&] { armada::bridge::RingReader reader(path); }, "ring whose size contradicts its header");

  auto bad_magic = cycled;
  bad_magic[0] = 'X';
  write_bytes(path, bad_magic);
  refuses([&] { armada::bridge::RingReader reader(path); }, "ring with a foreign magic");
}

} // namespace

// The viewer draws interpolated poses, so the pose it recovers from a wire matrix has to
// be the pose that matrix means: same yaw, same scale, same position, and the same matrix
// when written back out. A transposed column layout passes decode checks and still renders
// every yawed hull as a flat pancake, which is what this covers.
static void test_pose() {
  using namespace armada::bridge;
  const std::array<float, 12> identity{1, 0, 0, 0, 1, 0, 0, 0, 1, 10, 0, 5};
  const auto straight = pose_from_matrix(identity);
  check(std::abs(straight.yaw) < 1e-5f, "identity yaw is zero");
  check(std::abs(straight.scale - 1.0f) < 1e-6f, "identity scale is one");
  check(straight.position[0] == 10.0f && straight.position[2] == 5.0f,
        "identity translation is read from the last column");

  // Quarter turn about +y at twice the size, authored the same way the producer does.
  const float c = std::cos(float(M_PI) / 2.0f) * 2.0f, s = std::sin(float(M_PI) / 2.0f) * 2.0f;
  const std::array<float, 12> turned{c, 0, -s, 0, 2, 0, s, 0, c, -4.5f, 0, 12.25f};
  const auto quarter = pose_from_matrix(turned);
  check(std::abs(quarter.yaw - float(M_PI) / 2.0f) < 1e-5f, "quarter turn yaw recovered");
  check(std::abs(quarter.scale - 2.0f) < 1e-6f, "quarter turn scale recovered");
  check(quarter.position[0] == -4.5f && quarter.position[2] == 12.25f,
        "quarter turn translation recovered");

  // Round trip through the viewer's 20-float layout.
  const std::array<uint8_t, 4> tint{64, 128, 192, 255};
  for (const auto &matrix : {identity, turned}) {
    const auto pose = pose_from_matrix(matrix);
    float out[20];
    write_instance(out, pose, tint);
    // The wire holds three floats per column, the viewer four, so map them by hand.
    const size_t wire_to_viewer[12] = {0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14};
    for (size_t i = 0; i < 12; ++i)
      check(std::abs(out[wire_to_viewer[i]] - matrix[i]) < 1e-5f,
            "written matrix matches the wire matrix");
    check(std::abs(out[15] - 1.0f) < 1e-6f, "written w column is one");
    check(std::abs(out[16] - 64.0f / 255.0f) < 1e-6f, "written tint is the wire tint");
  }

  // Shortest-path interpolation: +3 rad to -3 rad crosses zero, not the long way round.
  const float middle = lerp_angle(3.0f, -3.0f, 0.5f);
  check(std::abs(middle) > float(M_PI) - 0.2f, "angle interpolation takes the short way");
  check(std::abs(lerp_angle(0.2f, 0.4f, 0.5f) - 0.3f) < 1e-6f, "small angle halves");

  // A matrix with no vertical axis cannot be decomposed, and must say so.
  bool refused = false;
  try {
    pose_from_matrix({1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0});
  } catch (const FrameError &) {
    refused = true;
  }
  check(refused, "degenerate scale is refused");
}

int main(int argc, char **argv) {
  const fs::path dir = argc > 1 ? fs::path(argv[1]) : fs::path(ARMADA_FIXTURE_DIR);
  try {
    const auto expected_bytes = read_bytes(dir / "expected-v2.json");
    const auto expected = Json::parse(
        std::string(reinterpret_cast<const char *>(expected_bytes.data()), expected_bytes.size()));
    test_tables(dir, expected);
    test_frame(dir, expected);
    test_ring(dir, expected);
    test_pose();
  } catch (const std::exception &e) {
    std::cerr << "FATAL " << e.what() << '\n';
    return 2;
  }
  if (failures != 0) {
    std::cerr << failures << " frame_v2 check(s) failed\n";
    return 1;
  }
  std::cout << "frame_v2: all checks passed\n";
  return 0;
}
