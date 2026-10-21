#include <cmath>
#include <iostream>
#include <stdexcept>
#if __has_include("camera.hpp")
#include "camera.hpp"
int main() {
  armada::Camera c;
  c.distance = 1000;
  c.yaw = 0;
  c.pitch = 45;
  const auto initial = c.eye();
  c.orbit(90, 0);
  if (std::abs(c.eye()[0] - initial[2]) > 0.01f)
    throw std::runtime_error("orbit does not turn camera");
  c.zoom(2);
  if (!(c.distance < 1000))
    throw std::runtime_error("zoom direction");
  for (int i = 0; i < 100; i++)
    c.zoom(100);
  if (c.distance < 20)
    throw std::runtime_error("zoom minimum");
  c.orbit(0, 1000);
  if (c.pitch > 89)
    throw std::runtime_error("pitch clamp");
  c.orbit(0, -2000);
  if (c.pitch < 5)
    throw std::runtime_error("pitch minimum");
  const auto before = c.target;
  c.pan(1, 0, 1);
  if (c.target == before)
    throw std::runtime_error("pan unchanged");
  if (!std::isfinite(c.eye()[0]))
    throw std::runtime_error("nonfinite eye");
  std::cout << "PASS camera orbit/zoom/pan bounds\n";
}
#else
int main() {
  std::cerr << "FAIL: camera control implementation missing\n";
  return 1;
}
#endif
