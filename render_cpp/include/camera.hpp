#pragma once
#include <algorithm>
#include <array>
#include <cmath>
namespace armada {
struct Camera {
  std::array<float, 3> target{0, 0, 0};
  float distance = 8000, yaw = 0, pitch = 65, fov = 55;
  static constexpr float radians = 0.017453292519943295f;
  std::array<float, 3> eye() const {
    const float y = yaw * radians, p = pitch * radians;
    return {target[0] + distance * std::cos(p) * std::sin(y),
            target[1] + distance * std::sin(p),
            target[2] + distance * std::cos(p) * std::cos(y)};
  }
  void orbit(float dx, float dy) {
    yaw = std::remainder(yaw + dx, 360.f);
    pitch = std::clamp(pitch + dy, 5.f, 89.f);
  }
  void zoom(float steps) {
    distance =
        std::clamp(distance * std::exp(std::clamp(-steps * .13f, -20.f, 20.f)),
                   20.f, 100000.f);
  }
  void pan(float right, float forward, float seconds) {
    const float y = yaw * radians, s = distance * .5f * std::min(seconds, .1f);
    target[0] += (right * std::cos(y) - forward * std::sin(y)) * s;
    target[2] += (-right * std::sin(y) - forward * std::cos(y)) * s;
  }
};
} // namespace armada
