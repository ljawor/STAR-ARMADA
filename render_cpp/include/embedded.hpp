// In-process, windowless renderer handshake. All bgfx calls stay on its one owner thread.
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
