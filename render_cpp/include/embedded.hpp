// Windowless renderer handshake. All bgfx calls stay on its one owner thread.
// PRIVATE INTERNAL ABI: armada_* exports require one serialized caller per session.
// No concurrent frame/poll/error/close calls are supported; error strings belong to
// that session and must be copied before the next call. The Python bridge confines
// library loading and every export call to a disposable native-worker process.
// A timeout/fatal error makes the session terminal: kill/reap that process rather
// than detaching its renderer thread or freeing state underneath a stuck close.
#pragma once
#include <condition_variable>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

struct EmbeddedState {
  std::mutex mutex;
  std::condition_variable cv;
  std::thread worker;
  bool stop = false, requested = false, completed = false, exited = false;
  std::string error;
  std::vector<unsigned char> pixels;
  bool beginFrame() {
    std::unique_lock lock(mutex);
    cv.wait(lock, [&] { return requested || stop; });
    if (stop) return false;
    requested = false;
    return true;
  }
  void finishFrame() {
    std::lock_guard lock(mutex);
    completed = true;
    cv.notify_all();
  }
};
