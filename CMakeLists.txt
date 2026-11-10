cmake_minimum_required(VERSION 3.20)
project(TanksRecomp C CXX)

# Static recompilation of tanks.swf (Flash 5 / AVM1) to C++20 + SDL3.
#   tools/recomp/gen.py translates every ActionScript block of the SWF into C++ (gen/), at build time.
#   rt/ is the runtime (AVM1 semantics, display list, rasterizer, audio) forked from IsaacRecomp (MIT).
#   Assets are read from tanks.swf at runtime: put it next to the executable (or pass its path).

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

set(TANKS_SWF "${CMAKE_SOURCE_DIR}/tanks.swf" CACHE FILEPATH "SWF to recompile")
find_package(Python3 REQUIRED COMPONENTS Interpreter)
find_package(SDL3 REQUIRED CONFIG)
find_package(ZLIB REQUIRED)

# ---- generated code (one function per frame script, button action, clip event and function)
set(GEN_DIR "${CMAKE_BINARY_DIR}/gen")
set(GEN_STAMP "${GEN_DIR}/gen.stamp")
file(GLOB RECOMP_TOOLS "${CMAKE_SOURCE_DIR}/tools/recomp/*.py")
add_custom_command(
  OUTPUT "${GEN_STAMP}"
  COMMAND "${CMAKE_COMMAND}" -E rm -rf "${GEN_DIR}"
  COMMAND Python3::Interpreter -I "${CMAKE_SOURCE_DIR}/tools/recomp/gen.py" "${TANKS_SWF}" "${GEN_DIR}" --ns tanks --title Tanks
  COMMAND "${CMAKE_COMMAND}" -E touch "${GEN_STAMP}"
  DEPENDS "${TANKS_SWF}" ${RECOMP_TOOLS}
  COMMENT "Recompiling ActionScript of tanks.swf to C++")
add_custom_target(recomp DEPENDS "${GEN_STAMP}")

# The number of gen_N.cpp files depends on the SWF: they are compiled through one unity file per slot.
set(GEN_UNITS "")
foreach(i RANGE 0 7)
  set(u "${CMAKE_BINARY_DIR}/gen_unit_${i}.cpp")
  file(WRITE "${u}.in" "#if __has_include(\"gen_${i}.cpp\")\n#include \"gen_${i}.cpp\"\n#endif\n")
  configure_file("${u}.in" "${u}" COPYONLY)
  list(APPEND GEN_UNITS "${u}")
endforeach()
set(GEN_FIXED "${GEN_DIR}/gen_atoms.cpp" "${GEN_DIR}/gen_tables.cpp")
set_source_files_properties(${GEN_FIXED} PROPERTIES GENERATED TRUE)

# ---- PlutoVG (vector rasterizer)
file(GLOB PLUTOVG_SRC third_party/plutovg/source/*.c)
add_library(plutovg STATIC ${PLUTOVG_SRC})
target_include_directories(plutovg PUBLIC third_party/plutovg/include)
target_compile_definitions(plutovg PUBLIC PLUTOVG_BUILD_STATIC)
set_target_properties(plutovg PROPERTIES C_STANDARD 11)
target_compile_options(plutovg PRIVATE -O2 -w)

# ---- generated ActionScript
add_library(tanksgen STATIC ${GEN_UNITS} ${GEN_FIXED})
add_dependencies(tanksgen recomp)
target_include_directories(tanksgen PRIVATE rt "${GEN_DIR}")
target_compile_options(tanksgen PRIVATE -O1 -fno-strict-aliasing -w)

# ---- runtime + SDL3 front-end
add_executable(tanks
  rt/main_sdl3.cpp rt/core.cpp rt/builtins.cpp rt/display.cpp rt/swfload.cpp rt/audio.cpp
  rt/raster.cpp rt/snapshot.cpp rt/platform.cpp)
target_include_directories(tanks PRIVATE rt third_party)
target_compile_options(tanks PRIVATE -O2 -fno-strict-aliasing -Wall -Wno-unused-function -Wno-misleading-indentation)
target_link_libraries(tanks PRIVATE tanksgen plutovg SDL3::SDL3 ZLIB::ZLIB)
if(WIN32)
  target_link_options(tanks PRIVATE -static-libgcc -static-libstdc++)
  set_target_properties(tanks PROPERTIES WIN32_EXECUTABLE $<CONFIG:Release>)
endif()

# copy the SWF and the SDL3 runtime next to the executable
add_custom_command(TARGET tanks POST_BUILD
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${TANKS_SWF}" "$<TARGET_FILE_DIR:tanks>/tanks.swf"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different $<TARGET_RUNTIME_DLLS:tanks> "$<TARGET_FILE_DIR:tanks>"
  COMMAND_EXPAND_LISTS)
