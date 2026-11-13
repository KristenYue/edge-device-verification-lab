cmake_minimum_required(VERSION 3.20)
project(edge_device_verification_lab VERSION 0.1.0 LANGUAGES CXX)

option(EDGE_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(MSVC)
  add_compile_options(/W4 /permissive- /EHsc)
else()
  add_compile_options(-Wall -Wextra -Wpedantic)
  if(EDGE_ENABLE_SANITIZERS)
    add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
    add_link_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
  endif()
endif()

find_package(Threads REQUIRED)

add_library(edge_core
  cpp/src/state_machine.cpp
  cpp/src/protocol.cpp
)
target_include_directories(edge_core PUBLIC cpp/include)

add_executable(edge_device_simulator cpp/src/main.cpp)
target_link_libraries(edge_device_simulator PRIVATE edge_core Threads::Threads)
if(WIN32)
  target_link_libraries(edge_device_simulator PRIVATE ws2_32)
endif()

enable_testing()
add_executable(edge_core_tests cpp/tests/test_state_machine.cpp)
target_link_libraries(edge_core_tests PRIVATE edge_core)
add_test(NAME edge_core_tests COMMAND edge_core_tests)


